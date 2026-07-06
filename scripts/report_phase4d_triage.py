"""Print the Phase 4d triage-policy snapshot used by the docs.

This is a reproducibility script, not a CLI surface: it rebuilds the current
train/holdout cohorts, fits the selected logistic model, then reports:

- Tier 1/2/3 queue quality
- expected prevented attritions under simple outreach-effectiveness scenarios
- NESB-focused triage-policy alternatives
- a 10-holdout stability check for remote calibration
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from equitylens_risk.models import (
    evaluate_top_fraction,
    fit_logistic_regression,
    predict_probability,
)
from equitylens_risk.pipeline import build_cohort, build_train_holdout, features_and_labels
from equitylens_risk.triage import (
    evaluate_selected_queue,
    minimum_group_slots_for_fnr_target,
    select_top_n,
    select_with_group_floor,
    summarize_group_queue,
)
from equitylens_synthetic.population import load_target_set

TARGET_SET_PATH = Path("data/calibration/targets_v3_2023ref.json")
N_STUDENTS = 20_000
TOP_FRACTIONS = (0.10, 0.15, 0.20)
REMOTE_MULTI_SEED_BASES = tuple(range(777, 787))


def _policy_summary(
    *,
    label: str,
    y_holdout: pd.Series,
    probabilities: pd.Series,
    nesb_mask: pd.Series,
    selected: pd.Series,
    baseline_true_positives: int,
) -> dict[str, float | int | str]:
    queue = evaluate_selected_queue(y_holdout, probabilities, selected)
    nesb = summarize_group_queue(y_holdout, selected, nesb_mask)
    return {
        "policy": label,
        "slots": queue.selected_students,
        "overall_precision": queue.precision,
        "overall_recall": queue.recall,
        "overall_fnr": queue.fnr,
        "overall_true_attriters_reached": queue.true_positives,
        "expected_prevented_10pct": queue.true_positives * 0.10,
        "nesb_slots": nesb.flagged_students,
        "nesb_flagged_share": nesb.flagged_share,
        "nesb_attriters_reached": nesb.true_positives,
        "nesb_fnr": nesb.fnr,
        "delta_overall_tp_vs_global": queue.true_positives - baseline_true_positives,
        "delta_expected_prevented_10pct_vs_global": (queue.true_positives - baseline_true_positives)
        * 0.10,
    }


def main() -> None:
    target_set = load_target_set(TARGET_SET_PATH)
    train, holdout = build_train_holdout(target_set, n_students=N_STUDENTS)
    X_train, y_train = features_and_labels(train)
    X_holdout, y_holdout = features_and_labels(holdout)
    model = fit_logistic_regression(X_train, y_train)
    probabilities = pd.Series(predict_probability(model, X_holdout), index=holdout.index)
    nesb_mask = holdout["non_english_speaking_background"].astype(bool)
    remote_mask = holdout["geography"].eq("remote")

    print("Tier table")
    for fraction in TOP_FRACTIONS:
        evaluation = evaluate_top_fraction(
            y_holdout, probabilities.to_numpy(), top_fraction=fraction
        )
        reached = round(evaluation.precision * evaluation.flagged_students)
        print(
            ",".join(
                [
                    f"tier=top_{int(fraction * 100)}pct",
                    f"slots={evaluation.flagged_students}",
                    f"threshold={evaluation.threshold_score:.4f}",
                    f"precision={evaluation.precision:.4f}",
                    f"recall={evaluation.recall:.4f}",
                    f"fnr={evaluation.fnr:.4f}",
                    f"lift={evaluation.lift_vs_base_rate:.4f}",
                    f"true_attriters_reached={reached}",
                    f"prevented_5pct={reached * 0.05:.1f}",
                    f"prevented_10pct={reached * 0.10:.1f}",
                    f"prevented_15pct={reached * 0.15:.1f}",
                ]
            )
        )

    slots = int(N_STUDENTS * 0.15)
    global_selected = pd.Series(
        select_top_n(probabilities.to_numpy(), n_slots=slots), index=holdout.index
    )
    global_queue = evaluate_selected_queue(y_holdout, probabilities, global_selected)
    global_nesb = summarize_group_queue(y_holdout, global_selected, nesb_mask)

    nesb_floor_population = int(nesb_mask.sum() * 0.15)
    population_floor_selected = pd.Series(
        select_with_group_floor(
            probabilities.to_numpy(),
            nesb_mask.to_numpy(),
            n_slots=slots,
            min_group_slots=nesb_floor_population,
        ),
        index=holdout.index,
    )
    parity_floor_slots = minimum_group_slots_for_fnr_target(
        y_holdout,
        probabilities,
        nesb_mask,
        n_slots=slots,
        target_fnr=global_queue.fnr,
    )
    parity_floor_selected = pd.Series(
        select_with_group_floor(
            probabilities.to_numpy(),
            nesb_mask.to_numpy(),
            n_slots=slots,
            min_group_slots=parity_floor_slots,
        ),
        index=holdout.index,
    )

    print("\nTier-2 policy alternatives (NESB-focused)")
    rows = [
        {
            "policy": "A_global_top15",
            "slots": global_queue.selected_students,
            "overall_precision": global_queue.precision,
            "overall_recall": global_queue.recall,
            "overall_fnr": global_queue.fnr,
            "overall_true_attriters_reached": global_queue.true_positives,
            "expected_prevented_10pct": global_queue.true_positives * 0.10,
            "nesb_slots": global_nesb.flagged_students,
            "nesb_flagged_share": global_nesb.flagged_share,
            "nesb_attriters_reached": global_nesb.true_positives,
            "nesb_fnr": global_nesb.fnr,
            "delta_overall_tp_vs_global": 0,
            "delta_expected_prevented_10pct_vs_global": 0.0,
        },
        _policy_summary(
            label="B_nesb_floor_15pct_within_group",
            y_holdout=y_holdout,
            probabilities=probabilities,
            nesb_mask=nesb_mask,
            selected=population_floor_selected,
            baseline_true_positives=global_queue.true_positives,
        ),
        _policy_summary(
            label=f"C_nesb_fnr_parity_floor_{parity_floor_slots}_slots",
            y_holdout=y_holdout,
            probabilities=probabilities,
            nesb_mask=nesb_mask,
            selected=parity_floor_selected,
            baseline_true_positives=global_queue.true_positives,
        ),
    ]
    print(pd.DataFrame(rows).to_csv(index=False))

    print("Remote calibration stability check (10 holdouts, fixed train model)")
    remote_rows = []
    for seed_base in REMOTE_MULTI_SEED_BASES:
        holdout_seed = {
            "population_seed": seed_base,
            "latent_seed": seed_base * 100 + 11,
            "outcome_seed": seed_base,
            "census_seed": seed_base * 100 + 97,
        }
        remote_holdout = build_cohort(
            target_set,
            N_STUDENTS,
            institution_id="acu",
            **holdout_seed,
        )
        X_remote_holdout, _y_remote_holdout = features_and_labels(remote_holdout)
        remote_probability = pd.Series(
            predict_probability(model, X_remote_holdout), index=remote_holdout.index
        )
        current_remote_mask = remote_holdout["geography"].eq("remote")
        observed = (~remote_holdout.loc[current_remote_mask, "retained"]).mean()
        predicted = remote_probability.loc[current_remote_mask].mean()
        remote_rows.append(
            {
                "seed": seed_base,
                "remote_students": int(current_remote_mask.sum()),
                "remote_attriters": int(
                    (~remote_holdout.loc[current_remote_mask, "retained"]).sum()
                ),
                "observed_attrition": observed,
                "mean_predicted": predicted,
                "calibration_gap_pp": (predicted - observed) * 100,
            }
        )
    remote_df = pd.DataFrame(remote_rows)
    print(remote_df.to_csv(index=False))
    print(remote_df["calibration_gap_pp"].describe().to_string())
    remote_top15 = summarize_group_queue(y_holdout, global_selected, remote_mask)
    print(f"single_holdout_remote_flagged_share_top15={remote_top15.flagged_share:.4f}")


if __name__ == "__main__":
    main()
