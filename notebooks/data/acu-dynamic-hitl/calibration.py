"""Thin, notebook-friendly wrapper around :mod:`acu_calibrator`.

Everything here operates on one **canonical frame**: one row per extracted
field value, with these columns.

===========================  ==================================================
``document_id``              which document the value came from; keeps repeated
                             line items from leaking across CV folds
``split``                    ``"train"`` | ``"test"``
``field_name``               the field this value belongs to
``extracted_value``          what Content Understanding returned (``None`` when
                             CU returned nothing)
``confidence``               CU's confidence score for that value, 0-1
``is_correct``               whether the extracted value matched ground truth
===========================  ==================================================

``ground_truth_value`` and ``observation_id`` are carried along for inspection
but are not used by the calibration itself.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from acu_calibrator import (
    CalibrationConfig,
    build_routing_policies,
    estimate_hitl_savings,
    redecide_policy,
    sweep_target_savings,
)
from acu_calibrator import _is_null_value as _is_null


DEMO_DATA_PATH = Path(__file__).resolve().parent / "data" / "cord_demo.parquet"

# A field earns an automatic cutoff only if the lower end of its AUC confidence
# interval clears this bar -- i.e. we are 95% sure its confidence ranks correct
# values above incorrect ones better than a coin flip.
MIN_AUC_CI_LOWER = 0.50

_REQUIRED_COLUMNS = (
    "document_id",
    "split",
    "field_name",
    "extracted_value",
    "confidence",
    "is_correct",
)

# Route reasons emitted when a fitted confidence cutoff made the call, as
# opposed to the blank track or a blanket always-review / always-trust rule.
THRESHOLD_ROUTE_REASONS = frozenset(
    {
        "lr_below_threshold",
        "lr_above_threshold",
        "raw_below_threshold",
        "raw_above_threshold",
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# Loading
# ─────────────────────────────────────────────────────────────────────────────


def load_demo_data(path: str | Path | None = None) -> pd.DataFrame:
    """Load the bundled CORD v2 receipt results (1,000 documents of measured
    Content Understanding output, no Azure credentials required)."""
    return load_canonical_file(path or DEMO_DATA_PATH)


def load_canonical_file(path: str | Path) -> pd.DataFrame:
    """Load a canonical frame from Parquet or CSV and validate its columns."""
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"dataset not found: {source}")
    if source.suffix.lower() == ".csv":
        frame = pd.read_csv(source)
    else:
        frame = pd.read_parquet(source)
    missing = [column for column in _REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise KeyError(f"dataset is missing required columns: {missing}")
    # The lab uses a two-way 80/20 holdout, so any 'validation' rows join the
    # test holdout here rather than in the file itself.
    frame["split"] = frame["split"].replace("validation", "test")
    return frame


def calibration_input(canonical: pd.DataFrame, *, split: str = "train") -> pd.DataFrame:
    """Slice one split out of a canonical frame, ready for calibration.

    Line items the extraction never returned are left out: in production no
    row exists for them, so no routing decision is ever made about them, and
    counting them here would credit the policy with catching mistakes it can
    never see. :func:`missed_line_items` reports them separately.
    """
    in_split = canonical["split"] == split
    frame = canonical.loc[in_split & ~missed_line_item_mask(canonical)].copy()
    if frame.empty:
        raise ValueError(f"dataset contains no rows for split {split!r}")
    frame["is_correct"] = frame["is_correct"].astype(int)
    return frame


def missed_line_item_mask(canonical: pd.DataFrame) -> pd.Series:
    """True for rows of line items that appear in ground truth but that the
    extraction never returned.

    Uses the ``line_item_status`` column from
    :func:`matching.pair_with_ground_truth` when it is present. Otherwise a line
    item (a row with an ``item_index``) counts as missed when none of its
    properties has an extracted value or a confidence score, because the
    extraction always attaches a confidence to the items it does return.
    """
    mask = pd.Series(False, index=canonical.index)
    if "line_item_status" in canonical.columns:
        return canonical["line_item_status"].eq("missed").fillna(False).astype(bool)
    if "item_index" not in canonical.columns:
        return mask
    listed = canonical["item_index"].notna()
    if not listed.any():
        return mask
    rows = canonical.loc[listed]
    returned = rows["extracted_value"].map(lambda value: not _is_null(value)) | pd.to_numeric(
        rows["confidence"], errors="coerce"
    ).notna()
    group = rows["field_name"].astype(str).str.partition(".")[0]
    any_returned = returned.groupby(
        [rows["document_id"], group, rows["item_index"]]
    ).transform("any")
    mask.loc[listed] = ~any_returned.astype(bool)
    return mask


def missed_line_items(canonical: pd.DataFrame, *, split: str = "test") -> dict[str, int]:
    """Count the line items in one split that the extraction never returned.

    These are real extraction mistakes that value-level routing cannot catch,
    because there is no extracted value to route. Catch them with a
    document-level check instead, for example comparing the sum of item prices
    with the subtotal, or the item count with the ground truth.
    """
    rows = canonical.loc[(canonical["split"] == split) & missed_line_item_mask(canonical)]
    group = rows["field_name"].astype(str).str.partition(".")[0]
    items = rows.groupby([rows["document_id"], group, rows["item_index"]]).ngroups if len(rows) else 0
    return {
        "items": int(items),
        "values": int(len(rows)),
        "mistakes": int((~rows["is_correct"].astype(bool)).sum()),
        "documents": int(rows["document_id"].nunique()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — measure the signal (target-independent, run once)
# ─────────────────────────────────────────────────────────────────────────────


def fit_base_policies(
    canonical: pd.DataFrame,
    *,
    split: str = "train",
    score_mode: str = "raw_confidence",
    n_bootstrap: int = 2000,
    random_state: int = 42,
) -> dict[str, dict]:
    """Measure each field's confidence signal once, on the training split.

    This is the expensive step: per field it runs grouped cross-validation,
    bootstraps a confidence interval on AUC, and sweeps every candidate cutoff.
    The result caches all of that, so re-deciding the policy at a different
    coverage target afterwards is nearly free.

    ``score_mode='raw_confidence'`` thresholds CU confidence directly.
    ``score_mode='logistic'`` first maps confidence to ``P(correct)`` with a
    one-dimensional logistic regression. With confidence as the only predictor
    the two rank observations identically, so every metric and every routing
    decision matches -- only the units of the exported cutoff differ. The
    logistic form is what you extend when you gain a second predictor.
    """
    frame = calibration_input(canonical, split=split)
    return build_routing_policies(
        frame,
        config=CalibrationConfig(
            n_bootstrap=n_bootstrap,
            random_state=random_state,
            group_col="document_id",
            min_auc_ci_lower=MIN_AUC_CI_LOWER,
            score_mode=score_mode,
        ),
    )


def signal_frame(base_policies: Mapping[str, Mapping]) -> pd.DataFrame:
    """Per-field summary of what the signal measurement found, before any
    business target is applied."""
    rows: list[dict[str, Any]] = []
    for field_name in sorted(base_policies):
        policy = base_policies[field_name]
        null_policy = policy["null_policy"]
        n_nulls = int(null_policy["n_nulls"])
        rows.append(
            {
                "field_name": field_name,
                "n_filled": int(policy["n"]),
                "n_filled_errors": int(policy["n_errors"]),
                "auc": policy.get("auc"),
                "auc_ci_lower": policy.get("auc_ci_lower"),
                "auc_ci_upper": policy.get("auc_ci_upper"),
                "confidence_is_usable": (
                    policy.get("auc_ci_lower") is not None
                    and policy["auc_ci_lower"] >= MIN_AUC_CI_LOWER
                ),
                "n_blank": n_nulls,
                "blank_precision": null_policy["null_precision"],
                "blank_ci_lower": null_policy["ci_lower"],
                "blank_ci_upper": null_policy["ci_upper"],
            }
        )
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — turn the business dial
# ─────────────────────────────────────────────────────────────────────────────


def select_policies(
    base_policies: Mapping[str, Mapping],
    target: float | Mapping[str, float],
) -> dict[str, dict]:
    """Pick each field's cutoff from one business target.

    ``target`` is the minimum share of known extraction mistakes that human
    review must catch. Per field, the lab picks the cutoff that meets that
    floor with the least review possible. The same number is used as the
    precision floor the blank track must clear before blanks are auto-approved.
    Pass a mapping to override the target for individual fields.
    """
    if isinstance(target, Mapping):
        missing = sorted(set(base_policies) - set(target))
        if missing:
            raise KeyError(f"missing targets for fields: {missing}")
        targets = target
    else:
        targets = {field: float(target) for field in base_policies}
    return {
        field: redecide_policy(
            policy,
            config=replace(
                CalibrationConfig(min_auc_ci_lower=MIN_AUC_CI_LOWER),
                target_catch_rate=float(targets[field]),
                min_null_precision=float(targets[field]),
            ),
        )
        for field, policy in base_policies.items()
    }


def savings_attribution(
    policies: Mapping[str, Mapping],
    calibration_frame: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """Split the expected review savings into its blank-track and filled-track
    contributions, per field and for the portfolio."""
    savings = estimate_hitl_savings(calibration_frame, policies)
    return savings["per_field"], savings["portfolio"]


def savings_sweep(
    base_policies: Mapping[str, Mapping],
    calibration_frame: pd.DataFrame,
    *,
    start: float = 0.50,
    end: float = 0.99,
    step: float = 0.01,
) -> pd.DataFrame:
    """Expected savings composition across the whole range of coverage targets.
    Reuses the cached signal, so no model is refit."""
    return sweep_target_savings(
        calibration_frame,
        base_policies,
        start=start,
        end=end,
        step=step,
        base_config=CalibrationConfig(min_auc_ci_lower=MIN_AUC_CI_LOWER),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — ship the calibration table
# ─────────────────────────────────────────────────────────────────────────────

# The deployment artifact: everything ``route_frame`` needs, plus the targets
# it was calibrated to and the wording that explains each decision.
CALIBRATION_TABLE_COLUMNS = (
    "field_name",
    "filled_decision",
    "cutoff",
    "score_mode",
    "lr_coef",
    "lr_intercept",
    "blank_decision",
    "target_catch_rate",
    "min_null_precision",
    "calibrated_at",
    "why",
)

# The subset routing actually reads.
_ROUTING_COLUMNS = (
    "field_name",
    "filled_decision",
    "cutoff",
    "score_mode",
    "lr_coef",
    "lr_intercept",
    "blank_decision",
)


def calibration_table(policies: Mapping[str, Mapping]) -> pd.DataFrame:
    """One row per field, carrying the whole routing policy.

    This is the deliverable: hand this table to inference and nothing else --
    no labeled data, no fitted model. In ``logistic`` score mode the fitted
    curve travels as ``lr_coef``/``lr_intercept`` and ``cutoff`` is a
    probability rather than a raw confidence.
    """
    stamped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows: list[dict[str, Any]] = []
    for field_name in sorted(policies):
        policy = policies[field_name]
        calibrated = policy.get("decision") == "calibrate"
        rows.append(
            {
                "field_name": field_name,
                "filled_decision": policy.get("decision"),
                "cutoff": policy.get("threshold") if calibrated else None,
                "score_mode": policy.get("score_mode"),
                "lr_coef": policy.get("lr_coef") if calibrated else None,
                "lr_intercept": policy.get("lr_intercept") if calibrated else None,
                "blank_decision": policy["null_policy"]["decision"],
                "target_catch_rate": policy.get("target_catch_rate"),
                "min_null_precision": policy["null_policy"].get("min_null_precision"),
                "calibrated_at": stamped_at,
                "why": policy.get("reason"),
            }
        )
    return pd.DataFrame(rows, columns=list(CALIBRATION_TABLE_COLUMNS))


def save_calibration_table(policies: Mapping[str, Mapping], path: str | Path) -> Path:
    """Write the routing policy to CSV. This file is what production loads."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    calibration_table(policies).to_csv(out, index=False)
    return out


def load_calibration_table(path: str | Path) -> dict[str, dict]:
    """Read a saved table back into policies ``route_frame`` can apply."""
    frame = pd.read_csv(path)
    missing = [c for c in _ROUTING_COLUMNS if c not in frame.columns]
    if missing:
        raise KeyError(f"calibration table is missing required columns: {missing}")

    policies: dict[str, dict] = {}
    for row in frame.to_dict(orient="records"):
        policies[row["field_name"]] = {
            "field_name": row["field_name"],
            "decision": row["filled_decision"],
            "threshold": None if _is_null(row["cutoff"]) else float(row["cutoff"]),
            "score_mode": row["score_mode"],
            "lr_coef": None if _is_null(row["lr_coef"]) else float(row["lr_coef"]),
            "lr_intercept": (
                None if _is_null(row["lr_intercept"]) else float(row["lr_intercept"])
            ),
            "null_policy": {"decision": row["blank_decision"]},
        }
    return policies


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — apply the frozen policy to unseen documents
# ─────────────────────────────────────────────────────────────────────────────


def route_frame(
    canonical: pd.DataFrame,
    policies: Mapping[str, Mapping],
    *,
    split: str,
) -> pd.DataFrame:
    """Run one split through the frozen policy, row by row, using the same
    formula production inference would use."""
    frame = calibration_input(canonical, split=split)
    routed: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        policy = policies.get(row["field_name"])
        route_to_hitl = True
        reason = "unknown_field"
        p_correct = None
        if policy is not None:
            if _is_null(row["extracted_value"]):
                route_to_hitl = policy["null_policy"]["decision"] != "null_to_stp"
                reason = "null_policy_review" if route_to_hitl else "null_policy_stp"
            elif _is_null(row["confidence"]):
                # A value CU returned no confidence for contributed no evidence
                # to this field's policy, so no policy can vouch for it.
                reason = "missing_confidence"
            elif policy.get("decision") == "always_trust":
                route_to_hitl = False
                reason = "always_trust"
            elif policy.get("decision") == "calibrate":
                if policy.get("score_mode") == "raw_confidence":
                    route_to_hitl = float(row["confidence"]) < float(policy["threshold"])
                    reason = (
                        "raw_below_threshold" if route_to_hitl else "raw_above_threshold"
                    )
                else:
                    p_correct = _sigmoid(
                        float(policy["lr_coef"]) * float(row["confidence"])
                        + float(policy["lr_intercept"])
                    )
                    route_to_hitl = p_correct < float(policy["threshold"])
                    reason = (
                        "lr_below_threshold" if route_to_hitl else "lr_above_threshold"
                    )
            else:
                reason = "non_null_uncalibrated"
        is_correct = bool(row["is_correct"])
        routed.append(
            {
                **row,
                "p_correct": p_correct,
                "route_to_hitl": route_to_hitl,
                "route_reason": reason,
                "stp_error": (not is_correct) and not route_to_hitl,
                "error_intercepted": (not is_correct) and route_to_hitl,
            }
        )
    return pd.DataFrame(routed)


def held_out_metrics(routed: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Measured per-field and portfolio outcomes for an already-routed split."""
    rows: list[dict[str, Any]] = []
    for field_name, source in routed.groupby("field_name", sort=True):
        n = len(source)
        stp = int((~source["route_to_hitl"]).sum())
        errors = int((~source["is_correct"].astype(bool)).sum())
        stp_errors = int(source["stp_error"].sum())
        intercepted = int(source["error_intercepted"].sum())
        rows.append(
            {
                "field_name": field_name,
                "n_observations": n,
                "auto_approved": stp,
                "auto_approve_rate": stp / n if n else np.nan,
                "mistakes_slipped_through": stp_errors,
                "stp_error_rate": stp_errors / stp if stp else np.nan,
                "total_mistakes": errors,
                "mistakes_caught": intercepted,
                "catch_rate": intercepted / errors if errors else np.nan,
            }
        )
    per_field = pd.DataFrame(rows)
    return per_field, portfolio_metrics(per_field)


def portfolio_metrics(per_field: pd.DataFrame) -> dict[str, float | int]:
    """Roll a per-field outcome table up to a single portfolio view."""
    total = int(per_field["n_observations"].sum())
    stp = int(per_field["auto_approved"].sum())
    stp_errors = int(per_field["mistakes_slipped_through"].sum())
    total_errors = int(per_field["total_mistakes"].sum())
    intercepted = int(per_field["mistakes_caught"].sum())
    return {
        "field_values": total,
        "auto_approved": stp,
        "auto_approve_rate": stp / total if total else math.nan,
        "review_rate": 1.0 - stp / total if total else math.nan,
        "mistakes_slipped_through": stp_errors,
        "stp_error_rate": stp_errors / stp if stp else math.nan,
        "total_mistakes": total_errors,
        "mistakes_caught": intercepted,
        "catch_rate": intercepted / total_errors if total_errors else math.nan,
    }


def coverage_tracking(
    base_policies: Mapping[str, Mapping],
    canonical: pd.DataFrame,
    *,
    split: str = "test",
    start: float = 0.50,
    end: float = 0.99,
    step: float = 0.01,
) -> pd.DataFrame:
    """Ask for each coverage target in turn and measure what was actually
    delivered on an unseen split -- the "does the dial behave like a dial" test.

    ``calibrated_catch`` isolates the fields whose routing came from a fitted
    confidence cutoff, and is the figure the target actually governs. The
    overall figure mixes in fully reviewed fields, which push it up, and
    auto-approved blanks, which push it down.
    """
    rows: list[dict[str, Any]] = []
    for target in target_range(start, end, step):
        routed = route_frame(canonical, select_policies(base_policies, target), split=split)
        to_hitl = routed["route_to_hitl"].astype(bool)
        incorrect = ~routed["is_correct"].astype(bool)
        thresholded = routed["route_reason"].isin(THRESHOLD_ROUTE_REASONS)
        total_errors = int(incorrect.sum())
        thresholded_errors = int((incorrect & thresholded).sum())
        stp_n = int((~to_hitl).sum())
        rows.append(
            {
                "target": target,
                "overall_catch": (
                    int((incorrect & to_hitl).sum()) / total_errors
                    if total_errors
                    else np.nan
                ),
                "calibrated_catch": (
                    int((incorrect & thresholded & to_hitl).sum()) / thresholded_errors
                    if thresholded_errors
                    else np.nan
                ),
                "overall_stp_rate": stp_n / len(routed) if len(routed) else np.nan,
                "stp_error_rate": (
                    int((incorrect & ~to_hitl).sum()) / stp_n if stp_n else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


def naive_threshold_sweep(
    canonical: pd.DataFrame,
    *,
    split: str = "test",
    step: float = 0.005,
) -> pd.DataFrame:
    """The strawman: one global confidence cutoff applied to every field,
    swept across its whole range so it can be compared on identical data."""
    frame = calibration_input(canonical, split=split)
    confidence = pd.to_numeric(frame["confidence"], errors="coerce").to_numpy(dtype=float)
    incorrect = ~frame["is_correct"].to_numpy(dtype=bool)
    total_errors = int(incorrect.sum())
    n = len(frame)

    rows: list[dict[str, Any]] = []
    for threshold in np.arange(0.0, 1.0 + step / 2, step):
        # A missing confidence goes to review, matching the policy's fallback.
        auto = np.where(np.isnan(confidence), False, confidence >= threshold)
        n_auto = int(auto.sum())
        rows.append(
            {
                "threshold": float(threshold),
                "stp_rate": n_auto / n,
                "catch": (
                    int((incorrect & ~auto).sum()) / total_errors
                    if total_errors
                    else np.nan
                ),
                "stp_error_rate": (
                    int((incorrect & auto).sum()) / n_auto if n_auto else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def target_range(start: float, end: float, step: float) -> list[float]:
    """Inclusive list of coverage targets from ``start`` to ``end``."""
    if step <= 0:
        raise ValueError("step must be > 0")
    n_steps = int(round((end - start) / step)) + 1
    return [
        round(start + index * step, 10)
        for index in range(n_steps)
        if start + index * step <= end + 1e-9
    ]


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)
