from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from equitylens_risk.features import (
    CENSUS_FEATURE_COLUMNS,
    build_census_feature_table,
    generate_census_engagement_signal,
)
from equitylens_synthetic.outcomes import compute_auc


@pytest.fixture
def population() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "geography": ["metro", "regional", "remote", "metro"],
            "low_ses": [False, True, False, False],
            "first_nations": [False, False, True, False],
            "disability": [False, False, False, False],
            "non_english_speaking_background": [False, False, False, False],
            "women_non_traditional_area": [False, False, False, True],
            "first_in_family": [True, False, True, False],
            "seifa_decile": [3, 4, 2, 8],
        }
    )


def test_generate_census_engagement_signal_returns_zero_one_range(population) -> None:
    latent_risk = np.array([1.0, -1.0, 0.5, -0.5])
    signal = generate_census_engagement_signal(population, latent_risk)
    assert (signal >= 0).all()
    assert (signal <= 1).all()
    assert signal.name == "census_engagement_score"


def test_census_engagement_signal_connection_strength_zero_is_uninformative() -> None:
    # connection_strength=0.0 must make this signal share nothing with the
    # latent risk that also drives retention -- an uninformative feature by
    # construction, mirroring outcomes._combined_noise at connection_strength=0.
    rng = np.random.default_rng(0)
    n = 20000
    population = pd.DataFrame({"x": range(n)})
    latent_risk = rng.standard_normal(n)
    outcome = rng.random(n) < (1 / (1 + np.exp(-latent_risk)))

    signal = generate_census_engagement_signal(population, latent_risk, connection_strength=0.0)
    auc = compute_auc(signal, pd.Series(outcome))
    assert auc == pytest.approx(0.5, abs=0.02)


def test_census_engagement_signal_stronger_connection_raises_auc() -> None:
    # Higher connection_strength must make the signal more informative about
    # an outcome that shares the same latent risk -- the core mechanism
    # docs/model_design.md's measured AUC sweep (0.594 -> 0.646) depends on.
    rng = np.random.default_rng(0)
    n = 20000
    population = pd.DataFrame({"x": range(n)})
    latent_risk = rng.standard_normal(n)
    outcome = rng.random(n) < (1 / (1 + np.exp(-latent_risk)))

    weak = generate_census_engagement_signal(population, latent_risk, connection_strength=0.2)
    strong = generate_census_engagement_signal(population, latent_risk, connection_strength=0.6)
    auc_weak = compute_auc(weak, pd.Series(outcome))
    auc_strong = compute_auc(strong, pd.Series(outcome))
    assert auc_strong > auc_weak


def test_build_census_feature_table_selects_allow_listed_columns_only(population) -> None:
    population = population.assign(
        census_engagement_score=[0.1, 0.2, 0.3, 0.4],
        retention_probability=[0.9, 0.8, 0.7, 0.6],  # must never appear in features
        success_rate_realized=[0.95, 0.9, 0.85, 0.8],  # must never appear in features
    )
    features = build_census_feature_table(population)
    assert set(features.columns) == set(CENSUS_FEATURE_COLUMNS)
    assert "retention_probability" not in features.columns
    assert "success_rate_realized" not in features.columns


def test_build_census_feature_table_raises_on_missing_column(population) -> None:
    with pytest.raises(ValueError, match="census_engagement_score"):
        build_census_feature_table(population)
