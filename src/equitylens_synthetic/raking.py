"""Iterative Proportional Fitting (raking), written from scratch rather than
taken from a library.

Three reasons, in order of importance for this project: (1) the available
Python IPF packages are either unmaintained or built for survey-weighting
use cases that bring more machinery than this needs; (2) this project's
margins are not uniformly "hard" -- some are directly observed, some are
imputed from a sector average when a publisher cell was suppressed
(`imputed_target_flag` in `docs/calibration_targets.md`), and a library has
no way to know which target should be treated as a loose vs. a strict
constraint, a decision that belongs in `population.py`, not here; (3) the
algorithm itself is ~50 lines of well-understood arithmetic -- writing it
means every convergence property below is something this project can
explain, not something imported.

Algorithm: classic raking/IPF. For each dimension in turn, for each level of
that dimension, scale every seed cell's weight so that the level's total
matches its target margin. Repeat across all dimensions until the worst
relative deviation across every margin is within tolerance, or `max_iter` is
reached without converging.
"""

from __future__ import annotations

import pandas as pd

from equitylens_synthetic.errors import MarginConfigurationError
from equitylens_synthetic.models import ConvergenceReport, IntegerizationReport

Margins = dict[str, dict[str, float]]


def _validate_margins(seed_table: pd.DataFrame, margins: Margins) -> None:
    for dimension in margins:
        if dimension not in seed_table.columns:
            raise MarginConfigurationError(
                f"Margin dimension {dimension!r} is not a column of the seed table"
            )


def _find_structural_zeros(
    seed_table: pd.DataFrame, margins: Margins, weights: pd.Series
) -> tuple[str, ...]:
    zeros = []
    for dimension, target_by_level in margins.items():
        for level, target in target_by_level.items():
            if target <= 0:
                continue
            mask = seed_table[dimension] == level
            if weights[mask].sum() == 0:
                zeros.append(f"{dimension}={level}")
    return tuple(zeros)


def _max_relative_deviation(
    seed_table: pd.DataFrame, margins: Margins, weights: pd.Series
) -> tuple[float, dict[str, float]]:
    max_deviation = 0.0
    deviation_by_margin: dict[str, float] = {}
    for dimension, target_by_level in margins.items():
        for level, target in target_by_level.items():
            if target <= 0:
                continue
            mask = seed_table[dimension] == level
            current = weights[mask].sum()
            relative_deviation = abs(current - target) / target
            deviation_by_margin[f"{dimension}={level}"] = relative_deviation
            max_deviation = max(max_deviation, relative_deviation)
    return max_deviation, deviation_by_margin


def rake(
    seed_table: pd.DataFrame,
    margins: Margins,
    *,
    weight_col: str = "weight",
    tolerance: float = 0.001,
    max_iter: int = 50,
) -> tuple[pd.Series, ConvergenceReport]:
    """Adjust `seed_table[weight_col]` so every margin's total matches its
    target, returning the adjusted weights and a convergence report.

    `margins` maps a dimension (a column in `seed_table`) to a mapping of
    level -> target total. A level with target 0 is skipped for convergence
    purposes (dividing by a zero target is meaningless; a genuine "this
    level should have zero weight" constraint is handled by the seed table
    simply not containing that level, not by a zero-target margin).
    """

    _validate_margins(seed_table, margins)
    weights = seed_table[weight_col].astype(float).copy()
    structural_zeros = _find_structural_zeros(seed_table, margins, weights)

    _completed_iterations = 0
    max_deviation = float("inf")
    deviation_by_margin: dict[str, float] = {}
    for _completed_iterations in range(1, max_iter + 1):
        for dimension, target_by_level in margins.items():
            for level, target in target_by_level.items():
                if target <= 0:
                    continue
                mask = seed_table[dimension] == level
                current = weights[mask].sum()
                if current == 0:
                    continue  # structural zero, already recorded; cannot rake
                weights[mask] *= target / current

        max_deviation, deviation_by_margin = _max_relative_deviation(seed_table, margins, weights)
        if max_deviation <= tolerance:
            break

    return weights, ConvergenceReport(
        converged=bool(max_deviation <= tolerance),
        iterations=_completed_iterations,
        max_relative_deviation=float(max_deviation),
        deviation_by_margin={k: float(v) for k, v in deviation_by_margin.items()},
        structural_zero_margins=structural_zeros,
    )


def integerize(
    seed_table: pd.DataFrame,
    weights: pd.Series,
    *,
    total_students: int,
    margins: Margins,
) -> tuple[pd.Series, IntegerizationReport]:
    """Convert continuous raked weights into integer per-cell student counts
    summing exactly to `total_students`, using the largest-remainder method
    (Hare quota): scale weights to sum to the target, floor every cell, then
    hand out the leftover units to the cells with the largest fractional
    remainder. This minimises total rounding error versus naive rounding and
    is deterministic (no randomness needed to decide which cells round up).

    Rounding can reintroduce a small margin deviation even after `rake()`
    converged exactly on continuous weights -- the returned report measures
    that residual so it is visible, not silently absorbed.
    """

    scaled = weights / weights.sum() * total_students
    floors = scaled.apply(lambda value: int(value // 1))
    remainder_budget = total_students - int(floors.sum())
    remainders = (scaled - floors).sort_values(ascending=False)

    counts = floors.copy()
    for index in remainders.index[:remainder_budget]:
        counts[index] += 1

    _max_dev, deviation_by_margin = _max_relative_deviation(
        seed_table, margins, counts.astype(float)
    )
    report = IntegerizationReport(
        total_students=int(counts.sum()),
        deviation_by_margin_after_rounding=deviation_by_margin,
    )
    return counts, report
