"""Per-field HITL/STP routing-policy calibration.

Two-track routing per field:
  * **Null track** — Wilson 95% CI on P(GT null | extracted null). When the
    lower bound clears the null target the policy routes nulls to STP;
    otherwise nulls go to HITL.
  * **Non-null track** — confidence ranked directly, or mapped through a
    Platt-style 1-D logistic regression, then gated on a 95% bootstrap CI on
    AUC and cut at the threshold that meets the requested catch target.

One business number drives it: ``target_catch_rate``, the minimum share of
known extraction errors human review must intercept.

This is the engine. :mod:`calibration` is the API you call.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import (
    StratifiedGroupKFold,
    StratifiedKFold,
    cross_val_predict,
)
from statsmodels.stats.proportion import proportion_confint


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _is_null_value(v) -> bool:
    """True when a value counts as "nothing was extracted": None, NaN, or a
    string that is empty or whitespace. Kept in step with ``matching.is_null``,
    so the module that labels and the module that routes agree."""
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str):
        return not v.strip()
    return False


def _wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score CI for a binomial proportion via
    :func:`statsmodels.stats.proportion.proportion_confint` with
    ``method='wilson'``. Returns ``(0.0, 1.0)`` when ``n == 0``."""
    if n == 0:
        return (0.0, 1.0)
    lo, hi = proportion_confint(count=k, nobs=n, alpha=alpha, method="wilson")
    return (float(lo), float(hi))


# ─────────────────────────────────────────────────────────────────────────────
# Config + result objects
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CalibrationConfig:
    """Knobs for the non-null LR track and the null track."""

    target_catch_rate: float = 0.80
    """The minimum fraction of known non-null extraction errors that human
    review must intercept.

    This is a floor on the *calibrated* track, measured on the rows the
    threshold was chosen from. It is not a portfolio-wide guarantee, and it
    says nothing about how often an auto-approved value is wrong.
    """

    min_null_precision: float = 0.80
    """Null: Wilson-CI lower-bound bar that null precision must clear before
    nulls are routed to STP."""

    min_auc_ci_lower: float = 0.50
    """Non-null: AUC 95% CI lower bound required before a threshold is fit.

    The most consequential knob here. 0.50 asks only that the whole interval
    beat a coin flip; raising it a few hundredths can disqualify every field on
    a dataset whose confidence carries weak signal. Fields whose lower bound
    sits near the bar can also change side with ``random_state``, so treat
    borderline qualification as provisional.
    """

    min_samples: int = 20
    """Minimum non-null rows before we'll attempt to fit the LR."""

    min_errors_for_cv: int = 5
    """Minimum non-null mis-extractions required for the 5-fold CV."""

    min_nulls: int = 10
    """Minimum null extractions required before the null track may route to
    STP. Below this, nulls always go to HITL."""

    n_splits: int = 5
    n_bootstrap: int = 2000
    random_state: int = 42

    group_col: str | None = None
    """Optional document/group column for leakage-safe fold splits and
    cluster-bootstrap AUC confidence intervals. Set this to ``"document_id"``
    for datasets containing repeated observations from the same document, such
    as receipt line items.
    """

    score_mode: Literal["logistic", "raw_confidence"] = "logistic"
    """Which score the non-null threshold sweep ranks observations by.

    * ``"logistic"`` (default) — Platt-style logistic regression on raw
      confidence. Leaves room for additional predictors of correctness later.
    * ``"raw_confidence"`` — rank by raw ACU confidence directly, and deploy a
      confidence cutoff instead of model coefficients.

    While confidence is the only predictor these two are strictly monotone
    transforms of one another, so they produce the *same* ranking, AUC,
    threshold sweep and routing decisions; only the units of the exported
    threshold differ. The modes can only diverge once a second predictor is
    added, at which point the logistic score stops being a function of
    confidence alone.
    """

    def __post_init__(self) -> None:
        if self.score_mode not in ("logistic", "raw_confidence"):
            raise ValueError(
                "score_mode must be 'logistic' or 'raw_confidence', got "
                f"{self.score_mode!r}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Per-field policy
# ─────────────────────────────────────────────────────────────────────────────


def build_routing_policy(
    df_full: pd.DataFrame,
    field_name: str,
    *,
    config: CalibrationConfig | None = None,
) -> dict:
    """Build a two-track routing policy for one field.

    Parameters
    ----------
    df_full : DataFrame with both null and non-null rows. Must include
        ``field_name``, ``confidence``, ``is_correct``, ``extracted_value``.
        Don't pre-filter nulls — the function splits them internally.
    field_name : friendly field key to build a policy for.
    config : tunable knobs; defaults to the values used in the notebook.

    Returns
    -------
    dict with keys (subset shown — see source for full list):
        decision               : 'calibrate' | 'always_review' | 'always_trust'
                                 | 'insufficient_data'
        reason                 : human-readable explanation
        threshold              : LR P(correct) cutoff (only for 'calibrate')
        model                  : fitted sklearn LogisticRegression (only for
                                 'calibrate')
        lr_coef, lr_intercept  : convenience copies of the LR parameters
        auc, auc_ci_lower,     : OOF AUC + 95% bootstrap CI
            auc_ci_upper
        confusion_matrix       : OOF CM on non-null rows
        achieved_catch_rate : errors intercepted by review (mis-extraction recall)
        hitl_load            : human-review rate
        stp_miss_rate        : observed error rate among auto-passed values
        null_policy            : sub-dict with keys
            decision ∈ {'null_to_stp', 'null_to_hitl',
                        'no_nulls_observed', 'insufficient_nulls'},
            null_precision, ci_lower, ci_upper, n_nulls, n_nulls_gt_null,
            min_null_precision, min_nulls, reason.

    The returned dict also carries a private ``_cache`` entry holding the
    pre-decision per-field signal (Wilson CI, OOF probs, AUC bootstrap,
    threshold sweep). :func:`redecide_policy` consumes that cache to derive
    new policies for different ``target_catch_rate`` /
    ``min_null_precision`` values without re-running the LR fit or
    bootstrap.
    """
    cfg = config or CalibrationConfig()
    signal = _compute_field_signal(df_full, field_name, cfg)
    return _apply_policy_decisions(signal, cfg)


def _compute_field_signal(
    df_full: pd.DataFrame,
    field_name: str,
    cfg: CalibrationConfig,
) -> dict:
    """Run all per-field heavy computation (Wilson CI, LR fit, OOF probs,
    AUC + bootstrap CI, threshold sweep). Output is *target-independent* —
    it does not apply the ``target_catch_rate`` or ``min_null_precision``
    gates. :func:`_apply_policy_decisions` consumes this signal to emit the
    policy dict; :func:`redecide_policy` reuses it to cheaply re-derive
    policies at different targets.
    """
    required = {"field_name", "confidence", "is_correct", "extracted_value"}
    missing = required - set(df_full.columns)
    if missing:
        raise KeyError(f"df_full is missing required columns: {sorted(missing)}")

    sub = df_full[df_full["field_name"] == field_name].copy()
    is_null = sub["extracted_value"].apply(_is_null_value).to_numpy()
    no_confidence = sub["confidence"].apply(_is_null_value).to_numpy()
    sub_null = sub.loc[is_null]
    # Same test the router uses to emit `missing_confidence`, so the threshold is
    # measured on exactly the population it will later be applied to.
    sub_nonnull = sub.loc[~is_null & ~no_confidence]

    # ── Null track (Wilson 95% CI on null precision) ─────────────────────────
    n_nulls = int(len(sub_null))
    n_nulls_gt_null = int(sub_null["is_correct"].sum()) if n_nulls else 0
    if n_nulls > 0:
        p_hat = n_nulls_gt_null / n_nulls
        lo, hi = _wilson_ci(n_nulls_gt_null, n_nulls, alpha=0.05)
        null_precision: float | None = float(p_hat)
        null_ci_lower: float | None = float(lo)
        null_ci_upper: float | None = float(hi)
    else:
        null_precision = null_ci_lower = null_ci_upper = None

    # ── Non-null track ───────────────────────────────────────────────────────
    X = sub_nonnull[["confidence"]].to_numpy()
    y = sub_nonnull["is_correct"].to_numpy().astype(int)
    n = len(y)
    n_errors = int((y == 0).sum())
    n_correct = int((y == 1).sum())

    signal: dict = {
        "field_name": field_name,
        "score_mode": cfg.score_mode,
        "n_nulls": n_nulls,
        "n_nulls_gt_null": n_nulls_gt_null,
        "null_precision": null_precision,
        "null_ci_lower": null_ci_lower,
        "null_ci_upper": null_ci_upper,
        "n": n,
        "n_errors": n_errors,
        "n_correct": n_correct,
        # Populated only if LR fit ran:
        "model": None,
        "oof_y": None,
        "oof_probs": None,
        "auc": None,
        "auc_ci_lower": None,
        "auc_ci_upper": None,
        "sweep": None,
        "bootstrap_degenerate": False,
        # Whether we even attempted the LR fit, and why we stopped if not:
        "lr_skip_reason": None,
    }

    if n < cfg.min_samples:
        signal["lr_skip_reason"] = (
            f"n={n} non-null rows below min_samples={cfg.min_samples}"
        )
        return signal
    if n_errors == 0:
        signal["lr_skip_reason"] = "no errors observed in non-null extractions"
        return signal
    if n_correct == 0:
        signal["lr_skip_reason"] = "no correct non-null extractions observed"
        return signal
    if n_errors < cfg.min_errors_for_cv:
        signal["lr_skip_reason"] = (
            f"only {n_errors} errors — too few for {cfg.n_splits}-fold CV"
        )
        return signal

    # Fit + score. In raw_confidence mode the scorer is the identity, so nothing
    # is fit and a row's score is its own confidence.
    raw_mode = cfg.score_mode == "raw_confidence"
    model = None
    if not raw_mode:
        model = LogisticRegression(random_state=cfg.random_state)
        model.fit(X, y)

    def _global_scores() -> np.ndarray:
        return X[:, 0].astype(float) if raw_mode else model.predict_proba(X)[:, 1]

    # With a single predictor the score is a strictly monotone function of
    # confidence, so the ranking -- and with it the AUC and the entire threshold
    # sweep -- cannot depend on the fitted parameters, and fitting introduces no
    # optimism into them. Pooling probabilities from five different fold models
    # would only reorder rows by fold membership, which is noise. Add a second
    # predictor and the weights do drive the ranking, so out-of-fold scoring
    # becomes necessary again.
    rank_globally = X.shape[1] == 1

    groups: np.ndarray | None = None
    if cfg.group_col is not None:
        if cfg.group_col not in sub_nonnull.columns:
            raise KeyError(
                f"group_col {cfg.group_col!r} is missing from the calibration data"
            )
        groups = sub_nonnull[cfg.group_col].to_numpy()
        if pd.isna(groups).any():
            raise ValueError(f"group_col {cfg.group_col!r} contains null values")
        if len(np.unique(groups)) < cfg.n_splits:
            signal["lr_skip_reason"] = (
                f"only {len(np.unique(groups))} unique groups — too few for "
                f"{cfg.n_splits}-fold grouped CV"
            )
            return signal

    if groups is None:
        if rank_globally:
            oof_probs = _global_scores()
        else:
            cv = StratifiedKFold(
                n_splits=cfg.n_splits, shuffle=True, random_state=cfg.random_state
            )
            oof_probs = cross_val_predict(
                model, X, y, cv=cv, method="predict_proba"
            )[:, 1]
    else:
        cv = StratifiedGroupKFold(
            n_splits=cfg.n_splits, shuffle=True, random_state=cfg.random_state
        )
        oof_probs = np.full(n, np.nan, dtype=float)
        try:
            splits = cv.split(X, y, groups)
            for train_idx, test_idx in splits:
                # The fold walk runs in every mode: it is the viability gate that
                # decides whether a field qualifies for a threshold at all.
                if len(np.unique(y[train_idx])) < 2:
                    signal["lr_skip_reason"] = (
                        "a grouped CV training fold contains only one class"
                    )
                    return signal
                if rank_globally:
                    continue
                fold_model = LogisticRegression(random_state=cfg.random_state)
                fold_model.fit(X[train_idx], y[train_idx])
                oof_probs[test_idx] = fold_model.predict_proba(X[test_idx])[:, 1]
        except ValueError as exc:
            signal["lr_skip_reason"] = f"grouped CV unavailable: {exc}"
            return signal
        if rank_globally:
            oof_probs = _global_scores()
        elif np.isnan(oof_probs).any():
            signal["lr_skip_reason"] = "grouped CV did not predict every row"
            return signal

    # AUC + bootstrap CI on OOF probs
    rng = np.random.default_rng(cfg.random_state)
    boot_aucs: list[float] = []
    unique_groups = np.unique(groups) if groups is not None else None
    group_indices = (
        [np.flatnonzero(groups == group) for group in unique_groups]
        if unique_groups is not None
        else None
    )
    for _ in range(cfg.n_bootstrap):
        if unique_groups is None:
            idx = rng.integers(0, n, size=n)
        else:
            sampled_group_indices = rng.integers(
                0,
                len(unique_groups),
                size=len(unique_groups),
            )
            idx = np.concatenate(
                [group_indices[index] for index in sampled_group_indices]
            )
        if len(np.unique(y[idx])) < 2:
            continue
        boot_aucs.append(roc_auc_score(y[idx], oof_probs[idx]))
    auc = float(roc_auc_score(y, oof_probs))
    signal.update(model=model, oof_y=y, oof_probs=oof_probs, auc=auc)

    if len(boot_aucs) < 0.5 * cfg.n_bootstrap:
        signal["bootstrap_degenerate"] = True
        return signal

    ci_lo = float(np.percentile(boot_aucs, 2.5))
    ci_hi = float(np.percentile(boot_aucs, 97.5))
    signal.update(auc_ci_lower=ci_lo, auc_ci_upper=ci_hi)

    # Sweep OOF thresholds — target-independent; downstream picks the
    # lowest-HITL row whose `catch` clears the requested target.
    cands = np.sort(np.unique(oof_probs))
    cands = np.unique(np.concatenate([cands, cands + 1e-9]))
    rows = []
    for t in cands:
        preds = (oof_probs >= t).astype(int)  # 1 = STP, 0 = HITL
        tp = int(((preds == 1) & (y == 1)).sum())
        fp = int(((preds == 1) & (y == 0)).sum())
        tn = int(((preds == 0) & (y == 0)).sum())
        fn = int(((preds == 0) & (y == 1)).sum())
        rows.append((t, tn, fp, fn, tp))
    sweep = pd.DataFrame(rows, columns=["t", "tn", "fp", "fn", "tp"])
    sweep["catch"] = sweep["tn"] / n_errors
    sweep["hitl_load"] = (sweep["tn"] + sweep["fn"]) / n
    sweep["stp_n"] = sweep["tp"] + sweep["fp"]
    sweep["stp_errors"] = sweep["fp"]
    sweep["stp_rate"] = sweep["stp_n"] / n
    sweep["stp_error_rate"] = np.where(
        sweep["stp_n"] > 0,
        sweep["stp_errors"] / sweep["stp_n"],
        np.nan,
    )
    sweep["stp_error_ci_lower"] = np.nan
    sweep["stp_error_ci_upper"] = np.nan
    has_stp = sweep["stp_n"] > 0
    if has_stp.any():
        lo, hi = proportion_confint(
            count=sweep.loc[has_stp, "stp_errors"].to_numpy(dtype=int),
            nobs=sweep.loc[has_stp, "stp_n"].to_numpy(dtype=int),
            alpha=0.05,
            method="wilson",
        )
        sweep.loc[has_stp, "stp_error_ci_lower"] = lo
        sweep.loc[has_stp, "stp_error_ci_upper"] = hi
    signal["sweep"] = sweep
    return signal


def _build_null_policy(signal: dict, cfg: CalibrationConfig) -> dict:
    """Build the ``null_policy`` sub-dict from cached signal + current cfg."""
    n_nulls = signal["n_nulls"]
    n_nulls_gt_null = signal["n_nulls_gt_null"]
    null_policy: dict = {
        "min_null_precision": cfg.min_null_precision,
        "min_nulls": cfg.min_nulls,
        "n_nulls": n_nulls,
        "n_nulls_gt_null": n_nulls_gt_null,
        "null_precision": signal["null_precision"],
        "ci_lower": signal["null_ci_lower"],
        "ci_upper": signal["null_ci_upper"],
        "decision": None,
        "reason": "",
    }
    if n_nulls == 0:
        null_policy.update(
            decision="no_nulls_observed",
            reason="no null extractions in labeled data (route nulls to HITL)",
        )
        return null_policy
    p_hat = signal["null_precision"]
    lo = signal["null_ci_lower"]
    hi = signal["null_ci_upper"]
    if n_nulls < cfg.min_nulls:
        null_policy.update(
            decision="insufficient_nulls",
            reason=(
                f"only {n_nulls} null extractions observed "
                f"(< min_nulls={cfg.min_nulls}), so route nulls to HITL"
            ),
        )
    elif lo >= cfg.min_null_precision:
        null_policy.update(
            decision="null_to_stp",
            reason=(
                f"null precision {p_hat:.1%} "
                f"[95% CI {lo:.1%}–{hi:.1%}] clears "
                f"{cfg.min_null_precision:.0%} bar (STP)"
            ),
        )
    else:
        null_policy.update(
            decision="null_to_hitl",
            reason=(
                f"null precision {p_hat:.1%} "
                f"[95% CI {lo:.1%}–{hi:.1%}] below "
                f"{cfg.min_null_precision:.0%} bar (HITL)"
            ),
        )
    return null_policy


def _apply_policy_decisions(signal: dict, cfg: CalibrationConfig) -> dict:
    """Cheap: derive a policy dict from a precomputed field signal + cfg.
    No LR fit, no bootstrap — just gates and threshold pick."""
    null_policy = _build_null_policy(signal, cfg)

    base: dict = {
        "field_name": signal["field_name"],
        "score_mode": signal.get("score_mode", "logistic"),
        "n": signal["n"],
        "n_errors": signal["n_errors"],
        "target_catch_rate": cfg.target_catch_rate,
        "decision": None,
        "reason": "",
        "threshold": None,
        "model": signal.get("model"),
        "lr_coef": None,
        "lr_intercept": None,
        "achieved_catch_rate": None,
        "hitl_load": None,
        "stp_miss_rate": None,
        "confusion_matrix": None,
        "auc": signal.get("auc"),
        "auc_ci_lower": signal.get("auc_ci_lower"),
        "auc_ci_upper": signal.get("auc_ci_upper"),
        "null_policy": null_policy,
        "_cache": signal,
    }

    skip_reason = signal.get("lr_skip_reason")
    if skip_reason is not None:
        if signal["n"] < cfg.min_samples:
            base.update(decision="insufficient_data", reason=skip_reason)
        elif signal["n_errors"] == 0:
            base.update(decision="always_trust", reason=skip_reason)
        else:
            base.update(decision="always_review", reason=skip_reason)
        return base

    if signal["bootstrap_degenerate"]:
        base.update(
            decision="always_review",
            reason="bootstrap degenerate — CI unreliable",
        )
        return base

    ci_lo = signal["auc_ci_lower"]
    if ci_lo < cfg.min_auc_ci_lower:
        base.update(
            decision="always_review",
            reason=(
                f"AUC CI lower {ci_lo:.3f} < {cfg.min_auc_ci_lower} — "
                "signal not trustworthy"
            ),
        )
        return base

    sweep: pd.DataFrame = signal["sweep"]
    n = signal["n"]
    n_errors = signal["n_errors"]
    hits = sweep[sweep["catch"] >= cfg.target_catch_rate]
    if hits.empty:
        base.update(
            decision="always_review",
            reason=(
                f"target catch {cfg.target_catch_rate:.0%} "
                "not achievable on OOF"
            ),
        )
        return base
    chosen = hits.loc[hits["hitl_load"].idxmin()]
    threshold = float(chosen["t"])
    tn, fp, fn, tp = (
        int(chosen["tn"]),
        int(chosen["fp"]),
        int(chosen["fn"]),
        int(chosen["tp"]),
    )
    cm = np.array([[tn, fp], [fn, tp]])
    achieved_catch = tn / n_errors
    hitl_load = (tn + fn) / n
    stp_miss = fp / (tp + fp) if (tp + fp) else float("nan")
    model = signal["model"]

    base.update(
        decision="calibrate",
        reason=(
            f"target catch {cfg.target_catch_rate:.0%} met at "
            f"threshold {threshold:.4f}"
        ),
        threshold=threshold,
        lr_coef=float(model.coef_[0, 0]) if model is not None else None,
        lr_intercept=float(model.intercept_[0]) if model is not None else None,
        achieved_catch_rate=float(achieved_catch),
        hitl_load=float(hitl_load),
        stp_miss_rate=float(stp_miss) if not np.isnan(stp_miss) else None,
        confusion_matrix=cm,
    )
    return base


def redecide_policy(policy: Mapping, *, config: CalibrationConfig) -> dict:
    """Re-derive a policy at a new ``config`` using the cached field signal,
    skipping the LR fit and AUC bootstrap.

    The input ``policy`` must have been produced by :func:`build_routing_policy`
    (which attaches a ``_cache`` entry holding the per-field signal).
    """
    cache = policy.get("_cache")
    if cache is None:
        raise ValueError(
            "policy is missing its _cache — was it built with the current "
            "version of build_routing_policy?"
        )
    return _apply_policy_decisions(cache, config)


def redecide_policies(
    policies: Mapping[str, Mapping],
    *,
    config: CalibrationConfig,
) -> dict[str, dict]:
    """Vector form of :func:`redecide_policy` over a ``{field: policy}``
    mapping."""
    return {f: redecide_policy(p, config=config) for f, p in policies.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio rollup
# ─────────────────────────────────────────────────────────────────────────────


# Null-policy decisions that send nulls to HITL (i.e. NOT routed to STP).
_NULL_TO_HITL_DECISIONS = frozenset(
    {"null_to_hitl", "no_nulls_observed", "insufficient_nulls"}
)


def build_routing_policies(
    df_full: pd.DataFrame,
    fields: Iterable[str] | None = None,
    *,
    config: CalibrationConfig | None = None,
) -> dict[str, dict]:
    """Convenience: run :func:`build_routing_policy` for every field and
    return the mapping ``{field_name: policy_dict}`` consumed by the
    plotting functions below.

    Parameters
    ----------
    df_full : the unfiltered comparison frame (same shape consumed by
        ``build_routing_policy``).
    fields : iterable of friendly field keys to include. Defaults to every
        unique value of ``df_full['field_name']``.
    config : ``CalibrationConfig`` knobs; defaults to
        ``CalibrationConfig()``.
    """
    cfg = config or CalibrationConfig()
    if fields is None:
        fields = sorted(df_full["field_name"].dropna().unique())
    return {f: build_routing_policy(df_full, f, config=cfg) for f in fields}


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio-level savings estimate
# ─────────────────────────────────────────────────────────────────────────────


def estimate_hitl_savings(
    df_full: pd.DataFrame,
    policies: Mapping[str, dict],
) -> dict:
    """Estimate the expected HITL load (and savings vs an all-HITL
    baseline) for the **entire form**, not just the calibrated fields.

    Every field present in ``df_full`` is bucketed and its expected HITL
    routings counted:

      * **calibrate**:       non-null HITL = ``hitl_load × n_scored``
                              (the policy's own estimate) plus every
                              unscored row; null HITL governed by the
                              null-policy.
      * **always_trust**:    non-null HITL = the unscored rows only; null
                              HITL governed by the null-policy.
      * everything else:     100% HITL (always_review,
                              insufficient_data, no_policy).

    A non-null row CU returned without a confidence score contributed no
    evidence to the field's policy, so :func:`calibration.route_frame` sends
    it to review as ``missing_confidence`` whatever the field decided. This
    forecast counts those rows as review for the same reason — crediting them
    would claim automation the router will never deliver.

    ``hitl_load`` comes from the threshold sweep in
    :func:`build_routing_policy`, which both fits and measures on the same
    rows. The number is therefore a forecast on the calibration set, not a
    held-out result — route an unseen split to measure what was delivered.

    Parameters
    ----------
    df_full : the unfiltered comparison frame used to fit the policies
        (must contain ``field_name``, ``extracted_value`` and
        ``confidence``). The row counts here define the field volume per
        form.
    policies : ``{field_name: policy_dict}`` from
        :func:`build_routing_policies`.

    Returns
    -------
    dict with keys:
        per_field : DataFrame, one row per field in ``df_full`` with
            columns: field, bucket, n_total, n_nonnull, n_unscored,
            n_nulls, null_savings, lr_savings, expected_hitl,
            baseline_hitl, hitl_savings_pct. ``null_savings + lr_savings +
            expected_hitl == baseline_hitl`` for every row.
        portfolio : dict with n_total, n_unscored, expected_hitl,
            baseline_hitl, null_savings, lr_savings, null_savings_pct,
            lr_savings_pct, hitl_load, hitl_savings_pct, plus per-bucket
            field counts. ``null_savings_pct + lr_savings_pct + hitl_load
            == 1.0``.
    """
    required = {"field_name", "extracted_value", "confidence"}
    missing = required - set(df_full.columns)
    if missing:
        raise KeyError(f"df_full is missing required columns: {sorted(missing)}")

    rows: list[dict] = []

    for field_name in sorted(df_full["field_name"].dropna().unique()):
        sub = df_full[df_full["field_name"] == field_name]
        is_null = sub["extracted_value"].apply(_is_null_value).to_numpy()
        no_confidence = sub["confidence"].apply(_is_null_value).to_numpy()
        n_total = int(len(sub))
        n_nulls = int(is_null.sum())
        n_nonnull = n_total - n_nulls
        n_unscored = int((~is_null & no_confidence).sum())
        n_scored = n_nonnull - n_unscored

        pol = policies.get(field_name)

        # Per-track savings: count of routings the policy diverts to STP
        # vs the all-HITL baseline. ``null_savings`` comes from the null
        # track, ``lr_savings`` comes from the non-null track.
        null_savings = 0
        lr_savings = 0

        if pol is None:
            bucket = "no_policy"
            expected_hitl = n_total
        else:
            decision = pol.get("decision")
            null_to_hitl = pol["null_policy"]["decision"] in _NULL_TO_HITL_DECISIONS
            null_hitl = n_nulls if null_to_hitl else 0
            null_savings = n_nulls - null_hitl  # nulls routed to STP
            if decision == "calibrate":
                bucket = "calibrate"
                # hitl_load is the OOF HITL fraction among *scored* non-null
                # rows; unscored rows are review whatever the cutoff says.
                scored_hitl = int(round(float(pol["hitl_load"]) * n_scored))
                lr_savings = n_scored - scored_hitl
                expected_hitl = scored_hitl + n_unscored + null_hitl
            elif decision == "always_trust":
                bucket = "always_trust"
                lr_savings = n_scored
                expected_hitl = n_unscored + null_hitl
            else:
                # always_review, insufficient_data, etc.: non-null values go to HITL.
                bucket = decision or "no_policy"
                expected_hitl = n_nonnull + null_hitl

        baseline_hitl = n_total
        savings_pct = (
            1.0 - expected_hitl / baseline_hitl if baseline_hitl else float("nan")
        )
        rows.append(
            {
                "field":            field_name,
                "bucket":           bucket,
                "n_total":          n_total,
                "n_nonnull":        n_nonnull,
                "n_unscored":       n_unscored,
                "n_nulls":          n_nulls,
                "null_savings":     int(null_savings),
                "lr_savings":       int(lr_savings),
                "expected_hitl":    int(expected_hitl),
                "baseline_hitl":    int(baseline_hitl),
                "hitl_savings_pct": float(savings_pct),
            }
        )

    per_field = pd.DataFrame(rows)

    total_baseline = int(per_field["baseline_hitl"].sum())
    total_expected = int(per_field["expected_hitl"].sum())
    total_null_savings = int(per_field["null_savings"].sum())
    total_lr_savings = int(per_field["lr_savings"].sum())
    portfolio_savings = (
        1.0 - total_expected / total_baseline if total_baseline else float("nan")
    )
    portfolio_hitl_load = (
        total_expected / total_baseline if total_baseline else float("nan")
    )

    bucket_counts = per_field["bucket"].value_counts().to_dict()
    portfolio = {
        "n_total":                total_baseline,
        "n_unscored":             int(per_field["n_unscored"].sum()),
        "expected_hitl":          total_expected,
        "baseline_hitl":          total_baseline,
        "null_savings":           total_null_savings,
        "lr_savings":             total_lr_savings,
        "null_savings_pct":       (
            total_null_savings / total_baseline if total_baseline else float("nan")
        ),
        "lr_savings_pct":         (
            total_lr_savings / total_baseline if total_baseline else float("nan")
        ),
        "hitl_load":              float(portfolio_hitl_load),
        "hitl_savings_pct":       float(portfolio_savings),
        "n_calibrated_fields":    int(bucket_counts.get("calibrate", 0)),
        "n_always_trust_fields":  int(bucket_counts.get("always_trust", 0)),
        "n_always_review_fields": int(bucket_counts.get("always_review", 0)),
        "n_no_policy_fields":     int(bucket_counts.get("no_policy", 0)),
    }

    return {"per_field": per_field, "portfolio": portfolio}


# ─────────────────────────────────────────────────────────────────────────────
# Coverage-target sweep
# ─────────────────────────────────────────────────────────────────────────────


def sweep_target_savings(
    df_full: pd.DataFrame,
    policies: Mapping[str, Mapping],
    *,
    start: float = 0.50,
    end: float = 0.95,
    step: float = 0.05,
    base_config: CalibrationConfig | None = None,
) -> pd.DataFrame:
    """Sweep the coverage target c from ``start`` to ``end`` (inclusive) in
    increments of ``step``, applying ``c`` to both ``target_catch_rate`` and
    ``min_null_precision`` at every step. Reuses the per-field signal cache
    attached to ``policies`` (built once by :func:`build_routing_policies`)
    so the LR fit and AUC bootstrap are not re-run.

    Returns one row per target with portfolio-level savings broken down
    into null-track and non-null (LR/always-trust) contributions.

    Columns
    -------
    target, hitl_load, hitl_savings_pct,
    null_savings_pct, lr_savings_pct,
    expected_hitl, baseline_hitl,
    null_savings, lr_savings,
    n_calibrated_fields,
    n_always_review_fields, n_always_trust_fields, n_no_policy_fields
    """
    if step <= 0:
        raise ValueError(f"step must be > 0, got {step}")
    if end < start:
        raise ValueError(f"end ({end}) must be >= start ({start})")
    base_cfg = base_config or CalibrationConfig()

    # Build target list inclusive of `end` (with float tolerance).
    n_steps = int(round((end - start) / step)) + 1
    targets = [round(start + i * step, 10) for i in range(n_steps)]
    targets = [t for t in targets if t <= end + 1e-9]

    rows = []
    for c in targets:
        cfg = replace(base_cfg, target_catch_rate=c, min_null_precision=c)
        new_policies = redecide_policies(policies, config=cfg)
        savings = estimate_hitl_savings(df_full, new_policies)
        p = savings["portfolio"]
        rows.append(
            {
                "target": c,
                "hitl_load":              p["hitl_load"],
                "hitl_savings_pct":       p["hitl_savings_pct"],
                "null_savings_pct":       p["null_savings_pct"],
                "lr_savings_pct":         p["lr_savings_pct"],
                "expected_hitl":          p["expected_hitl"],
                "baseline_hitl":          p["baseline_hitl"],
                "null_savings":           p["null_savings"],
                "lr_savings":             p["lr_savings"],
                "n_calibrated_fields":    p["n_calibrated_fields"],
                "n_always_review_fields": p["n_always_review_fields"],
                "n_always_trust_fields":  p["n_always_trust_fields"],
                "n_no_policy_fields":     p["n_no_policy_fields"],
            }
        )
    return pd.DataFrame(rows)
