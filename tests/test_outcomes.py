from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from equitylens_synthetic.outcomes import (
    _logit,
    _sigmoid,
    assign_completion_outcomes,
    assign_retention_outcomes,
    assign_success_outcomes,
    calibrate_anchors,
    compute_auc,
    generate_latent_risk,
)


@pytest.fixture
def target_set() -> dict:
    def rate(equity_group_id: str, value: float) -> dict:
        return {
            "institution_id": "acu",
            "equity_group_id": equity_group_id,
            "metric": "retention_rate",
            "value": value,
            "n": 1000.0,
            "tolerance_tier": "n>=200",
            "tolerance_pp": 2.0,
            "imputed_target_flag": False,
            "imputation_source": None,
        }

    return {
        "targets": {
            "retention_rate": [
                rate("all_domestic", 82.91),
                rate("low_ses_by_sa1", 80.84),
                rate("first_nations", 77.85),
                rate("disability", 83.76),
                rate("non_english_speaking_background", 84.32),
                rate("regional", 81.77),
                rate("remote", 66.78),
            ],
            "success_rate": [
                {**rate("all_domestic", 90.51), "metric": "success_rate"},
                {**rate("low_ses_by_sa1", 87.80), "metric": "success_rate"},
            ],
            "completion_rate": [
                {
                    "institution_id": "acu",
                    "tracking_window_years": 4,
                    "cohort_end_year": 2024,
                    "value": 43.12,
                    "tolerance_pp": 2.0,
                },
                {
                    "institution_id": "acu",
                    "tracking_window_years": 9,
                    "cohort_end_year": 2024,
                    "value": 70.46,
                    "tolerance_pp": 2.0,
                },
            ],
        }
    }


@pytest.fixture
def population() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "geography": ["metro", "regional", "remote", "metro"],
            "low_ses": [False, True, False, False],
            "first_nations": [False, False, True, False],
            "disability": [False, False, False, False],
            "non_english_speaking_background": [False, False, False, False],
        }
    )


def _large_population(seed: int = 0, n: int = 20000) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "geography": rng.choice(["metro", "regional", "remote"], n, p=[0.88, 0.11, 0.01]),
            "low_ses": rng.random(n) < 0.12,
            "first_nations": rng.random(n) < 0.02,
            "disability": rng.random(n) < 0.07,
            "non_english_speaking_background": rng.random(n) < 0.03,
        }
    )


def test_logit_sigmoid_are_inverses() -> None:
    p = np.array([0.1, 0.5, 0.9])
    assert _sigmoid(_logit(p)) == pytest.approx(p, abs=1e-9)


def test_calibrate_anchors_converges_each_group_to_its_own_target() -> None:
    # Two overlapping groups (a "low_ses" student can also be "regional") so
    # the anchors must be solved cyclically, not in one independent pass, for
    # each group's *own* realized rate to land on its own target.
    n = 20000
    rng = np.random.default_rng(1)
    group_membership = {
        "all_domestic": np.ones(n, dtype=bool),
        "low_ses": rng.random(n) < 0.2,
        "regional": rng.random(n) < 0.15,
    }
    group_values = {"all_domestic": 80.0, "low_ses": 65.0, "regional": 70.0}
    group_tolerances = {"all_domestic": 1.0, "low_ses": 1.0, "regional": 1.0}
    noise = rng.standard_normal(n)

    anchors, convergence = calibrate_anchors(
        group_membership, group_values, group_tolerances, noise
    )

    assert convergence.converged
    assert all(deviation <= 1.0 for deviation in convergence.deviation_by_margin.values())

    final_logit = sum(anchors[g] * group_membership[g] for g in anchors) + noise
    for group, target_pct in group_values.items():
        realized_pct = float(_sigmoid(final_logit[group_membership[group]]).mean() * 100)
        assert realized_pct == pytest.approx(target_pct, abs=1.0)


def test_assign_retention_outcomes_matches_aggregate_target(target_set) -> None:
    # Regression test for the Jensen's-inequality bias: naively adding
    # logit-scale noise then averaging sigmoid does not preserve the mean:
    # an earlier version realized 78.66% against an 82.91% target.
    large_population = _large_population(seed=0)
    result, convergence = assign_retention_outcomes(large_population, target_set, sigma=1.0, seed=1)
    realized_pct = result["retained"].mean() * 100
    assert realized_pct == pytest.approx(82.91, abs=0.5)
    assert convergence.converged


def test_assign_retention_outcomes_calibrates_first_nations_within_tolerance(target_set) -> None:
    # Regression test for the first_nations systematic-bias finding
    # (docs/assumptions.md, "first_nations finding"): a fixed, single-pass
    # logit delta let this group's realized rate drift ~5pp above its
    # published target because of how Step 2's seed correlation structure
    # interacts with compounding multiple group memberships. Iteratively
    # solved group anchors must bring it back within the ±2pp tolerance
    # Step 0 declared for this group's N tier.
    large_population = _large_population(seed=0)
    result, _convergence = assign_retention_outcomes(
        large_population, target_set, sigma=1.0, seed=1
    )
    realized_pct = result.loc[result["first_nations"], "retained"].mean() * 100
    assert realized_pct == pytest.approx(77.85, abs=2.0)


def test_assign_success_outcomes_matches_aggregate_target_and_computes_units(target_set) -> None:
    large_population = _large_population(seed=0)
    result, convergence = assign_success_outcomes(large_population, target_set, seed=2)
    assert result["success_rate_realized"].mean() * 100 == pytest.approx(90.51, abs=0.5)
    assert (
        result["units_passed_eftsl"]
        == result["units_attempted_eftsl"] * result["success_rate_realized"]
    ).all()
    assert convergence.converged


def test_connection_strength_zero_keeps_behavioral_signal_uninformative(target_set) -> None:
    # connection_strength=0.0 (the default) must reproduce the original
    # independent-noise behaviour: success and retention share nothing, so
    # success_rate_realized carries no information about retained.
    large_population = _large_population(seed=0)
    latent_risk = generate_latent_risk(len(large_population), seed=100)
    retained_population, _ = assign_retention_outcomes(
        large_population,
        target_set,
        connection_strength=0.0,
        shared_latent_risk=latent_risk,
        seed=42,
    )
    result, _ = assign_success_outcomes(
        retained_population,
        target_set,
        connection_strength=0.0,
        shared_latent_risk=latent_risk,
        seed=43,
    )
    auc = compute_auc(result["success_rate_realized"], result["retained"])
    assert auc == pytest.approx(0.5, abs=0.02)


def test_connection_strength_above_zero_makes_behavioral_signal_informative(target_set) -> None:
    # Once retention and success share `shared_latent_risk`, the behavioural
    # signal genuinely leads the outcome -- this is the fix for the
    # architectural gap the AUC~0.52 finding exposed: 3c's signals were being
    # generated independently of 3a/3b's outcome. See docs/assumptions.md,
    # "latent risk propensity linking," for the connection strengths
    # actually measured.
    large_population = _large_population(seed=0)
    latent_risk = generate_latent_risk(len(large_population), seed=100)
    retained_population, _ = assign_retention_outcomes(
        large_population,
        target_set,
        connection_strength=0.7,
        shared_latent_risk=latent_risk,
        seed=42,
    )
    result, _ = assign_success_outcomes(
        retained_population,
        target_set,
        connection_strength=0.7,
        shared_latent_risk=latent_risk,
        seed=43,
    )
    auc = compute_auc(result["success_rate_realized"], result["retained"])
    assert auc > 0.6


def test_assign_completion_outcomes_requires_retention_first(target_set, population) -> None:
    with pytest.raises(ValueError, match="assign_retention_outcomes"):
        assign_completion_outcomes(population, target_set)


def test_assign_completion_outcomes_conditions_on_retention(target_set) -> None:
    # Regression test for the synthetic version of the Phase 2
    # retention_vs_completion_plausibility contradiction: an attrited
    # student must not show a high completion probability.
    population = pd.DataFrame(
        {
            "geography": ["metro"] * 1000,
            "low_ses": [False] * 1000,
            "first_nations": [False] * 1000,
            "disability": [False] * 1000,
            "non_english_speaking_background": [False] * 1000,
            "retained": [True] * 500 + [False] * 500,
        }
    )
    result = assign_completion_outcomes(population, target_set, seed=3)
    retained_rate = result.loc[result["retained"], "completed_4yr"].mean()
    attrited_rate = result.loc[~result["retained"], "completed_4yr"].mean()
    assert retained_rate > attrited_rate
    assert attrited_rate < 0.10  # near the documented ATTRITED_COMPLETION_FLOOR


def test_compute_auc_perfect_separation_is_one() -> None:
    scores = pd.Series([0.9, 0.8, 0.2, 0.1])
    outcome = pd.Series([True, True, False, False])
    assert compute_auc(scores, outcome) == pytest.approx(1.0)


def test_compute_auc_reversed_separation_is_zero() -> None:
    scores = pd.Series([0.1, 0.2, 0.8, 0.9])
    outcome = pd.Series([True, True, False, False])
    assert compute_auc(scores, outcome) == pytest.approx(0.0)


def test_compute_auc_handles_single_class_as_nan() -> None:
    scores = pd.Series([0.1, 0.5, 0.9])
    outcome = pd.Series([True, True, True])
    assert compute_auc(scores, outcome) != compute_auc(scores, outcome)  # NaN != NaN
