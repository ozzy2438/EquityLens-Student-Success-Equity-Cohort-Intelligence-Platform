from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from equitylens_risk.initiatives import (
    evaluate_group_initiative,
    evaluate_initiative,
    select_rank_band,
)


def test_select_rank_band_picks_exclusive_slice() -> None:
    probabilities = np.array([0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50])

    selected = select_rank_band(probabilities, start_fraction=0.2, end_fraction=0.5)

    assert selected.tolist() == [
        False,
        False,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
    ]


def test_select_rank_band_rejects_invalid_bounds() -> None:
    with pytest.raises(ValueError, match="fractions must satisfy"):
        select_rank_band(np.array([0.9, 0.8]), start_fraction=0.5, end_fraction=0.5)


def test_evaluate_initiative_computes_expected_prevented_attritions() -> None:
    y_true = pd.Series([1, 1, 0, 0, 1, 0])
    probabilities = np.array([0.90, 0.85, 0.80, 0.70, 0.60, 0.50])
    selected = np.array([True, True, False, False, False, False])

    impact = evaluate_initiative(
        "case_management",
        y_true,
        probabilities,
        selected,
        effectiveness_rate=0.15,
    )

    assert impact.initiative_name == "case_management"
    assert impact.targeted_students == 2
    assert impact.true_attriters_reached == 2
    assert impact.precision == pytest.approx(1.0)
    assert impact.expected_prevented_attritions == pytest.approx(0.30)
    assert impact.prevented_per_100_slots == pytest.approx(15.0)


def test_evaluate_group_initiative_computes_group_specific_prevention() -> None:
    y_true = pd.Series([1, 0, 1, 0, 1, 0])
    selected = np.array([True, False, False, False, True, False])
    group = np.array([True, True, True, False, False, False])

    impact = evaluate_group_initiative(
        "advisor_outreach",
        y_true,
        selected,
        group,
        effectiveness_rate=0.10,
    )

    assert impact.group_students == 3
    assert impact.group_attriters == 2
    assert impact.flagged_students == 1
    assert impact.true_attriters_reached == 1
    assert impact.recall == pytest.approx(0.5)
    assert impact.fnr == pytest.approx(0.5)
    assert impact.expected_prevented_attritions == pytest.approx(0.10)


def test_evaluate_initiative_rejects_invalid_effectiveness() -> None:
    with pytest.raises(ValueError, match="effectiveness_rate"):
        evaluate_initiative(
            "bad",
            pd.Series([1, 0]),
            np.array([0.9, 0.1]),
            np.array([True, False]),
            effectiveness_rate=1.5,
        )
