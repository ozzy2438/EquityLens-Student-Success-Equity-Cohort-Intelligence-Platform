from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from equitylens_risk.triage import (
    evaluate_selected_queue,
    minimum_group_slots_for_fnr_target,
    select_top_n,
    select_with_group_floor,
    summarize_group_queue,
)


def test_select_top_n_picks_highest_scores() -> None:
    probabilities = np.array([0.1, 0.9, 0.8, 0.2, 0.7])

    selected = select_top_n(probabilities, n_slots=2)

    assert selected.tolist() == [False, True, True, False, False]


def test_select_with_group_floor_guarantees_minimum_group_slots() -> None:
    probabilities = np.array([0.95, 0.90, 0.40, 0.30, 0.20, 0.10])
    group = np.array([False, False, False, True, True, True])

    selected = select_with_group_floor(probabilities, group, n_slots=3, min_group_slots=2)

    assert int(selected.sum()) == 3
    assert int(selected[group].sum()) == 2
    assert selected.tolist() == [True, False, False, True, True, False]


def test_evaluate_selected_queue_reports_precision_recall_and_lift() -> None:
    y_true = pd.Series([1, 1, 0, 0, 1, 0])
    probabilities = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4])
    selected = np.array([True, True, False, False, False, False])

    evaluation = evaluate_selected_queue(y_true, probabilities, selected)

    assert evaluation.selected_students == 2
    assert evaluation.threshold_score == pytest.approx(0.8)
    assert evaluation.true_positives == 2
    assert evaluation.precision == pytest.approx(1.0)
    assert evaluation.recall == pytest.approx(2 / 3)
    assert evaluation.fnr == pytest.approx(1 / 3)
    assert evaluation.lift_vs_base_rate == pytest.approx(1.0 / 0.5)


def test_summarize_group_queue_reports_group_fnr_and_flagged_share() -> None:
    y_true = pd.Series([1, 0, 1, 0, 1, 0])
    selected = np.array([True, False, False, False, True, False])
    group = np.array([True, True, True, False, False, False])

    summary = summarize_group_queue(y_true, selected, group)

    assert summary.group_students == 3
    assert summary.group_attriters == 2
    assert summary.flagged_students == 1
    assert summary.flagged_share == pytest.approx(1 / 3)
    assert summary.true_positives == 1
    assert summary.recall == pytest.approx(0.5)
    assert summary.fnr == pytest.approx(0.5)


def test_minimum_group_slots_for_fnr_target_finds_smallest_working_floor() -> None:
    y_true = pd.Series([1, 1, 0, 0, 1, 0])
    probabilities = np.array([0.90, 0.85, 0.80, 0.70, 0.60, 0.50])
    group = np.array([False, False, False, True, True, True])

    # With 2 slots globally, the group gets none unless a floor is imposed.
    # A floor of 2 is the smallest one that catches the group's only attriter.
    result = minimum_group_slots_for_fnr_target(
        y_true, probabilities, group, n_slots=2, target_fnr=0.0
    )

    assert result == 2


def test_select_with_group_floor_rejects_invalid_lengths() -> None:
    with pytest.raises(ValueError, match="length"):
        select_with_group_floor(
            np.array([0.9, 0.8]), np.array([True]), n_slots=1, min_group_slots=1
        )
