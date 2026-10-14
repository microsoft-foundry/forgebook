"""Regression tests for the calibration library.

Run from this folder with: python -m unittest test_calibration
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import calibration as calib  # noqa: E402

FIELD = "invoice_id"


def filled_rows(n_correct: int, n_mistakes: int = 0, *, n_docs: int | None = None) -> pd.DataFrame:
    """Training values for one field, all with high confidence, spread evenly
    across ``n_docs`` documents (one value per document by default)."""
    n = n_correct + n_mistakes
    n_docs = n_docs or n
    return pd.DataFrame(
        {
            "document_id": [f"train-{i % n_docs}" for i in range(n)],
            "split": "train",
            "field_name": FIELD,
            "extracted_value": [f"INV-{i}" for i in range(n)],
            "confidence": [0.90 + (i % 10) / 100 for i in range(n)],
            "is_correct": [True] * n_correct + [False] * n_mistakes,
        }
    )


def blank_rows(n: int, *, n_docs: int | None = None) -> pd.DataFrame:
    """Training blanks for the same field, all truly blank, spread evenly
    across ``n_docs`` documents (one blank per document by default)."""
    n_docs = n_docs or n
    return pd.DataFrame(
        {
            "document_id": [f"blank-{i % n_docs}" for i in range(n)],
            "split": "train",
            "field_name": FIELD,
            "extracted_value": None,
            "confidence": 0.5,
            "is_correct": True,
        }
    )


def separated_rows(n_correct: int, n_mistakes: int) -> pd.DataFrame:
    """Training values whose confidence cleanly separates mistakes (low) from
    correct values (high), one value per document."""
    n = n_correct + n_mistakes
    return pd.DataFrame(
        {
            "document_id": [f"train-{i}" for i in range(n)],
            "split": "train",
            "field_name": FIELD,
            "extracted_value": [f"INV-{i}" for i in range(n)],
            "confidence": [0.90 + (i % 10) / 100 for i in range(n_correct)]
            + [0.10 + (i % 10) / 100 for i in range(n_mistakes)],
            "is_correct": [True] * n_correct + [False] * n_mistakes,
        }
    )


# One unseen wrong value with almost no confidence, plus one unseen blank.
UNSEEN = pd.DataFrame(
    {
        "document_id": ["test-0", "test-1"],
        "split": "test",
        "field_name": FIELD,
        "extracted_value": ["garbage", None],
        "confidence": [0.01, 0.5],
        "is_correct": [False, True],
    }
)


def shipped_routes(train: pd.DataFrame, target: float) -> tuple[dict, pd.DataFrame]:
    """Select policies at ``target``, save and reload the CSV, then route the
    unseen values with the reloaded table, as production would."""
    canonical = pd.concat([train, UNSEEN], ignore_index=True)
    policies = calib.select_policies(
        calib.fit_base_policies(canonical, n_bootstrap=200), target
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = calib.save_calibration_table(policies, Path(tmp) / "table.csv")
        shipped = calib.load_calibration_table(path)
    routed = calib.route_frame(canonical, shipped, split="test")
    return policies[FIELD], routed.set_index("document_id")


class ZeroMistakeFieldTests(unittest.TestCase):
    def test_stays_in_review_when_accuracy_bound_misses_the_target(self):
        # 20 perfect documents give a Wilson lower bound of about 0.84, short of 0.99.
        policy, routed = shipped_routes(filled_rows(20), target=0.99)

        self.assertEqual(policy["decision"], "always_review")
        self.assertTrue(routed.loc["test-0", "route_to_hitl"])
        self.assertEqual(routed.loc["test-0", "route_reason"], "non_null_uncalibrated")
        self.assertFalse(routed.loc["test-0", "stp_error"])

    def test_is_trusted_only_when_accuracy_bound_clears_the_target(self):
        # The same 20 perfect values clear an 0.80 target but not 0.90.
        policy, routed = shipped_routes(filled_rows(20), target=0.80)
        self.assertEqual(policy["decision"], "always_trust")
        self.assertFalse(routed.loc["test-0", "route_to_hitl"])
        self.assertEqual(routed.loc["test-0", "route_reason"], "always_trust")

        policy, _ = shipped_routes(filled_rows(20), target=0.90)
        self.assertEqual(policy["decision"], "always_review")

    def test_dial_sets_the_minimum_evidence(self):
        # At 0.80 the Wilson bound needs 16 perfect documents; no fixed floor.
        policy, _ = shipped_routes(filled_rows(16), target=0.80)
        self.assertEqual(policy["decision"], "always_trust")

        policy, _ = shipped_routes(filled_rows(15), target=0.80)
        self.assertEqual(policy["decision"], "always_review")

    def test_counts_documents_not_values(self):
        # 30 values from 10 receipts is only 10 independent pieces of evidence.
        policy, _ = shipped_routes(filled_rows(30, n_docs=10), target=0.80)
        self.assertEqual(policy["decision"], "always_review")

        policy, _ = shipped_routes(filled_rows(30, n_docs=30), target=0.80)
        self.assertEqual(policy["decision"], "always_trust")

    def test_blank_policy_is_decided_independently(self):
        # 400 true blanks clear 0.99 on their own, while the filled values don't.
        train = pd.concat([filled_rows(20), blank_rows(400)], ignore_index=True)
        policy, routed = shipped_routes(train, target=0.99)

        self.assertEqual(policy["decision"], "always_review")
        self.assertEqual(policy["null_policy"]["decision"], "null_to_stp")
        self.assertTrue(routed.loc["test-0", "route_to_hitl"])
        self.assertFalse(routed.loc["test-1", "route_to_hitl"])


class CalibratedCutoffTests(unittest.TestCase):
    def test_catch_rate_must_clear_the_target_with_95_percent_confidence(self):
        # Catching all 10 known mistakes is 100%, but its lower bound is ~72%.
        policy, routed = shipped_routes(separated_rows(100, 10), target=0.80)
        self.assertEqual(policy["decision"], "always_review")
        self.assertTrue(routed.loc["test-0", "route_to_hitl"])

        # 20 caught out of 20 has a lower bound of ~84%, which clears 0.80.
        policy, routed = shipped_routes(separated_rows(100, 20), target=0.80)
        self.assertEqual(policy["decision"], "calibrate")
        self.assertGreaterEqual(policy["achieved_catch_ci_lower"], 0.80)
        self.assertTrue(routed.loc["test-0", "route_to_hitl"])

        # The same evidence falls short of a 0.90 target.
        policy, _ = shipped_routes(separated_rows(100, 20), target=0.90)
        self.assertEqual(policy["decision"], "always_review")

    def test_one_known_mistake_cannot_clear_the_catch_bound(self):
        # Trusting the field would knowingly approve its one known mistake, and
        # catching one of one is too little evidence for any cutoff.
        policy, routed = shipped_routes(filled_rows(200, n_mistakes=1), target=0.50)

        self.assertEqual(policy["decision"], "always_review")
        self.assertTrue(routed.loc["test-0", "route_to_hitl"])


class BlankTrackTests(unittest.TestCase):
    def test_counts_documents_not_blanks(self):
        policy, _ = shipped_routes(
            pd.concat([filled_rows(20), blank_rows(30, n_docs=10)]), target=0.80
        )
        self.assertEqual(policy["null_policy"]["decision"], "null_to_hitl")

        policy, _ = shipped_routes(
            pd.concat([filled_rows(20), blank_rows(30, n_docs=30)]), target=0.80
        )
        self.assertEqual(policy["null_policy"]["decision"], "null_to_stp")

    def test_dial_sets_the_minimum_evidence(self):
        # 8 truly blank documents give a lower bound of ~0.68: enough for a
        # 0.65 target, not for 0.70. No fixed minimum count applies.
        train = pd.concat([filled_rows(20), blank_rows(8)])
        policy, _ = shipped_routes(train, target=0.65)
        self.assertEqual(policy["null_policy"]["decision"], "null_to_stp")

        policy, _ = shipped_routes(train, target=0.70)
        self.assertEqual(policy["null_policy"]["decision"], "null_to_hitl")


class DemoDataTests(unittest.TestCase):
    def test_default_path_loads_bundled_receipts(self):
        data = calib.load_demo_data()
        self.assertEqual(data["document_id"].nunique(), 1000)


if __name__ == "__main__":
    unittest.main()
