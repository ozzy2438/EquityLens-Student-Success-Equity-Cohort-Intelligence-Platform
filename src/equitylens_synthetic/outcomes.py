"""Step 3: outcome assignment for the synthetic population.

Three outcomes are assigned in sequence, and the sequence matters: retention
and success share a latent risk propensity (see below), then multi-year
completion is assigned **conditioned on** the retention outcome -- assigning
completion independently of year-1 retention would let the synthetic data
reproduce the exact S15-vs-S17 contradiction Phase 2's
`retention_vs_completion_plausibility` reconciliation check exists to catch
in the real warehouse (see `docs/schema.md`), just in synthetic form.

Outcome calibration anchors (replaces a naive fixed logit delta): a student
belonging to more than one equity group has their outcome logit built from
one additive anchor per group they belong to (plus a universal
`all_domestic` anchor every student carries), solved iteratively so that
each group's own *realized* mean probability -- accounting for every other
group's anchor and the shared noise draw -- matches its published target.
This is the fix for a bug found empirically while validating: a naive fixed
delta (group logit minus base logit, applied once) let a group whose
synthetic co-occurrence with other raked attributes diverges from its true
co-occurrence drift its own realized rate away from target (see
`docs/assumptions.md`, "outcome calibration anchors" and "first_nations
finding"). Iteratively solving anchors is the same cyclic-adjustment idea as
`raking.rake`, just solving one scalar per group via bisection instead of
rescaling cell weights.

Latent risk propensity: retention and success outcomes share a common
individual noise component (`shared_latent_risk`, weight controlled by
`connection_strength`), so a student's academic-performance signal
(`success_rate_realized`) genuinely leads their retention outcome, the way
real early-warning systems depend on behavioural signals to work at all --
see `docs/assumptions.md`, "latent risk propensity linking" for the implied
AUC this produces, checked (not tuned to a target number) at several
connection strengths.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from equitylens_synthetic.models import ConvergenceReport

# Population attributes with a directly observed Section 16 retention/success
# rate to attach as an outcome calibration anchor.
ATTRIBUTE_TO_EQUITY_GROUP = {
    "low_ses": "low_ses_by_sa1",
    "first_nations": "first_nations",
    "disability": "disability",
    "non_english_speaking_background": "non_english_speaking_background",
}
_GEOGRAPHY_EQUITY_GROUPS = ("regional", "remote")

# Population attributes with NO Section 16 rate broken out by that group at
# all (women_non_traditional_area) or no DoE-published rate whatsoever
# (first_in_family, not an official equity group -- see docs/assumptions.md).
# These contribute no calibrated anchor: a well-specified Phase 4 model
# should find near-zero effect for them unless it discovers a real
# relationship directly from the data, which this generative process does
# not build in.
UNCALIBRATED_ATTRIBUTES = ("women_non_traditional_area", "first_in_family")

# Individual heterogeneity magnitude on the logit scale, chosen structurally
# (a standard unexplained-heterogeneity magnitude for retention-style
# models) -- see docs/assumptions.md.
DEFAULT_SIGMA = 1.0

# Excluded-tier targets (tolerance_pp is None, docs/calibration_targets.md)
# are still used as an outcome-generating anchor value, but never gate
# convergence -- this stand-in tolerance means "never fails the gate."
_UNGATED_TOLERANCE_PP = 1000.0

# A small nonzero probability that a student who did not return in year 2
# still eventually completes (e.g. via a later readmission) -- kept nonzero
# rather than 0.0 because DoE's own completion outcome categories
# distinguish "never came back" from other non-completion paths, implying
# some late-return completions do occur, but small because this is the
# dominant, expected case (attrition materially reduces completion odds).
ATTRITED_COMPLETION_FLOOR = 0.05


def _logit(p: np.ndarray | float) -> np.ndarray | float:
    clipped = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(clipped / (1 - clipped))


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1 / (1 + np.exp(-x))


def _rate_targets_by_group(target_set: dict, metric: str, institution_id: str) -> dict[str, dict]:
    """Full target records (value + tolerance_pp), keyed by equity_group_id."""

    return {
        t["equity_group_id"]: t
        for t in target_set["targets"][metric]
        if t["institution_id"] == institution_id
    }


def _group_membership_masks(population: pd.DataFrame) -> dict[str, np.ndarray]:
    n = len(population)
    masks: dict[str, np.ndarray] = {"all_domestic": np.ones(n, dtype=bool)}
    for attribute, equity_group_id in ATTRIBUTE_TO_EQUITY_GROUP.items():
        masks[equity_group_id] = population[attribute].to_numpy(dtype=bool)
    for level in _GEOGRAPHY_EQUITY_GROUPS:
        masks[level] = (population["geography"] == level).to_numpy()
    return masks


def generate_latent_risk(n_students: int, seed: int) -> np.ndarray:
    """Standard-normal latent risk propensity shared across outcome
    assignment calls, so academic performance and retention are not drawn
    independently -- see the module docstring."""

    rng = np.random.default_rng(seed)
    return rng.standard_normal(n_students)


def _combined_noise(
    n: int,
    sigma: float,
    connection_strength: float,
    shared_latent_risk: np.ndarray | None,
    rng: np.random.Generator,
) -> np.ndarray:
    """A one-factor mixture of the shared latent risk and this outcome's own
    idiosyncratic noise, `connection_strength` in [0, 1] controlling the
    mix. Both components are unit-variance standard normals combined as
    `sqrt(w) * shared + sqrt(1-w) * idiosyncratic`, so the result is still a
    standard normal (before `sigma` scaling) regardless of `connection_strength`
    -- `connection_strength=0` reproduces fully independent per-outcome noise
    (the original behaviour); `connection_strength=1` makes this outcome's
    noise identical (up to `sigma` scaling) to the shared latent risk.
    """

    idiosyncratic = rng.standard_normal(n)
    if shared_latent_risk is None or connection_strength <= 0:
        combined = idiosyncratic
    else:
        combined = (
            np.sqrt(connection_strength) * shared_latent_risk
            + np.sqrt(1 - connection_strength) * idiosyncratic
        )
    return combined * sigma


def calibrate_anchors(
    group_membership: dict[str, np.ndarray],
    group_values: dict[str, float],
    group_tolerances: dict[str, float],
    noise: np.ndarray,
    *,
    max_iter: int = 30,
    anchor_step_tolerance: float = 1e-4,
) -> tuple[dict[str, float], ConvergenceReport]:
    """Solve one additive logit anchor per equity group (including the
    universal `all_domestic` anchor) so each group's realized mean
    probability matches its target, cycling because group memberships
    overlap (the same idea as `raking.rake`, applied to a scalar anchor per
    group instead of rescaling cell weights)."""

    anchors = dict.fromkeys(group_values, 0.0)
    iterations = 0
    for iterations in range(1, max_iter + 1):  # noqa: B007 -- iterations used below
        max_anchor_step = 0.0
        for group, target_pct in group_values.items():
            mask = group_membership[group]
            if not mask.any():
                continue
            target_prob = target_pct / 100

            other_contribution = noise.copy()
            for other_group, anchor in anchors.items():
                if other_group != group:
                    other_contribution = other_contribution + anchor * group_membership[other_group]
            subset_logit = other_contribution[mask]

            lo, hi = -8.0, 8.0
            new_anchor = anchors[group]
            for _ in range(50):
                new_anchor = (lo + hi) / 2
                realized = float(_sigmoid(subset_logit + new_anchor).mean())
                if abs(realized - target_prob) < 1e-5:
                    break
                if realized < target_prob:
                    lo = new_anchor
                else:
                    hi = new_anchor

            max_anchor_step = max(max_anchor_step, abs(new_anchor - anchors[group]))
            anchors[group] = new_anchor

        if max_anchor_step < anchor_step_tolerance:
            break

    final_logit = noise.copy()
    for group, anchor in anchors.items():
        final_logit = final_logit + anchor * group_membership[group]

    deviation_by_margin: dict[str, float] = {}
    for group, target_pct in group_values.items():
        mask = group_membership[group]
        if not mask.any():
            continue
        realized_pct = float(_sigmoid(final_logit[mask]).mean() * 100)
        deviation_by_margin[group] = abs(realized_pct - target_pct)

    converged = all(
        deviation <= group_tolerances.get(group, _UNGATED_TOLERANCE_PP)
        for group, deviation in deviation_by_margin.items()
    )
    max_deviation = max(deviation_by_margin.values()) if deviation_by_margin else 0.0

    report = ConvergenceReport(
        converged=converged,
        iterations=iterations,
        max_relative_deviation=max_deviation,
        deviation_by_margin=deviation_by_margin,
    )
    return anchors, report


def _apply_anchors(
    anchors: dict[str, float], group_membership: dict[str, np.ndarray], n: int
) -> np.ndarray:
    total = np.zeros(n)
    for group, anchor in anchors.items():
        total = total + anchor * group_membership[group]
    return total


def _assign_rate_outcome(
    population: pd.DataFrame,
    target_set: dict,
    metric: str,
    *,
    institution_id: str,
    sigma: float,
    connection_strength: float,
    shared_latent_risk: np.ndarray | None,
    seed: int,
    anchor_max_iter: int,
) -> tuple[np.ndarray, np.ndarray, ConvergenceReport]:
    """Shared machinery for retention_rate and success_rate: solve group
    anchors, add (possibly shared) noise, return (pre-noise probability,
    noisy logit, anchor convergence report)."""

    rng = np.random.default_rng(seed)
    targets_by_group = _rate_targets_by_group(target_set, metric, institution_id)
    group_membership = _group_membership_masks(population)

    group_values = {g: t["value"] for g, t in targets_by_group.items() if g in group_membership}
    group_tolerances = {
        g: (t["tolerance_pp"] if t["tolerance_pp"] is not None else _UNGATED_TOLERANCE_PP)
        for g, t in targets_by_group.items()
        if g in group_membership
    }

    n = len(population)
    noise = _combined_noise(n, sigma, connection_strength, shared_latent_risk, rng)
    anchors, convergence = calibrate_anchors(
        group_membership, group_values, group_tolerances, noise, max_iter=anchor_max_iter
    )

    pre_noise_logit = _apply_anchors(anchors, group_membership, n)
    noisy_logit = pre_noise_logit + noise
    return _sigmoid(pre_noise_logit), noisy_logit, convergence


def assign_retention_outcomes(
    population: pd.DataFrame,
    target_set: dict,
    *,
    institution_id: str = "acu",
    sigma: float = DEFAULT_SIGMA,
    connection_strength: float = 0.0,
    shared_latent_risk: np.ndarray | None = None,
    seed: int = 42,
    anchor_max_iter: int = 30,
) -> tuple[pd.DataFrame, ConvergenceReport]:
    """Assign each student a year-1 retention probability and a realized
    (noisy) retained/attrited outcome, calibrated via group anchors."""

    pre_noise_probability, noisy_logit, convergence = _assign_rate_outcome(
        population,
        target_set,
        "retention_rate",
        institution_id=institution_id,
        sigma=sigma,
        connection_strength=connection_strength,
        shared_latent_risk=shared_latent_risk,
        seed=seed,
        anchor_max_iter=anchor_max_iter,
    )
    rng = np.random.default_rng(seed + 1)  # separate stream from the noise draw's own rng

    population = population.copy()
    population["retention_probability"] = pre_noise_probability
    population["retained"] = rng.random(len(population)) < _sigmoid(noisy_logit)
    return population, convergence


def assign_success_outcomes(
    population: pd.DataFrame,
    target_set: dict,
    *,
    institution_id: str = "acu",
    units_attempted_eftsl: float = 1.0,
    sigma: float = DEFAULT_SIGMA,
    connection_strength: float = 0.0,
    shared_latent_risk: np.ndarray | None = None,
    seed: int = 43,
    anchor_max_iter: int = 30,
) -> tuple[pd.DataFrame, ConvergenceReport]:
    """Assign a success rate (S15's EFTSL passed-over-attempted definition,
    docs/schema.md), sharing `shared_latent_risk` with retention when
    `connection_strength > 0` so academic performance leads retention rather
    than being drawn independently of it."""

    _pre_noise_probability, noisy_logit, convergence = _assign_rate_outcome(
        population,
        target_set,
        "success_rate",
        institution_id=institution_id,
        sigma=sigma,
        connection_strength=connection_strength,
        shared_latent_risk=shared_latent_risk,
        seed=seed,
        anchor_max_iter=anchor_max_iter,
    )
    success_rate_realized = _sigmoid(noisy_logit)

    population = population.copy()
    population["units_attempted_eftsl"] = units_attempted_eftsl
    population["success_rate_realized"] = success_rate_realized
    population["units_passed_eftsl"] = (
        population["units_attempted_eftsl"] * population["success_rate_realized"]
    )
    return population, convergence


def assign_completion_outcomes(
    population: pd.DataFrame,
    target_set: dict,
    *,
    institution_id: str = "acu",
    attrited_completion_floor: float = ATTRITED_COMPLETION_FLOOR,
    seed: int = 44,
) -> pd.DataFrame:
    """Assign 4/6/9-year completion outcomes conditioned on the student's
    already-assigned year-1 `retained` outcome, so a student who attrited in
    year 1 cannot show an implausibly high completion probability -- the
    synthetic-data version of the check `retention_vs_completion_plausibility`
    runs against the real warehouse (docs/schema.md).

    Requires `assign_retention_outcomes` to have run first (needs the
    `retained` column).
    """

    if "retained" not in population.columns:
        raise ValueError(
            "assign_completion_outcomes requires assign_retention_outcomes to "
            "have run first (missing 'retained' column)"
        )

    rng = np.random.default_rng(seed)
    retention_rate = _rate_targets_by_group(target_set, "retention_rate", institution_id)[
        "all_domestic"
    ]["value"]
    completion_targets = {
        t["tracking_window_years"]: t["value"]
        for t in target_set["targets"]["completion_rate"]
        if t["institution_id"] == institution_id
    }

    population = population.copy()
    for window, completion_rate in completion_targets.items():
        p_complete_given_retained = min(1.0, completion_rate / retention_rate)
        probability = np.where(
            population["retained"], p_complete_given_retained, attrited_completion_floor
        )
        population[f"completed_{window}yr"] = rng.random(len(population)) < probability
    return population


def compute_auc(scores: pd.Series, outcome: pd.Series) -> float:
    """Rank-based AUC (the Mann-Whitney U / (n_pos * n_neg) identity) --
    deliberately not a fitted model: `scores` is already this project's own
    structural risk score (e.g. pre-noise `retention_probability`, or the
    realized `success_rate_realized` academic-performance signal), so this
    directly answers "how discriminative is this signal against the actual
    simulated outcome," without adding a modelling dependency to answer a
    question the raw scores already carry the answer to."""

    ranks = scores.rank()
    outcome_bool = outcome.astype(bool)
    n_pos = int(outcome_bool.sum())
    n_neg = len(outcome_bool) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    sum_ranks_pos = ranks[outcome_bool].sum()
    return float((sum_ranks_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))
