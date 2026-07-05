"""Typed error hierarchy for the synthetic population layer.

Deliberately does NOT include a "raking failed to converge" error: per
docs/assumptions.md and docs/calibration_targets.md, non-convergence is a
reportable finding (usually evidence of conflicting marginals, which
suppressed-cell imputation can produce), not a crash. `rake()` always
returns a `ConvergenceReport`; callers decide what a failed report means for
their use case.
"""

from __future__ import annotations


class SyntheticError(Exception):
    """Base class for all synthetic-population-layer failures."""


class MarginConfigurationError(SyntheticError):
    """Raised when a margin specification cannot be reconciled with the seed
    table at all (e.g. a dimension referenced in margins does not exist in
    the seed table) -- a configuration bug, not a convergence outcome."""
