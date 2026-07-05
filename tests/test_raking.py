from __future__ import annotations

import pandas as pd
import pytest

from equitylens_synthetic.errors import MarginConfigurationError
from equitylens_synthetic.raking import integerize, rake


def test_rake_2x2_exact_solvable_case_matches_independence_solution() -> None:
    # Classic textbook IPF case: uniform seed + consistent margins (both sum
    # to 100) has a known closed-form solution when there are only two
    # dimensions -- the independent joint distribution.
    seed = pd.DataFrame(
        {
            "sex": ["M", "M", "F", "F"],
            "region": ["A", "B", "A", "B"],
            "weight": [1.0, 1.0, 1.0, 1.0],
        }
    )
    margins = {"sex": {"M": 60.0, "F": 40.0}, "region": {"A": 70.0, "B": 30.0}}
    weights, report = rake(seed, margins, tolerance=1e-9, max_iter=200)

    assert report.converged is True
    expected = {0: 42.0, 1: 18.0, 2: 28.0, 3: 12.0}  # M/A, M/B, F/A, F/B
    for index, value in expected.items():
        assert weights[index] == pytest.approx(value, abs=1e-6)


def test_rake_3x3_solvable_case_converges_to_exact_margins() -> None:
    levels = ["a", "b", "c"]
    rows = [(x, y) for x in levels for y in levels]
    seed = pd.DataFrame(
        {
            "dim1": [r[0] for r in rows],
            "dim2": [r[1] for r in rows],
            "weight": [1.0] * len(rows),
        }
    )
    margins = {
        "dim1": {"a": 500.0, "b": 300.0, "c": 200.0},
        "dim2": {"a": 400.0, "b": 400.0, "c": 200.0},
    }
    weights, report = rake(seed, margins, tolerance=1e-9, max_iter=500)

    assert report.converged is True
    seed = seed.assign(weight=weights)
    for dim, targets in margins.items():
        for level, target in targets.items():
            actual = seed.loc[seed[dim] == level, "weight"].sum()
            assert actual == pytest.approx(target, abs=1e-4)


def test_rake_reports_structural_zero_when_seed_has_no_cell_for_a_target_level() -> None:
    # The seed table has no "remote" cell at all, but a positive target is
    # requested for it -- IPF cannot invent weight from nothing, so this must
    # be reported, not silently ignored or treated as a bug to raise on.
    seed = pd.DataFrame({"geo": ["metro", "regional"], "weight": [1.0, 1.0]})
    margins = {"geo": {"metro": 80.0, "regional": 15.0, "remote": 5.0}}
    _weights, report = rake(seed, margins, tolerance=1e-6, max_iter=50)

    assert report.converged is False
    assert "geo=remote" in report.structural_zero_margins


def test_rake_reports_non_convergence_when_max_iter_is_too_low() -> None:
    # A perfectly uniform seed converges in a single sweep regardless of
    # dimensionality (it has no interaction structure to disturb), so forcing
    # non-convergence needs a seed with real cell-to-cell variation: raking
    # dim2 to its margin then disturbs the already-matched dim1 totals,
    # genuinely requiring multiple sweeps before the worst deviation clears a
    # tight tolerance.
    seed = pd.DataFrame(
        {
            "dim1": ["a", "a", "b", "b", "c", "c"],
            "dim2": ["x", "y", "x", "y", "x", "y"],
            "weight": [5.0, 1.0, 1.0, 5.0, 3.0, 3.0],
        }
    )
    margins = {"dim1": {"a": 500.0, "b": 300.0, "c": 200.0}, "dim2": {"x": 600.0, "y": 400.0}}
    _weights, report = rake(seed, margins, tolerance=1e-12, max_iter=1)
    assert report.converged is False
    assert report.iterations == 1
    assert report.max_relative_deviation > 1e-12

    _weights_full, report_full = rake(seed, margins, tolerance=1e-9, max_iter=200)
    assert report_full.converged is True
    assert report_full.iterations > 1


def test_rake_supports_excluding_imputed_targets_by_omitting_them_from_margins() -> None:
    # Callers decide whether an imputed target participates as a hard
    # constraint by including or excluding it from `margins` before calling
    # rake() -- rake() itself has no concept of "imputed".
    seed = pd.DataFrame({"geo": ["metro", "regional", "remote"], "weight": [1.0, 1.0, 1.0]})

    strict_margins = {"geo": {"metro": 88.0, "regional": 11.0, "remote": 1.0}}
    _weights_strict, report_strict = rake(seed, strict_margins, tolerance=1e-9, max_iter=100)
    assert report_strict.converged is True

    loose_margins = {"geo": {"metro": 88.0, "regional": 11.0}}  # remote excluded
    weights_loose, report_loose = rake(seed, loose_margins, tolerance=1e-9, max_iter=100)
    assert report_loose.converged is True
    # The excluded level's weight is untouched by raking (still its seed value).
    assert weights_loose[2] == pytest.approx(1.0)


def test_rake_rejects_margin_dimension_missing_from_seed_table() -> None:
    seed = pd.DataFrame({"geo": ["metro"], "weight": [1.0]})
    with pytest.raises(MarginConfigurationError, match="first_nations"):
        rake(seed, {"first_nations": {"yes": 1.0}})


def test_integerize_sums_exactly_to_total_and_minimises_rounding_error() -> None:
    seed = pd.DataFrame({"geo": ["metro", "regional", "remote"]})
    weights = pd.Series([88.4, 10.6, 1.0])
    counts, report = integerize(seed, weights, total_students=100, margins={"geo": {}})

    assert counts.sum() == 100
    assert report.total_students == 100
    # Largest-remainder method: 88.4 -> 88, 10.6 -> 11 (largest fractional
    # remainder gets the leftover unit), 1.0 -> 1.
    assert list(counts) == [88, 11, 1]


def test_integerize_reports_residual_deviation_after_rounding() -> None:
    seed = pd.DataFrame({"geo": ["metro", "regional"]})
    weights = pd.Series([2.5, 2.5])
    margins = {"geo": {"metro": 2.5, "regional": 2.5}}
    _counts, report = integerize(seed, weights, total_students=5, margins=margins)
    # 2.5/2.5 scaled to sum to 5 stays 2.5/2.5; rounding to integers (2 and 3,
    # order depends on remainder tie-break) cannot both equal 2.5 exactly.
    assert any(deviation > 0 for deviation in report.deviation_by_margin_after_rounding.values())
