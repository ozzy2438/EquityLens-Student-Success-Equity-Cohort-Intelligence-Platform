"""Typed domain models for calibration targets.

Every target record traces back to `docs/calibration_targets.md`: the tiered
tolerance, the suppressed-cell imputation policy, and the reference year are
not re-derived here, they are read from that contract's numbers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ToleranceTier:
    """One N-dependent tolerance bucket from the Step 0 target contract."""

    name: str
    tolerance_pp: float | None  # None means "excluded from the pass/fail gate"


@dataclass(frozen=True, slots=True)
class EnrolmentShareTarget:
    """Section 11 equity-group enrolment share target, tolerance ±1.0pp fixed."""

    institution_id: str
    equity_group_id: str
    count: float
    all_students: float
    share_pct: float
    tolerance_pp: float
    imputed_target_flag: bool
    imputation_source: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RateTarget:
    """Section 16 retention/success rate target, N-dependent tolerance tier."""

    institution_id: str
    equity_group_id: str
    metric: str
    value: float
    n: float | None
    tolerance_tier: str
    tolerance_pp: float | None
    imputed_target_flag: bool
    imputation_source: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SeifaDecileTarget:
    """National, population-weighted SEIFA (IEO) decile share target, ±2.0pp."""

    decile: int
    population: int
    share_pct: float
    tolerance_pp: float

    def to_dict(self) -> dict:
        return asdict(self)
