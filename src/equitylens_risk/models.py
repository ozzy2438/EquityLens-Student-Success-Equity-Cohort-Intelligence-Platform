"""Phase 4b: baseline logistic regression vs. gradient boosting, evaluated
on `pipeline.build_train_holdout`'s holdout cohort.

AUC alone is not the right lens for a triage-facing model: the outreach
team acts on the *ranking* of a rare-ish class (~17-18% attrition, not 50%),
so PR-AUC (precision/recall on the minority class), calibration (is a
predicted 30% risk actually a ~30% observed rate), and capacity-based
top-k error rates matter as much as discrimination -- see
`docs/model_results.md` for the measured numbers and the model-selection
call this module's output feeds into.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

CATEGORICAL_COLUMNS = ("geography",)
NUMERIC_COLUMNS = (
    "low_ses",
    "first_nations",
    "disability",
    "non_english_speaking_background",
    "women_non_traditional_area",
    "first_in_family",
    "seifa_decile",
    "census_engagement_score",
)


@dataclass(frozen=True, slots=True)
class ModelEvaluation:
    """Holdout-cohort evaluation of one fitted pipeline."""

    model_name: str
    auc: float
    pr_auc: float
    brier_score: float
    calibration_bin_true: np.ndarray
    calibration_bin_predicted: np.ndarray


@dataclass(frozen=True, slots=True)
class TopFractionEvaluation:
    """Operational ranking quality at a capacity-based top-k cut."""

    top_fraction: float
    threshold_score: float
    flagged_students: int
    precision: float
    recall: float
    fnr: float
    lift_vs_base_rate: float


def _build_preprocessor(*, scale_numeric: bool, drop_first_category: bool) -> ColumnTransformer:
    # `drop_first_category=True` for logistic regression: with all three
    # `geography` levels one-hot encoded and no dropped baseline, L2
    # regularization splits the same information unpredictably between the
    # intercept and all three dummy coefficients, making them individually
    # uninterpretable. Dropping one category (metro, alphabetically first)
    # makes the remaining two coefficients a clean "risk relative to metro"
    # read. Boosting's splits do not have this ambiguity, so it keeps every
    # category.
    numeric_step = StandardScaler() if scale_numeric else "passthrough"
    categorical_encoder = OneHotEncoder(
        handle_unknown="ignore", drop="first" if drop_first_category else None
    )
    return ColumnTransformer(
        [
            ("categorical", categorical_encoder, list(CATEGORICAL_COLUMNS)),
            ("numeric", numeric_step, list(NUMERIC_COLUMNS)),
        ]
    )


def fit_logistic_regression(X_train: pd.DataFrame, y_train: pd.Series) -> Pipeline:
    pipeline = Pipeline(
        [
            ("preprocess", _build_preprocessor(scale_numeric=True, drop_first_category=True)),
            ("model", LogisticRegression(max_iter=1000)),
        ]
    )
    pipeline.fit(X_train, y_train)
    return pipeline


def fit_gradient_boosting(
    X_train: pd.DataFrame, y_train: pd.Series, *, random_state: int = 42
) -> Pipeline:
    # Tree splits are scale-invariant, so the numeric block is left
    # unscaled -- fitting the *same* logistic-vs-boosting comparison on
    # differently-scaled features would confound the model-choice
    # comparison with a preprocessing difference.
    pipeline = Pipeline(
        [
            ("preprocess", _build_preprocessor(scale_numeric=False, drop_first_category=False)),
            ("model", HistGradientBoostingClassifier(random_state=random_state)),
        ]
    )
    pipeline.fit(X_train, y_train)
    return pipeline


def predict_probability(pipeline: Pipeline, X: pd.DataFrame) -> np.ndarray:
    """Positive-class probability used throughout the docs' evaluation."""

    return pipeline.predict_proba(X)[:, 1]


def evaluate_model(
    pipeline: Pipeline,
    X_holdout: pd.DataFrame,
    y_holdout: pd.Series,
    model_name: str,
    *,
    n_bins: int = 10,
) -> ModelEvaluation:
    predicted_probability = predict_probability(pipeline, X_holdout)
    auc = roc_auc_score(y_holdout, predicted_probability)
    pr_auc = average_precision_score(y_holdout, predicted_probability)
    brier = brier_score_loss(y_holdout, predicted_probability)
    bin_true, bin_predicted = calibration_curve(
        y_holdout, predicted_probability, n_bins=n_bins, strategy="quantile"
    )
    return ModelEvaluation(model_name, auc, pr_auc, brier, bin_true, bin_predicted)


def _top_fraction_flagged_mask(
    predicted_probability: np.ndarray, top_fraction: float
) -> tuple[np.ndarray, float]:
    if not 0 < top_fraction <= 1:
        raise ValueError(f"top_fraction must be in (0, 1], got {top_fraction}")

    n_students = len(predicted_probability)
    flagged_students = max(1, int(np.floor(n_students * top_fraction)))
    ranking = np.argsort(predicted_probability)[::-1]
    flagged = np.zeros(n_students, dtype=bool)
    flagged[ranking[:flagged_students]] = True
    threshold_score = float(predicted_probability[ranking[flagged_students - 1]])
    return flagged, threshold_score


def evaluate_top_fraction(
    y_true: pd.Series | np.ndarray,
    predicted_probability: np.ndarray,
    *,
    top_fraction: float,
) -> TopFractionEvaluation:
    """Evaluate the ranking at the operational top-k cut used by triage."""

    y_array = np.asarray(y_true, dtype=bool)
    probability_array = np.asarray(predicted_probability, dtype=float)
    flagged, threshold_score = _top_fraction_flagged_mask(probability_array, top_fraction)

    true_positives = int(np.count_nonzero(flagged & y_array))
    actual_positives = int(np.count_nonzero(y_array))
    flagged_students = int(np.count_nonzero(flagged))
    base_rate = actual_positives / len(y_array)

    precision = true_positives / flagged_students if flagged_students else 0.0
    recall = true_positives / actual_positives if actual_positives else 0.0
    fnr = 1 - recall
    lift = precision / base_rate if base_rate else 0.0

    return TopFractionEvaluation(
        top_fraction=top_fraction,
        threshold_score=threshold_score,
        flagged_students=flagged_students,
        precision=precision,
        recall=recall,
        fnr=fnr,
        lift_vs_base_rate=lift,
    )


def _wilson_interval(successes: int, trials: int, *, z: float = 1.96) -> tuple[float, float]:
    if trials == 0:
        return float("nan"), float("nan")

    proportion = successes / trials
    denominator = 1 + z**2 / trials
    centre = (proportion + z**2 / (2 * trials)) / denominator
    margin = z * np.sqrt((proportion * (1 - proportion) / trials) + (z**2 / (4 * trials**2)))
    margin /= denominator
    return max(0.0, float(centre - margin)), min(1.0, float(centre + margin))


def audit_group_fairness(
    y_true: pd.Series | np.ndarray,
    predicted_probability: np.ndarray,
    group_memberships: dict[str, pd.Series | np.ndarray],
    *,
    top_fraction: float,
) -> pd.DataFrame:
    """Group-level calibration and threshold-dependent miss rates.

    The threshold is applied once at the full-cohort ranking level, then
    inspected within each group -- matching how a real capacity-constrained
    triage queue behaves.
    """

    y_array = np.asarray(y_true, dtype=bool)
    probability_array = np.asarray(predicted_probability, dtype=float)
    flagged, _threshold_score = _top_fraction_flagged_mask(probability_array, top_fraction)

    rows: list[dict[str, float | int | str]] = []
    for group_name, membership in group_memberships.items():
        mask = np.asarray(membership, dtype=bool)
        if len(mask) != len(y_array):
            raise ValueError(
                f"group '{group_name}' membership length {len(mask)} does not match "
                f"y_true length {len(y_array)}"
            )

        group_y = y_array[mask]
        group_probability = probability_array[mask]
        group_flagged = flagged[mask]

        n_students = int(np.count_nonzero(mask))
        n_attrited = int(np.count_nonzero(group_y))
        n_flagged = int(np.count_nonzero(group_flagged))
        true_positives = int(np.count_nonzero(group_flagged & group_y))
        false_negatives = n_attrited - true_positives

        observed_attrition = n_attrited / n_students if n_students else float("nan")
        mean_predicted = float(group_probability.mean()) if n_students else float("nan")
        fnr = false_negatives / n_attrited if n_attrited else float("nan")
        fnr_ci_low, fnr_ci_high = _wilson_interval(false_negatives, n_attrited)

        rows.append(
            {
                "group": group_name,
                "n_students": n_students,
                "attriters": n_attrited,
                "observed_attrition": observed_attrition,
                "mean_predicted": mean_predicted,
                "calibration_gap_pp": (mean_predicted - observed_attrition) * 100,
                "flagged_share": n_flagged / n_students if n_students else float("nan"),
                "threshold_fnr": fnr,
                "threshold_fnr_ci_low": fnr_ci_low,
                "threshold_fnr_ci_high": fnr_ci_high,
            }
        )

    return pd.DataFrame(rows)


def logistic_feature_importance(pipeline: Pipeline) -> pd.Series:
    """Standardized logistic coefficients -- comparable across features
    because `_build_preprocessor(scale_numeric=True)` z-scores every
    numeric column first."""

    encoded_names = pipeline.named_steps["preprocess"].get_feature_names_out()
    coefficients = pipeline.named_steps["model"].coef_[0]
    return pd.Series(coefficients, index=encoded_names).sort_values(
        key=lambda s: s.abs(), ascending=False
    )


def boosting_feature_importance(
    pipeline: Pipeline,
    X: pd.DataFrame,
    y: pd.Series,
    *,
    n_repeats: int = 10,
    random_state: int = 42,
) -> pd.Series:
    """Permutation importance on the *original* (pre-one-hot) feature
    columns -- `HistGradientBoostingClassifier` has no built-in
    `feature_importances_`, and permutation importance is measured against
    the holdout's own AUC, which is also what `docs/model_results.md`
    reports the model on."""

    result = permutation_importance(
        pipeline, X, y, n_repeats=n_repeats, random_state=random_state, scoring="roc_auc"
    )
    return pd.Series(result.importances_mean, index=X.columns).sort_values(ascending=False)
