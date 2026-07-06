"""Phase 4e: initiative-effect evaluation on top of triage policies.

Phase 4d answers "which students enter the queue?" Phase 4e answers
"what happens if a queue band receives a specific outreach intensity?"
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from equitylens_risk.triage import evaluate_selected_queue, summarize_group_queue


@dataclass(frozen=True, slots=True)
class InitiativeImpact:
    """Overall impact of one initiative applied to one selected cohort."""

    initiative_name: str
    effectiveness_rate: float
    targeted_students: int
    true_attriters_reached: int
    precision: float
    recall: float
    fnr: float
    expected_prevented_attritions: float
    prevented_per_100_slots: float


@dataclass(frozen=True, slots=True)
class GroupInitiativeImpact:
    """Group-specific impact of one initiative."""

    initiative_name: str
    effectiveness_rate: float
    group_students: int
    group_attriters: int
    flagged_students: int
    flagged_share: float
    true_attriters_reached: int
    recall: float
    fnr: float
    expected_prevented_attritions: float


def _validate_effectiveness_rate(effectiveness_rate: float) -> None:
    if not 0 <= effectiveness_rate <= 1:
        raise ValueError(f"effectiveness_rate must be in [0, 1], got {effectiveness_rate}")


def select_rank_band(
    predicted_probability: pd.Series | np.ndarray,
    *,
    start_fraction: float,
    end_fraction: float,
) -> np.ndarray:
    """Select an exclusive risk band, e.g. top 10-15% rather than top 15%.

    The bounds are half-open on rank: [start_fraction, end_fraction).
    """

    if not 0 <= start_fraction < end_fraction <= 1:
        raise ValueError("fractions must satisfy 0 <= start_fraction < end_fraction <= 1")

    probability_array = np.asarray(predicted_probability, dtype=float)
    ranking = np.argsort(probability_array)[::-1]
    n_students = len(probability_array)
    start_rank = int(np.floor(n_students * start_fraction))
    end_rank = int(np.floor(n_students * end_fraction))
    if end_rank <= start_rank:
        raise ValueError("selected band is empty; choose wider fractions or a larger cohort")

    selected = np.zeros(n_students, dtype=bool)
    selected[ranking[start_rank:end_rank]] = True
    return selected


def evaluate_initiative(
    initiative_name: str,
    y_true: pd.Series | np.ndarray,
    predicted_probability: pd.Series | np.ndarray,
    selected: pd.Series | np.ndarray,
    *,
    effectiveness_rate: float,
) -> InitiativeImpact:
    """Evaluate one initiative scenario against a selected queue or band."""

    _validate_effectiveness_rate(effectiveness_rate)
    queue = evaluate_selected_queue(y_true, predicted_probability, selected)
    expected_prevented = queue.true_positives * effectiveness_rate
    return InitiativeImpact(
        initiative_name=initiative_name,
        effectiveness_rate=effectiveness_rate,
        targeted_students=queue.selected_students,
        true_attriters_reached=queue.true_positives,
        precision=queue.precision,
        recall=queue.recall,
        fnr=queue.fnr,
        expected_prevented_attritions=expected_prevented,
        prevented_per_100_slots=(expected_prevented / queue.selected_students) * 100,
    )


def evaluate_group_initiative(
    initiative_name: str,
    y_true: pd.Series | np.ndarray,
    selected: pd.Series | np.ndarray,
    group_membership: pd.Series | np.ndarray,
    *,
    effectiveness_rate: float,
) -> GroupInitiativeImpact:
    """Evaluate one initiative's impact within a specific group."""

    _validate_effectiveness_rate(effectiveness_rate)
    group = summarize_group_queue(y_true, selected, group_membership)
    return GroupInitiativeImpact(
        initiative_name=initiative_name,
        effectiveness_rate=effectiveness_rate,
        group_students=group.group_students,
        group_attriters=group.group_attriters,
        flagged_students=group.flagged_students,
        flagged_share=group.flagged_share,
        true_attriters_reached=group.true_positives,
        recall=group.recall,
        fnr=group.fnr,
        expected_prevented_attritions=group.true_positives * effectiveness_rate,
    )
