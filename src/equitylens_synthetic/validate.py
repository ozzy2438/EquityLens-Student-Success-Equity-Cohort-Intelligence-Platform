"""Step 3d: post-outcome validation.

Step 2's `population.compare_marginals` only checks that the population's
*composition* matches Section 11/ABS marginals -- it runs before any outcome
exists. This module re-checks after `outcomes.py` has assigned retention,
success, and completion outcomes, because assigning outcomes (individual
noise, the conditional completion draw) can shift realized rates away from
the population-level composition checks already passed. A population that
passes Step 2's checks but whose *outcomes* drift from Section 15/16/17
targets would be exactly as uncalibrated as if Step 2 had never run.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from equitylens_synthetic.outcomes import (
    assign_retention_outcomes,
    assign_success_outcomes,
    compute_auc,
    generate_latent_risk,
)
from equitylens_synthetic.population import build_raked_population

# Geography levels resolved from the `geography` column rather than a
# boolean attribute column, mirroring `outcomes._group_membership_masks`.
_GEOGRAPHY_GROUPS = ("regional", "remote")
_BOOLEAN_ATTRIBUTE_GROUPS = {
    "low_ses": "low_ses_by_sa1",
    "first_nations": "first_nations",
    "disability": "disability",
    "non_english_speaking_background": "non_english_speaking_background",
}

# Per-dimension tolerance for `population.compare_marginals`'s output,
# matching docs/calibration_targets.md exactly: geography/low_ses/
# first_nations are raked against Section 11 enrolment-share targets
# (±1.0pp), seifa_decile against the national SEIFA distribution (±2.0pp).
# A single flat tolerance across both would either be too strict for SEIFA
# or too loose for the equity-share dimensions.
_MARGINAL_TOLERANCE_PP = {
    "geography": 1.0,
    "low_ses": 1.0,
    "first_nations": 1.0,
    "seifa_decile": 2.0,
}


def _realized_rate(
    population: pd.DataFrame, equity_group_id: str, outcome_col: str
) -> float | None:
    if equity_group_id == "all_domestic":
        subset = population
    elif equity_group_id in _GEOGRAPHY_GROUPS:
        subset = population[population["geography"] == equity_group_id]
    else:
        attribute = next(
            (attr for attr, group in _BOOLEAN_ATTRIBUTE_GROUPS.items() if group == equity_group_id),
            None,
        )
        if attribute is None or attribute not in population.columns:
            return None
        subset = population[population[attribute]]
    if len(subset) == 0:
        return None
    return float(subset[outcome_col].mean() * 100)


_OUTCOME_RATE_COLUMNS = (
    "metric",
    "equity_group_id",
    "target_pct",
    "realized_pct",
    "deviation_pp",
    "tolerance_pp",
    "gated",
    "passed",
)


def validate_outcome_rates(
    population: pd.DataFrame,
    target_set: dict,
    metric: str,
    outcome_col: str,
    institution_id: str = "acu",
) -> pd.DataFrame:
    """Compare realized rates (from assigned outcomes) against every
    calibrated target for `metric`, using each target's own N-dependent
    tolerance tier -- targets in the excluded tier (`n<10_or_suppressed`)
    are reported but never gate pass/fail, matching Step 0's contract.

    Always returns the same columns, even with zero rows (e.g. a metric with
    no targets for this institution) -- an earlier version returned a
    column-less `pd.DataFrame([])` in that case, which crashed
    `generate_validation_report`'s `["gated"]` column access downstream.
    """

    rows = []
    for target in target_set["targets"][metric]:
        if target["institution_id"] != institution_id:
            continue
        realized = _realized_rate(population, target["equity_group_id"], outcome_col)
        if realized is None:
            continue
        deviation = abs(realized - target["value"])
        tolerance = target["tolerance_pp"]
        rows.append(
            {
                "metric": metric,
                "equity_group_id": target["equity_group_id"],
                "target_pct": target["value"],
                "realized_pct": round(realized, 2),
                "deviation_pp": round(deviation, 2),
                "tolerance_pp": tolerance,
                "gated": tolerance is not None,
                "passed": (tolerance is None) or (deviation <= tolerance),
            }
        )
    return pd.DataFrame(rows, columns=_OUTCOME_RATE_COLUMNS)


# Step 0's own boundary between the "10<=n<50" (+-8pp) and "n>=50" (tighter)
# tolerance tiers (docs/calibration_targets.md). Below this N, a single
# Bernoulli realization's own sampling variance is comparable to or larger
# than the group's tolerance, so gating on one draw cannot tell a genuine
# miscalibration apart from ordinary noise -- see docs/assumptions.md,
# "tiny-N gate methodology."
TINY_N_GATE_THRESHOLD = 50.0

_MULTI_SEED_COLUMNS = (
    "metric",
    "equity_group_id",
    "target_pct",
    "n_seeds",
    "mean_realized_pct",
    "std_realized_pct",
    "min_realized_pct",
    "max_realized_pct",
    "deviation_pp",
    "tolerance_pp",
    "gated",
    "passed",
)


def tiny_n_groups(target_set: dict, metric: str, institution_id: str = "acu") -> set[str]:
    """Equity groups whose own target N falls below `TINY_N_GATE_THRESHOLD`
    -- these are the ones `run_multi_seed_outcome_rates` exists for."""

    return {
        t["equity_group_id"]
        for t in target_set["targets"][metric]
        if t["institution_id"] == institution_id
        and t.get("n") is not None
        and t["n"] < TINY_N_GATE_THRESHOLD
    }


def run_multi_seed_outcome_rates(
    target_set: dict,
    metric: str,
    outcome_col: str,
    *,
    institution_id: str = "acu",
    n_students: int = 20000,
    connection_strength: float = 0.7,
    n_seeds: int = 10,
    population_seed: int = 42,
    base_outcome_seed: int = 1000,
) -> pd.DataFrame:
    """Re-run outcome assignment `n_seeds` times against the *same* raked
    population (only the outcome-noise draw varies across runs) and report
    the mean, spread, and range of each group's realized rate.

    This is the empirical evidence behind the tiny-N gate methodology
    (docs/assumptions.md): for a group like `remote` (N~35, the
    `10<=n<50` tolerance tier), a single Bernoulli draw over a few dozen
    synthetic students carries sampling variance on the same order as the
    group's own +-8pp tolerance, so one draw exceeding tolerance is not,
    by itself, evidence of miscalibration -- only the distribution across
    many draws can distinguish "correctly centred but noisy" from a
    genuine systematic miss (the `first_nations` finding this project's
    calibration anchors fixed was the latter: its *own calibrated mean*,
    not just one draw, was off target).
    """

    population, _convergence, _integerization = build_raked_population(
        target_set, n_students, institution_id=institution_id, seed=population_seed
    )
    latent_risk = generate_latent_risk(len(population), seed=population_seed + 500)

    realized_by_group: dict[str, list[float]] = {}
    for i in range(n_seeds):
        outcome_seed = base_outcome_seed + i
        pop, _retention_convergence = assign_retention_outcomes(
            population,
            target_set,
            institution_id=institution_id,
            connection_strength=connection_strength,
            shared_latent_risk=latent_risk,
            seed=outcome_seed,
        )
        if metric == "success_rate":
            pop, _success_convergence = assign_success_outcomes(
                pop,
                target_set,
                institution_id=institution_id,
                connection_strength=connection_strength,
                shared_latent_risk=latent_risk,
                seed=outcome_seed + 1,
            )
        report = validate_outcome_rates(pop, target_set, metric, outcome_col, institution_id)
        for _, row in report.iterrows():
            realized_by_group.setdefault(row["equity_group_id"], []).append(row["realized_pct"])

    rows = []
    for target in target_set["targets"][metric]:
        if target["institution_id"] != institution_id:
            continue
        group = target["equity_group_id"]
        values = realized_by_group.get(group)
        if not values:
            continue
        mean_realized = float(np.mean(values))
        deviation = abs(mean_realized - target["value"])
        tolerance = target["tolerance_pp"]
        rows.append(
            {
                "metric": metric,
                "equity_group_id": group,
                "target_pct": target["value"],
                "n_seeds": len(values),
                "mean_realized_pct": round(mean_realized, 2),
                "std_realized_pct": round(float(np.std(values)), 2),
                "min_realized_pct": round(min(values), 2),
                "max_realized_pct": round(max(values), 2),
                "deviation_pp": round(deviation, 2),
                "tolerance_pp": tolerance,
                "gated": tolerance is not None,
                "passed": (tolerance is None) or (deviation <= tolerance),
            }
        )
    return pd.DataFrame(rows, columns=_MULTI_SEED_COLUMNS)


def _apply_multi_seed_override(
    single_seed_report: pd.DataFrame, multi_seed_report: pd.DataFrame
) -> pd.DataFrame:
    """For any equity group present in `multi_seed_report` (the tiny-N
    groups it was computed for), replace the single-draw `deviation_pp`/
    `passed` verdict with the multi-seed mean's -- implements the tiny-N
    gate methodology rule for `generate_validation_report`."""

    if len(multi_seed_report) == 0:
        return single_seed_report
    report = single_seed_report.copy()
    override = multi_seed_report.set_index("equity_group_id")
    for group in override.index:
        mask = report["equity_group_id"] == group
        if not mask.any():
            continue
        report.loc[mask, "deviation_pp"] = override.loc[group, "deviation_pp"]
        report.loc[mask, "passed"] = bool(override.loc[group, "passed"])
    return report


_COMPLETION_RATE_COLUMNS = (
    "tracking_window_years",
    "target_pct",
    "realized_pct",
    "deviation_pp",
    "tolerance_pp",
    "passed",
)


def validate_completion_rates(
    population: pd.DataFrame, target_set: dict, institution_id: str = "acu"
) -> pd.DataFrame:
    rows = []
    for target in target_set["targets"]["completion_rate"]:
        if target["institution_id"] != institution_id:
            continue
        window = target["tracking_window_years"]
        column = f"completed_{window}yr"
        if column not in population.columns:
            continue
        realized = float(population[column].mean() * 100)
        deviation = abs(realized - target["value"])
        rows.append(
            {
                "tracking_window_years": window,
                "target_pct": target["value"],
                "realized_pct": round(realized, 2),
                "deviation_pp": round(deviation, 2),
                "tolerance_pp": target["tolerance_pp"],
                "passed": deviation <= target["tolerance_pp"],
            }
        )
    return pd.DataFrame(rows, columns=_COMPLETION_RATE_COLUMNS)


def generate_validation_report(
    population: pd.DataFrame,
    target_set: dict,
    marginal_comparison: pd.DataFrame,
    institution_id: str = "acu",
    multi_seed_retention_rate: pd.DataFrame | None = None,
    multi_seed_success_rate: pd.DataFrame | None = None,
) -> dict:
    """Assemble the full post-outcome validation report: population
    marginals (Step 2), outcome rates (retention/success), completion, and
    the implied-AUC finding -- reported, never tuned toward a target value
    (docs/assumptions.md).

    `multi_seed_retention_rate`/`multi_seed_success_rate`
    (`run_multi_seed_outcome_rates`'s output) are optional: when supplied,
    the tiny-N groups they cover (docs/assumptions.md, "tiny-N gate
    methodology") are gated on their multi-seed mean instead of this single
    population's single draw, since one Bernoulli realization over a
    handful of students cannot distinguish genuine miscalibration from
    ordinary sampling noise.
    """

    retention_report = validate_outcome_rates(
        population, target_set, "retention_rate", "retained", institution_id
    )
    success_report = validate_outcome_rates(
        population, target_set, "success_rate", "success_rate_realized", institution_id
    )
    # success_rate_realized is a continuous [0,1] proportion, not a boolean
    # outcome column -- its mean already is the realized percentage once
    # multiplied by 100 inside _realized_rate, so this reuses the same path.
    completion_report = validate_completion_rates(population, target_set, institution_id)

    if multi_seed_retention_rate is not None:
        retention_report = _apply_multi_seed_override(retention_report, multi_seed_retention_rate)
    if multi_seed_success_rate is not None:
        success_report = _apply_multi_seed_override(success_report, multi_seed_success_rate)

    implied_auc = None
    if "retention_probability" in population.columns and "retained" in population.columns:
        implied_auc = compute_auc(population["retention_probability"], population["retained"])

    # A second, separate AUC: how well the *behavioural* signal (success_rate,
    # generated in Step 3c) discriminates the retention outcome on its own.
    # With `connection_strength=0.0` (the default) this stays near 0.5 -- 3c
    # is generated fully independently of retention's noise draw in that
    # case. It only rises once retention and success are asked to share a
    # `shared_latent_risk` draw -- see docs/assumptions.md, "latent risk
    # propensity linking," for the connection strengths actually measured.
    implied_auc_behavioral_signal = None
    if "success_rate_realized" in population.columns and "retained" in population.columns:
        implied_auc_behavioral_signal = compute_auc(
            population["success_rate_realized"], population["retained"]
        )

    marginal_tolerance = marginal_comparison["dimension"].map(_MARGINAL_TOLERANCE_PP)
    marginal_report = marginal_comparison.assign(
        tolerance_pp=marginal_tolerance,
        passed=marginal_comparison["abs_diff_pp"] <= marginal_tolerance,
    )

    gated_reports = [
        marginal_report,
        retention_report[retention_report["gated"]],
        success_report[success_report["gated"]],
        completion_report,
    ]
    all_passed = all(bool(report["passed"].all()) for report in gated_reports if len(report))

    return {
        "population_marginals": marginal_report,
        "retention_rate": retention_report,
        "success_rate": success_report,
        "completion_rate": completion_report,
        "implied_auc": implied_auc,
        "implied_auc_behavioral_signal": implied_auc_behavioral_signal,
        "all_gated_checks_passed": all_passed,
    }
