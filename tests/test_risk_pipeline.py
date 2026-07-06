from __future__ import annotations

import pytest

from equitylens_risk.features import CENSUS_FEATURE_COLUMNS
from equitylens_risk.pipeline import build_cohort, build_train_holdout, features_and_labels


@pytest.fixture
def target_set() -> dict:
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

    def rate(equity_group_id: str, value: float, *, n: float) -> dict:
        return {
            "institution_id": "acu",
            "equity_group_id": equity_group_id,
            "value": value,
            "n": n,
            "tolerance_tier": "n>=200",
            "tolerance_pp": 2.0,
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
                rate("all_domestic", 83.0, n=2000.0),
                rate("low_ses_by_sa1", 80.0, n=240.0),
                rate("first_nations", 78.0, n=240.0),
                rate("regional", 82.0, n=220.0),
                rate("remote", 67.0, n=220.0),
            ],
            "success_rate": [],
        },
    }


def test_build_cohort_produces_census_feature_and_outcome_columns(target_set) -> None:
    population = build_cohort(
        target_set,
        1000,
        population_seed=1,
        latent_seed=2,
        outcome_seed=3,
        census_seed=4,
    )
    assert "retained" in population.columns
    assert "census_engagement_score" in population.columns
    assert population["census_engagement_score"].between(0, 1).all()


def test_build_train_holdout_shares_the_raked_joint_distribution_by_design(target_set) -> None:
    # `raking.rake` + `integerize` are deterministic given the same target
    # set and n_students -- geography/low_ses/first_nations/seifa_decile are
    # *expected* to come out identical between any two seeds, since that is
    # exactly what "calibrated to the same targets" means. This is not a
    # leak: it only pins the four *raked* columns; it says nothing about the
    # label.
    train, holdout = build_train_holdout(target_set, 1000)
    assert train["seifa_decile"].equals(holdout["seifa_decile"])
    assert train["geography"].equals(holdout["geography"])


def test_build_train_holdout_draws_independent_outcomes_and_attributes(target_set) -> None:
    # What a cohort-based split actually needs to vary -- the four
    # independent attributes, the shared latent risk draw, and every
    # outcome/behavioural signal -- must differ between train and holdout,
    # even though the raked joint distribution (above) does not.
    train, holdout = build_train_holdout(target_set, 1000)
    assert not train["disability"].equals(holdout["disability"])
    assert not train["census_engagement_score"].equals(holdout["census_engagement_score"])
    assert train["retained"].mean() != holdout["retained"].mean()


def test_features_and_labels_matches_allow_list_exactly(target_set) -> None:
    train, _holdout = build_train_holdout(target_set, 1000)
    features, labels = features_and_labels(train)
    assert list(features.columns) == list(CENSUS_FEATURE_COLUMNS)
    assert set(labels.unique()) <= {0, 1}
    assert "retained" not in features.columns
    assert "retention_probability" not in features.columns
