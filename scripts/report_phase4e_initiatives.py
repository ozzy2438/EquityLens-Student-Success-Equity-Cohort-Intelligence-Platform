"""Print the Phase 4e initiative-evaluation snapshot used by the docs.

This is a reproducibility script, not a CLI surface: it rebuilds the current
train/holdout cohorts, fits the selected logistic model, then reports:

- a three-tier outreach ladder with initiative-specific effectiveness rates
- the expected prevented-attrition yield of each marginal band
- how the Tier-2 queue-policy alternatives change overall and NESB-specific
  expected impact under a common intervention effect rate
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from equitylens_risk.initiatives import (
    evaluate_group_initiative,
    evaluate_initiative,
    select_rank_band,
)
from equitylens_risk.models import fit_logistic_regression, predict_probability
from equitylens_risk.pipeline import build_train_holdout, features_and_labels
from equitylens_risk.triage import (
    evaluate_selected_queue,
    minimum_group_slots_for_fnr_target,
    select_top_n,
    select_with_group_floor,
)
from equitylens_synthetic.population import load_target_set

TARGET_SET_PATH = Path("data/calibration/targets_v3_2023ref.json")
N_STUDENTS = 20_000

TIER_BANDS = (
    {
        "initiative_name": "Tier 1 - case management",
        "band_label": "top_0_10pct",
        "start_fraction": 0.00,
        "end_fraction": 0.10,
        "effectiveness_rate": 0.15,
    },
    {
        "initiative_name": "Tier 2 - advisor outreach",
        "band_label": "top_10_15pct",
        "start_fraction": 0.10,
        "end_fraction": 0.15,
        "effectiveness_rate": 0.10,
    },
    {
        "initiative_name": "Tier 3 - digital nudge",
        "band_label": "top_15_20pct",
        "start_fraction": 0.15,
        "end_fraction": 0.20,
        "effectiveness_rate": 0.05,
    },
)
TIER2_EFFECTIVENESS_RATE = 0.10


def main() -> None:
    target_set = load_target_set(TARGET_SET_PATH)
    train, holdout = build_train_holdout(target_set, n_students=N_STUDENTS)
    X_train, y_train = features_and_labels(train)
    X_holdout, y_holdout = features_and_labels(holdout)
    model = fit_logistic_regression(X_train, y_train)
    probabilities = pd.Series(predict_probability(model, X_holdout), index=holdout.index)
    nesb_mask = holdout["non_english_speaking_background"].astype(bool)

    print("Tier-band initiative ladder")
    band_rows = []
    for tier in TIER_BANDS:
        selected = pd.Series(
            select_rank_band(
                probabilities,
                start_fraction=tier["start_fraction"],
                end_fraction=tier["end_fraction"],
            ),
            index=holdout.index,
        )
        impact = evaluate_initiative(
            tier["initiative_name"],
            y_holdout,
            probabilities,
            selected,
            effectiveness_rate=tier["effectiveness_rate"],
        )
        band_rows.append(
            {
                "initiative_name": impact.initiative_name,
                "band_label": tier["band_label"],
                "slots": impact.targeted_students,
                "precision": impact.precision,
                "recall": impact.recall,
                "fnr": impact.fnr,
                "true_attriters_reached": impact.true_attriters_reached,
                "effectiveness_rate": impact.effectiveness_rate,
                "expected_prevented_attritions": impact.expected_prevented_attritions,
                "prevented_per_100_slots": impact.prevented_per_100_slots,
            }
        )
    band_df = pd.DataFrame(band_rows)
    blended_total = float(band_df["expected_prevented_attritions"].sum())
    band_df["share_of_blended_program_impact"] = (
        band_df["expected_prevented_attritions"] / blended_total
    )
    print(band_df.to_csv(index=False))
    print(f"blended_total_expected_prevented_attritions={blended_total:.1f}")

    print("Tier-2 policy alternatives under common 10% intervention effect")
    slots = int(N_STUDENTS * 0.15)
    global_selected = pd.Series(
        select_top_n(probabilities.to_numpy(), n_slots=slots), index=holdout.index
    )
    global_queue = evaluate_selected_queue(y_holdout, probabilities, global_selected)

    nesb_floor_slots = int(nesb_mask.sum() * 0.15)
    floor_selected = pd.Series(
        select_with_group_floor(
            probabilities.to_numpy(),
            nesb_mask.to_numpy(),
            n_slots=slots,
            min_group_slots=nesb_floor_slots,
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
    parity_selected = pd.Series(
        select_with_group_floor(
            probabilities.to_numpy(),
            nesb_mask.to_numpy(),
            n_slots=slots,
            min_group_slots=parity_floor_slots,
        ),
        index=holdout.index,
    )

    policy_rows = []
    for label, selected in [
        ("A_global_top15", global_selected),
        ("B_nesb_floor_15pct_within_group", floor_selected),
        (f"C_nesb_fnr_parity_floor_{parity_floor_slots}_slots", parity_selected),
    ]:
        initiative = evaluate_initiative(
            label,
            y_holdout,
            probabilities,
            selected,
            effectiveness_rate=TIER2_EFFECTIVENESS_RATE,
        )
        nesb = evaluate_group_initiative(
            label,
            y_holdout,
            selected,
            nesb_mask,
            effectiveness_rate=TIER2_EFFECTIVENESS_RATE,
        )
        policy_rows.append(
            {
                "policy": label,
                "slots": initiative.targeted_students,
                "overall_precision": initiative.precision,
                "overall_true_attriters_reached": initiative.true_attriters_reached,
                "overall_expected_prevented": initiative.expected_prevented_attritions,
                "nesb_flagged_share": nesb.flagged_share,
                "nesb_true_attriters_reached": nesb.true_attriters_reached,
                "nesb_expected_prevented": nesb.expected_prevented_attritions,
            }
        )
    policy_df = pd.DataFrame(policy_rows)
    baseline_overall = float(policy_df.loc[0, "overall_expected_prevented"])
    baseline_nesb = float(policy_df.loc[0, "nesb_expected_prevented"])
    policy_df["delta_overall_prevented_vs_global"] = (
        policy_df["overall_expected_prevented"] - baseline_overall
    )
    policy_df["delta_nesb_prevented_vs_global"] = (
        policy_df["nesb_expected_prevented"] - baseline_nesb
    )
    print(policy_df.to_csv(index=False))


if __name__ == "__main__":
    main()
