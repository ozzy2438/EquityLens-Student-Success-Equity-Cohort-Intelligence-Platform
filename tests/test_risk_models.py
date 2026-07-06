from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from equitylens_risk.models import (
    audit_group_fairness,
    boosting_feature_importance,
    evaluate_model,
    evaluate_top_fraction,
    fit_gradient_boosting,
    fit_logistic_regression,
    logistic_feature_importance,
)


@pytest.fixture
def train_holdout() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    # A small synthetic dataset where census_engagement_score is the only
    # informative feature -- mirrors the real pipeline's own finding
    # (docs/model_results.md) that one feature carries almost all of the
    # discriminative power, so this is a realistic, not contrived, fixture.

    def make(n: int, seed_offset: int) -> tuple[pd.DataFrame, pd.Series]:
        r = np.random.default_rng(seed_offset)
        engagement = r.random(n)
        attrited = r.random(n) < (0.4 - 0.3 * engagement)
        X = pd.DataFrame(
            {
                "geography": r.choice(["metro", "regional", "remote"], n),
                "low_ses": r.random(n) < 0.12,
                "first_nations": r.random(n) < 0.02,
                "disability": r.random(n) < 0.07,
                "non_english_speaking_background": r.random(n) < 0.03,
                "women_non_traditional_area": r.random(n) < 0.04,
                "first_in_family": r.random(n) < 0.5,
                "seifa_decile": r.integers(1, 11, n),
                "census_engagement_score": engagement,
            }
        )
        y = pd.Series(attrited.astype(int))
        return X, y

    X_train, y_train = make(2000, 1)
    X_holdout, y_holdout = make(2000, 2)
    return X_train, y_train, X_holdout, y_holdout


def test_fit_logistic_regression_beats_chance(train_holdout) -> None:
    X_train, y_train, X_holdout, y_holdout = train_holdout
    pipeline = fit_logistic_regression(X_train, y_train)
    evaluation = evaluate_model(pipeline, X_holdout, y_holdout, "logistic_regression")
    assert evaluation.auc > 0.6
    assert 0.0 <= evaluation.pr_auc <= 1.0
    assert 0.0 <= evaluation.brier_score <= 1.0


def test_fit_gradient_boosting_beats_chance(train_holdout) -> None:
    X_train, y_train, X_holdout, y_holdout = train_holdout
    pipeline = fit_gradient_boosting(X_train, y_train)
    evaluation = evaluate_model(pipeline, X_holdout, y_holdout, "gradient_boosting")
    # A looser bound than the logistic test: boosting on a small (n=2000),
    # purely-linear-in-logit fixture is expected to be noisier and slightly
    # worse than logistic regression here -- exactly the real pipeline's own
    # finding (docs/model_results.md) -- not a bug in the fitting code.
    assert evaluation.auc > 0.55


def test_logistic_feature_importance_ranks_census_engagement_score_highest(train_holdout) -> None:
    X_train, y_train, _X_holdout, _y_holdout = train_holdout
    pipeline = fit_logistic_regression(X_train, y_train)
    importance = logistic_feature_importance(pipeline)
    assert importance.abs().idxmax() == "numeric__census_engagement_score"


def test_boosting_feature_importance_ranks_census_engagement_score_highest(train_holdout) -> None:
    X_train, y_train, X_holdout, y_holdout = train_holdout
    pipeline = fit_gradient_boosting(X_train, y_train)
    importance = boosting_feature_importance(pipeline, X_holdout, y_holdout, n_repeats=3)
    assert importance.idxmax() == "census_engagement_score"


def test_logistic_regression_drops_first_geography_category(train_holdout) -> None:
    # geography has 3 levels; with drop='first' the encoder should only
    # produce 2 dummy columns, not 3 -- confirms the collinearity fix
    # (docs/model_results.md) is actually wired in, not just described.
    X_train, y_train, _X_holdout, _y_holdout = train_holdout
    pipeline = fit_logistic_regression(X_train, y_train)
    encoded_names = pipeline.named_steps["preprocess"].get_feature_names_out()
    geography_columns = [name for name in encoded_names if "geography" in name]
    assert len(geography_columns) == 2


def test_evaluate_top_fraction_reports_operational_precision_recall() -> None:
    y_true = pd.Series([1, 1, 0, 0, 1, 0, 0, 1, 0, 0])
    predicted_probability = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05])

    evaluation = evaluate_top_fraction(y_true, predicted_probability, top_fraction=0.3)

    assert evaluation.flagged_students == 3
    assert evaluation.threshold_score == pytest.approx(0.7)
    assert evaluation.precision == pytest.approx(2 / 3)
    assert evaluation.recall == pytest.approx(0.5)
    assert evaluation.fnr == pytest.approx(0.5)
    assert evaluation.lift_vs_base_rate == pytest.approx((2 / 3) / 0.4)


def test_audit_group_fairness_reports_group_calibration_and_threshold_fnr() -> None:
    y_true = pd.Series([1, 1, 0, 0, 1, 0, 0, 1, 0, 0])
    predicted_probability = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05])
    groups = {
        "group_a": np.array([1, 1, 1, 1, 1, 0, 0, 0, 0, 0], dtype=bool),
        "group_b": np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1], dtype=bool),
    }

    audit = audit_group_fairness(y_true, predicted_probability, groups, top_fraction=0.3)

    group_a = audit.loc[audit["group"] == "group_a"].iloc[0]
    assert group_a["n_students"] == 5
    assert group_a["attriters"] == 3
    assert group_a["observed_attrition"] == pytest.approx(0.6)
    assert group_a["mean_predicted"] == pytest.approx(0.7)
    assert group_a["calibration_gap_pp"] == pytest.approx(10.0)
    assert group_a["flagged_share"] == pytest.approx(0.6)
    assert group_a["threshold_fnr"] == pytest.approx(1 / 3)
    assert 0.0 <= group_a["threshold_fnr_ci_low"] <= group_a["threshold_fnr"]
    assert group_a["threshold_fnr"] <= group_a["threshold_fnr_ci_high"] <= 1.0


def test_audit_group_fairness_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError, match="membership length"):
        audit_group_fairness(
            pd.Series([1, 0, 1]),
            np.array([0.9, 0.8, 0.1]),
            {"bad": np.array([True, False])},
            top_fraction=0.5,
        )
