"""Phase 4d: capacity-constrained triage policy helpers.

The risk model outputs a ranking; these helpers turn that ranking into
queue-selection policies so Phase 4d can compare operational designs
without refitting the model itself.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class QueueEvaluation:
    """Outcome of one concrete queue-selection policy."""

    selected_students: int
    threshold_score: float
    true_positives: int
    precision: float
    recall: float
    fnr: float
    lift_vs_base_rate: float


@dataclass(frozen=True, slots=True)
class GroupQueueSummary:
    """How one group's students fare under a concrete queue selection."""

    group_students: int
    group_attriters: int
    flagged_students: int
    flagged_share: float
    true_positives: int
    recall: float
    fnr: float


def _validate_slots(n_students: int, n_slots: int) -> None:
    if n_slots <= 0:
        raise ValueError(f"n_slots must be positive, got {n_slots}")
    if n_slots > n_students:
        raise ValueError(f"n_slots must be <= number of students ({n_students}), got {n_slots}")


def select_top_n(predicted_probability: np.ndarray, *, n_slots: int) -> np.ndarray:
    """Select the highest-risk `n_slots` students globally."""

    probability_array = np.asarray(predicted_probability, dtype=float)
    _validate_slots(len(probability_array), n_slots)

    ranking = np.argsort(probability_array)[::-1]
    selected = np.zeros(len(probability_array), dtype=bool)
    selected[ranking[:n_slots]] = True
    return selected


def select_with_group_floor(
    predicted_probability: np.ndarray,
    group_membership: pd.Series | np.ndarray,
    *,
    n_slots: int,
    min_group_slots: int,
) -> np.ndarray:
    """Guarantee a minimum number of slots for one group, then fill the
    rest globally by score.

    This is the least efficiency-destructive way to impose a floor: after
    satisfying the group minimum, every remaining slot still goes to the
    highest unselected score in the full cohort.
    """

    probability_array = np.asarray(predicted_probability, dtype=float)
    membership_array = np.asarray(group_membership, dtype=bool)
    if len(membership_array) != len(probability_array):
        raise ValueError("group_membership must match predicted_probability length")
    _validate_slots(len(probability_array), n_slots)
    if min_group_slots < 0:
        raise ValueError(f"min_group_slots must be non-negative, got {min_group_slots}")

    group_size = int(np.count_nonzero(membership_array))
    if min_group_slots > group_size:
        raise ValueError(
            f"min_group_slots must be <= group size ({group_size}), got {min_group_slots}"
        )
    if min_group_slots > n_slots:
        raise ValueError(f"min_group_slots must be <= n_slots ({n_slots}), got {min_group_slots}")

    selected = np.zeros(len(probability_array), dtype=bool)
    group_indices = np.where(membership_array)[0]
    group_ranking = group_indices[np.argsort(probability_array[group_indices])[::-1]]
    selected[group_ranking[:min_group_slots]] = True

    remaining_slots = n_slots - int(np.count_nonzero(selected))
    if remaining_slots:
        remaining_ranking = np.argsort(np.where(selected, -np.inf, probability_array))[::-1]
        selected[remaining_ranking[:remaining_slots]] = True
    return selected


def evaluate_selected_queue(
    y_true: pd.Series | np.ndarray,
    predicted_probability: np.ndarray,
    selected: pd.Series | np.ndarray,
) -> QueueEvaluation:
    """Evaluate a concrete selected queue rather than a percentile cut."""

    y_array = np.asarray(y_true, dtype=bool)
    probability_array = np.asarray(predicted_probability, dtype=float)
    selected_array = np.asarray(selected, dtype=bool)
    if len(y_array) != len(probability_array) or len(y_array) != len(selected_array):
        raise ValueError("y_true, predicted_probability, and selected must have equal length")

    selected_students = int(np.count_nonzero(selected_array))
    _validate_slots(len(y_array), selected_students)
    true_positives = int(np.count_nonzero(selected_array & y_array))
    actual_positives = int(np.count_nonzero(y_array))
    base_rate = actual_positives / len(y_array)

    precision = true_positives / selected_students
    recall = true_positives / actual_positives if actual_positives else 0.0
    fnr = 1 - recall
    threshold_score = float(probability_array[selected_array].min())
    lift = precision / base_rate if base_rate else 0.0

    return QueueEvaluation(
        selected_students=selected_students,
        threshold_score=threshold_score,
        true_positives=true_positives,
        precision=precision,
        recall=recall,
        fnr=fnr,
        lift_vs_base_rate=lift,
    )


def summarize_group_queue(
    y_true: pd.Series | np.ndarray,
    selected: pd.Series | np.ndarray,
    group_membership: pd.Series | np.ndarray,
) -> GroupQueueSummary:
    """Summarize one group's queue exposure under a concrete selection."""

    y_array = np.asarray(y_true, dtype=bool)
    selected_array = np.asarray(selected, dtype=bool)
    membership_array = np.asarray(group_membership, dtype=bool)
    if len(y_array) != len(selected_array) or len(y_array) != len(membership_array):
        raise ValueError("y_true, selected, and group_membership must have equal length")

    group_y = y_array[membership_array]
    group_selected = selected_array[membership_array]
    group_students = int(np.count_nonzero(membership_array))
    group_attriters = int(np.count_nonzero(group_y))
    flagged_students = int(np.count_nonzero(group_selected))
    true_positives = int(np.count_nonzero(group_selected & group_y))
    recall = true_positives / group_attriters if group_attriters else 0.0
    fnr = 1 - recall if group_attriters else 0.0

    return GroupQueueSummary(
        group_students=group_students,
        group_attriters=group_attriters,
        flagged_students=flagged_students,
        flagged_share=flagged_students / group_students if group_students else 0.0,
        true_positives=true_positives,
        recall=recall,
        fnr=fnr,
    )


def minimum_group_slots_for_fnr_target(
    y_true: pd.Series | np.ndarray,
    predicted_probability: np.ndarray,
    group_membership: pd.Series | np.ndarray,
    *,
    n_slots: int,
    target_fnr: float,
) -> int:
    """Find the smallest group floor that achieves the requested group FNR."""

    if not 0 <= target_fnr <= 1:
        raise ValueError(f"target_fnr must be in [0, 1], got {target_fnr}")

    probability_array = np.asarray(predicted_probability, dtype=float)
    membership_array = np.asarray(group_membership, dtype=bool)
    max_group_slots = min(int(np.count_nonzero(membership_array)), n_slots)

    for group_slots in range(max_group_slots + 1):
        selected = select_with_group_floor(
            probability_array,
            membership_array,
            n_slots=n_slots,
            min_group_slots=group_slots,
        )
        group_summary = summarize_group_queue(y_true, selected, membership_array)
        if group_summary.fnr <= target_fnr:
            return group_slots

    return max_group_slots
