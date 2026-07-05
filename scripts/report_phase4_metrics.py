"""Print the Phase 4b/4c model snapshot used by docs/model_results.md.

Kept as a lightweight script rather than a CLI entrypoint because it is a
documentation reproducibility aid, not a user-facing product surface.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from equitylens_risk.models import (
    audit_group_fairness,
    boosting_feature_importance,
    evaluate_model,
    evaluate_top_fraction,
    fit_gradient_boosting,
    fit_logistic_regression,
    logistic_feature_importance,
    predict_probability,
)
from equitylens_risk.pipeline import build_train_holdout, features_and_labels

TARGET_SET_PATH = Path("data/calibration/targets_v3_2023ref.json")
N_STUDENTS = 20_000


def _group_memberships(population: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "all_students": pd.Series(True, index=population.index),
        "low_ses": population["low_ses"].astype(bool),
        "first_nations": population["first_nations"].astype(bool),
        "disability": population["disability"].astype(bool),
        "nesb": population["non_english_speaking_background"].astype(bool),
        "women_non_traditional_area": population["women_non_traditional_area"].astype(bool),
        "first_in_family": population["first_in_family"].astype(bool),
        "regional": population["geography"].eq("regional"),
        "remote": population["geography"].eq("remote"),
        "metro": population["geography"].eq("metro"),
    }


def main() -> None:
    target_set = json.loads(TARGET_SET_PATH.read_text())
    train, holdout = build_train_holdout(target_set, N_STUDENTS)
    X_train, y_train = features_and_labels(train)
    X_holdout, y_holdout = features_and_labels(holdout)

    logistic = fit_logistic_regression(X_train, y_train)
    boosting = fit_gradient_boosting(X_train, y_train)

    logistic_eval = evaluate_model(logistic, X_holdout, y_holdout, "logistic_regression")
    boosting_eval = evaluate_model(boosting, X_holdout, y_holdout, "gradient_boosting")

    logistic_probability = predict_probability(logistic, X_holdout)

    print("Headline metrics")
    for evaluation in [logistic_eval, boosting_eval]:
        print(
            f"{evaluation.model_name}: AUC={evaluation.auc:.4f}, "
            f"PR-AUC={evaluation.pr_auc:.4f}, Brier={evaluation.brier_score:.4f}"
        )
    print(f"Holdout base rate: {y_holdout.mean():.4f}")
    print()

    print("Top-fraction triage")
    for share in [0.10, 0.15, 0.20]:
        top_eval = evaluate_top_fraction(y_holdout, logistic_probability, top_fraction=share)
        print(
            f"top {share:.0%}: threshold={top_eval.threshold_score:.4f}, "
            f"precision={top_eval.precision:.4f}, recall={top_eval.recall:.4f}, "
            f"fnr={top_eval.fnr:.4f}, lift={top_eval.lift_vs_base_rate:.4f}"
        )
    print()

    print("Group fairness audit at top 15%")
    fairness = audit_group_fairness(
        y_holdout,
        logistic_probability,
        _group_memberships(holdout),
        top_fraction=0.15,
    )
    print(
        fairness[
            [
                "group",
                "n_students",
                "attriters",
                "observed_attrition",
                "mean_predicted",
                "calibration_gap_pp",
                "flagged_share",
                "threshold_fnr",
                "threshold_fnr_ci_low",
                "threshold_fnr_ci_high",
            ]
        ].to_csv(index=False)
    )

    print("Logistic importance")
    print(logistic_feature_importance(logistic).head(10).to_string())
    print()
    print("Boosting importance")
    print(boosting_feature_importance(boosting, X_holdout, y_holdout).head(10).to_string())


if __name__ == "__main__":
    main()
