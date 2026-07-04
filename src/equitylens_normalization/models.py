"""Typed domain models used across the normalization and warehouse layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ExtractionRule:
    """One `(source_id, sheet)` extraction instruction from `extraction_map.yml`.

    `header_style` selects which normalizer/reader branch interprets `options`;
    the shape of `options` is style-specific and documented alongside each
    style in `config/extraction_map.yml` rather than fixed in code, so new
    sources can be added as pure config as long as they fit an existing style.
    """

    source_id: str
    target_fact: str
    header_style: str
    sheet: str | None = None
    sheet_pattern: str | None = None
    workbook_member: str | None = None
    table_number: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class LongRecord:
    """One tidy fact row prior to institution-alias resolution and warehouse load.

    `institution_raw` and `state_raw` are the as-read publisher strings (before
    canonicalisation); `dimensions` and `measures` hold fact-family-specific
    axes and numeric fields that do not fit the common
    institution/state/year/equity_group/metric shape (e.g. QILT's
    `ci_low`/`ci_high`, SEIFA's `geo_level`/`geo_code`/`decile`).

    `dimensions` participates in the deduplication natural key (see
    `warehouse.deduplicate_overlapping_publications`) because it distinguishes
    otherwise-identical fact rows (e.g. completion's `tracking_window_years`).
    `metadata` does not: it carries publication-level attributes (e.g. S17's
    `is_annual_release`) that describe *how* a fact was published, not *what*
    fact it is -- including such a field in the dedup key would let the same
    underlying fact survive twice under different publication metadata.
    """

    source_id: str
    source_sheet: str
    target_fact: str
    year: int | None
    metric: str
    value: float | None
    suppressed_flag: bool
    institution_raw: str | None = None
    state_raw: str | None = None
    equity_group: str = "not_disaggregated"
    metric_definition: str | None = None
    dimensions: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)
    measures: dict[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InstitutionAlias:
    """One canonical institution entry from `institution_map.yml`."""

    canonical_id: str
    canonical_name: str
    institution_type: str
    state: str
    peer_group_id: str | None
    aliases: tuple[str, ...]
    is_multi_state: bool = False
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationFinding:
    """One flagged anomaly from a cross-source reconciliation check."""

    check_name: str
    severity: str  # "error" | "warning"
    institution_id: str | None
    year_value: int | None
    message: str
    context: dict[str, Any] = field(default_factory=dict)
