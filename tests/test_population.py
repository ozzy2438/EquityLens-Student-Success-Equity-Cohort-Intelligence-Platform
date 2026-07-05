from __future__ import annotations

import pytest

from equitylens_synthetic.population import (
    build_baseline_population,
    build_raked_population,
    build_seed_table,
    compare_marginals,
)


@pytest.fixture
def target_set() -> dict:
    def share(equity_group_id: str, share_pct: float, *, imputed: bool = False) -> dict:
        return {
            "institution_id": "acu",
            "equity_group_id": equity_group_id,
            "count": 0.0,
            "all_students": 10000.0,
            "share_pct": share_pct,
            "tolerance_pp": 1.0,
            "imputed_target_flag": imputed,
            "imputation_source": ("sector_average_share_2023" if imputed else None),
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
        },
    }


def test_baseline_population_matches_marginals_and_is_independent(target_set) -> None:
    population = build_baseline_population(target_set, 20000, seed=1)
    comparison = compare_marginals(population, target_set)
    assert comparison["abs_diff_pp"].max() < 1.0

    low_ses_pct = population["low_ses"].mean()
    regional_pct = population["geography"].isin(["regional", "remote"]).mean()
    joint_pct = (
        (population["low_ses"]) & population["geography"].isin(["regional", "remote"])
    ).mean()
    # Baseline is drawn independently, so the joint proportion should track
    # the independence product within sampling noise.
    assert joint_pct == pytest.approx(low_ses_pct * regional_pct, abs=0.01)


def test_baseline_and_raked_populations_share_a_dtype_schema(target_set) -> None:
    # Regression test: an earlier version left `low_ses`/`first_nations` as
    # raw "yes"/"no" seed-table strings in the raked population while the
    # baseline population used booleans -- the two builders must be
    # interchangeable for any downstream comparison code.
    baseline = build_baseline_population(target_set, 500, seed=1)
    raked, _convergence, _integerization = build_raked_population(target_set, 500, seed=1)
    for column in ("low_ses", "first_nations"):
        assert baseline[column].dtype == raked[column].dtype == bool


def test_raked_population_converges_and_matches_marginals(target_set) -> None:
    population, convergence, integerization = build_raked_population(target_set, 20000, seed=1)
    assert convergence.converged is True
    assert integerization.total_students == 20000

    comparison = compare_marginals(population, target_set)
    assert comparison["abs_diff_pp"].max() < 1.0


def test_raked_population_reflects_seed_correlation_not_independence(target_set) -> None:
    # The seed table shapes low_ses x regional/remote co-occurrence below
    # the independence-implied level (docs/assumptions.md, Table 11.9 lift
    # factors); the raked population should show a joint proportion clearly
    # below what independent sampling of the same marginals would produce,
    # while the baseline (independent by construction) should not.
    population, _convergence, _integerization = build_raked_population(target_set, 20000, seed=1)
    low_ses_pct = population["low_ses"].mean()
    regional_pct = population["geography"].isin(["regional", "remote"]).mean()
    independence_expected = low_ses_pct * regional_pct
    joint_pct = (
        (population["low_ses"]) & population["geography"].isin(["regional", "remote"])
    ).mean()
    assert joint_pct < independence_expected * 0.95


def test_include_imputed_false_uses_seed_implied_value_not_institution_value(target_set) -> None:
    # When "remote" is marked imputed and include_imputed=False, its target
    # is replaced with the seed table's own relative weight for that level
    # (scaled to n_students) rather than dropped from the margins outright --
    # dropping it would leave every other dimension still targeting the full
    # population while geography's own total silently fell short, an
    # inconsistency that degrades convergence for reasons unrelated to the
    # real data. Both variants must still converge; only the resolved
    # "remote" value should differ.
    target_set["targets"]["enrolment_share"] = [
        t if t["equity_group_id"] != "remote" else {**t, "imputed_target_flag": True}
        for t in target_set["targets"]["enrolment_share"]
    ]
    population_included, report_included, _ = build_raked_population(
        target_set, 5000, include_imputed=True, seed=1
    )
    population_excluded, report_excluded, _ = build_raked_population(
        target_set, 5000, include_imputed=False, seed=1
    )
    assert report_included.converged is True
    assert report_excluded.converged is True

    remote_share_included = (population_included["geography"] == "remote").mean() * 100
    remote_share_excluded = (population_excluded["geography"] == "remote").mean() * 100
    assert remote_share_included == pytest.approx(1.0, abs=0.5)
    assert remote_share_excluded != pytest.approx(remote_share_included, abs=0.05)


def test_build_seed_table_has_no_uniform_weight_shortcut() -> None:
    # A uniform seed would make raking provably converge to the independence
    # solution regardless of real correlation -- confirm the seed itself
    # carries genuine variation before it ever reaches rake().
    seed = build_seed_table()
    assert seed["weight"].nunique() > 1
