"""Typed domain models for the synthetic population layer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ConvergenceReport:
    """Outcome of one `raking.rake()` run.

    Non-convergence is a first-class, reportable outcome, not an exception:
    `converged=False` usually means the margins passed in are mutually
    inconsistent (a real risk once suppressed-cell imputed targets are mixed
    with observed ones), and the caller -- not this module -- decides
    whether that is acceptable for a given use.
    """

    converged: bool
    iterations: int
    max_relative_deviation: float
    deviation_by_margin: dict[str, float]
    structural_zero_margins: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class IntegerizationReport:
    """Outcome of converting continuous raked weights into integer student
    counts per cell (`raking.integerize`)."""

    total_students: int
    deviation_by_margin_after_rounding: dict[str, float]
