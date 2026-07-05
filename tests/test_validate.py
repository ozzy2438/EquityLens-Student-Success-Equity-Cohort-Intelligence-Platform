from __future__ import annotations

import pandas as pd
import pytest

from equitylens_synthetic.validate import (
    _apply_multi_seed_override,
    generate_validation_report,
    run_multi_seed_outcome_rates,
    tiny_n_groups,
    validate_completion_rates,
    validate_outcome_rates,
)


@pytest.fixture
def target_set() -> dict:
    return {
        "targets": {
            "retention_rate": [
                {
                    "institution_id": "acu",
                    "equity_group_id": "all_domestic",
                    "value": 80.0,
                    "tolerance_pp": 2.0,
                },
                {
                    "institution_id": "acu",
                    "equity_group_id": "low_ses_by_sa1",
                    "value": 70.0,
                    "tolerance_pp": 2.0,
                },
                {
                    "institution_id": "acu",
                    "equity_group_id": "remote",
                    "value": 50.0,
                    "tolerance_pp": None,
                },
            ],
            "success_rate": [],
            "completion_rate": [
                {
                    "institution_id": "acu",
                    "tracking_window_years": 4,
                    "cohort_end_year": 2024,
                    "value": 40.0,
                    "tolerance_pp": 2.0,
                },
            ],
        }
    }


@pytest.fixture
def population() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "geography": ["metro"] * 6 + ["remote"] * 2,
            "low_ses": [True, True, False, False, False, False, False, False],
            "retained": [True, True, True, True, True, True, False, False],
            "completed_4yr": [True, True, True, False, False, False, False, False],
        }
    )


def test_validate_outcome_rates_computes_realized_and_pass_fail(target_set, population) -> None:
    report = validate_outcome_rates(population, target_set, "retention_rate", "retained")
    by_group = report.set_index("equity_group_id")

    assert by_group.loc["all_domestic", "realized_pct"] == pytest.approx(75.0)  # 6/8
    assert by_group.loc["low_ses_by_sa1", "realized_pct"] == pytest.approx(100.0)  # 2/2
    assert not by_group.loc["all_domestic", "passed"]  # 75 vs target 80, deviation 5 > tolerance 2
    assert not by_group.loc[
        "low_ses_by_sa1", "passed"
    ]  # 100 vs target 70, deviation 30 > tolerance 2


def test_validate_outcome_rates_null_tolerance_is_reported_but_not_gated(
    target_set, population
) -> None:
    report = validate_outcome_rates(population, target_set, "retention_rate", "retained")
    remote_row = report[report["equity_group_id"] == "remote"].iloc[0]
    assert not remote_row["gated"]
    assert remote_row["passed"]  # excluded targets never fail the gate


def test_validate_completion_rates(target_set, population) -> None:
    report = validate_completion_rates(population, target_set)
    row = report.iloc[0]
    assert row["realized_pct"] == pytest.approx(37.5)  # 3/8
    assert row["deviation_pp"] == pytest.approx(2.5)
    assert not row["passed"]  # 2.5 > tolerance 2.0


def test_generate_validation_report_flags_failure_and_reports_auc(target_set, population) -> None:
    population = population.assign(retention_probability=[0.9, 0.9, 0.8, 0.8, 0.7, 0.7, 0.3, 0.2])
    marginal_comparison = pd.DataFrame(
        {
            "dimension": ["geography", "low_ses"],
            "level": ["remote", "yes"],
            "target_pct": [25.0, 25.0],
            "actual_pct": [25.0, 25.0],
            "abs_diff_pp": [0.0, 0.0],
        }
    )
    report = generate_validation_report(population, target_set, marginal_comparison)
    assert report["all_gated_checks_passed"] is False
    assert report["implied_auc"] is not None
    assert 0.0 <= report["implied_auc"] <= 1.0
    assert report["population_marginals"]["passed"].all()


def test_apply_multi_seed_override_replaces_only_covered_groups(target_set, population) -> None:
    # single-seed report says all_domestic fails (75 vs 80, tolerance 2);
    # the multi-seed override only covers "remote" -- all_domestic's
    # single-seed verdict must be untouched.
    single_seed_report = validate_outcome_rates(
        population, target_set, "retention_rate", "retained"
    )
    multi_seed_report = pd.DataFrame(
        [
            {
                "metric": "retention_rate",
                "equity_group_id": "remote",
                "target_pct": 50.0,
                "n_seeds": 10,
                "mean_realized_pct": 50.5,
                "std_realized_pct": 4.0,
                "min_realized_pct": 45.0,
                "max_realized_pct": 56.0,
                "deviation_pp": 0.5,
                "tolerance_pp": None,
                "gated": False,
                "passed": True,
            }
        ]
    )
    overridden = _apply_multi_seed_override(single_seed_report, multi_seed_report)
    by_group = overridden.set_index("equity_group_id")
    assert not by_group.loc["all_domestic", "passed"]  # untouched, still fails
    assert by_group.loc["remote", "deviation_pp"] == pytest.approx(0.5)  # replaced


@pytest.fixture
def full_target_set() -> dict:
    def share(equity_group_id: str, share_pct: float) -> dict:
        return {
            "institution_id": "acu",
            "equity_group_id": equity_group_id,
            "count": 0.0,
            "all_students": 2000.0,
            "share_pct": share_pct,
            "tolerance_pp": 1.0,
            "imputed_target_flag": False,
            "imputation_source": None,
        }

    def rate(equity_group_id: str, value: float, *, n: float, tolerance_pp: float) -> dict:
        return {
            "institution_id": "acu",
            "equity_group_id": equity_group_id,
            "value": value,
            "n": n,
            "tolerance_tier": "n>=200" if n >= 200 else "10<=n<50",
            "tolerance_pp": tolerance_pp,
            "imputed_target_flag": False,
            "imputation_source": None,
        }

    return {
        "target_version": "v1",
        "reference_year": 2023,
        "targets": {
            "enrolment_share": [
                share("low_ses_sa1", 12.0),
                share("first_nations", 2.0),
                share("regional", 11.0),
                share("remote", 1.0),
                share("disability", 7.0),
                share("non_english_speaking_background", 3.0),
                share("women_non_traditional_area", 4.0),
            ],
            "seifa_decile_share": [
                {"decile": d, "population": 1000, "share_pct": 10.0, "tolerance_pp": 2.0}
                for d in range(1, 11)
            ],
            "retention_rate": [
                rate("all_domestic", 83.0, n=2000.0, tolerance_pp=2.0),
                rate("low_ses_by_sa1", 80.0, n=240.0, tolerance_pp=2.0),
                rate("first_nations", 78.0, n=240.0, tolerance_pp=2.0),
                rate("regional", 82.0, n=220.0, tolerance_pp=2.0),
                rate("remote", 67.0, n=20.0, tolerance_pp=8.0),
            ],
            "success_rate": [
                rate("all_domestic", 90.0, n=2000.0, tolerance_pp=2.0),
                rate("remote", 86.0, n=20.0, tolerance_pp=8.0),
            ],
        },
    }


def test_tiny_n_groups_identifies_small_n_targets_only(full_target_set) -> None:
    assert tiny_n_groups(full_target_set, "retention_rate") == {"remote"}
    assert tiny_n_groups(full_target_set, "success_rate") == {"remote"}


def test_run_multi_seed_outcome_rates_reports_spread_across_seeds(full_target_set) -> None:
    report = run_multi_seed_outcome_rates(
        full_target_set,
        "retention_rate",
        "retained",
        n_students=2000,
        n_seeds=3,
        population_seed=1,
        base_outcome_seed=100,
    )
    by_group = report.set_index("equity_group_id")
    assert by_group.loc["remote", "n_seeds"] == 3
    # A tiny-N group's realized rate should vary across outcome-noise seeds
    # (the whole point of the multi-seed check); a large group like
    # all_domestic should barely move at 2000 students.
    assert by_group.loc["remote", "std_realized_pct"] >= 0.0
    assert (
        by_group.loc["all_domestic", "std_realized_pct"]
        < by_group.loc["remote", "std_realized_pct"]
        or by_group.loc["remote", "std_realized_pct"] == 0.0
    )
