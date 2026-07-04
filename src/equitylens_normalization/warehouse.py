"""DuckDB star-schema DDL and full-rebuild loader.

`build_warehouse` is a pure function of the immutable raw files plus the
versioned `extraction_map.yml`/`institution_map.yml` configs, so each run
does a full `CREATE OR REPLACE` rebuild rather than an incremental upsert --
simpler and safer, and cheap for a 31-file corpus.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb

from equitylens_normalization.extraction_map import ExtractionRule
from equitylens_normalization.institution_map import InstitutionResolver
from equitylens_normalization.models import LongRecord
from equitylens_normalization.normalizers import (
    abs_seifa,
    doe_s11,
    doe_s15,
    doe_s16,
    doe_s17,
    qilt_ses,
)
from equitylens_normalization.readers.grid_reader import read_grid

DDL = """
CREATE OR REPLACE TABLE dim_institution (
    institution_id VARCHAR PRIMARY KEY,
    institution_name VARCHAR NOT NULL,
    institution_type VARCHAR NOT NULL,
    state VARCHAR NOT NULL,
    is_multi_state BOOLEAN NOT NULL DEFAULT FALSE,
    peer_group_id VARCHAR
);

CREATE OR REPLACE TABLE dim_equity_group (
    equity_group_id VARCHAR PRIMARY KEY,
    display_name VARCHAR NOT NULL
);

CREATE OR REPLACE TABLE dim_year (
    year_value INTEGER PRIMARY KEY,
    is_completion_cohort_only BOOLEAN NOT NULL DEFAULT FALSE
);

-- GRAIN: institution x year x equity_group x metric x metric_definition
CREATE OR REPLACE TABLE fact_enrolment_equity (
    institution_id VARCHAR NOT NULL,
    year_value INTEGER NOT NULL,
    equity_group_id VARCHAR NOT NULL,
    metric VARCHAR NOT NULL,
    metric_definition VARCHAR,
    value DOUBLE,
    suppressed_flag BOOLEAN NOT NULL DEFAULT FALSE,
    source_id VARCHAR NOT NULL,
    source_sheet VARCHAR NOT NULL
);

-- GRAIN: institution x year x metric x metric_definition (equity_group fixed
-- at 'not_disaggregated' -- S15 institution tables carry no equity split)
CREATE OR REPLACE TABLE fact_retention_attrition (
    institution_id VARCHAR NOT NULL,
    year_value INTEGER NOT NULL,
    equity_group_id VARCHAR NOT NULL DEFAULT 'not_disaggregated',
    metric VARCHAR NOT NULL,
    metric_definition VARCHAR,
    value DOUBLE,
    suppressed_flag BOOLEAN NOT NULL DEFAULT FALSE,
    source_id VARCHAR NOT NULL,
    source_sheet VARCHAR NOT NULL
);

-- GRAIN: institution x year x equity_group x metric x metric_definition.
-- No `state` column -- S16 institution rows carry no per-row state; resolve
-- via dim_institution if needed.
CREATE OR REPLACE TABLE fact_equity_performance (
    institution_id VARCHAR NOT NULL,
    year_value INTEGER NOT NULL,
    equity_group_id VARCHAR NOT NULL,
    metric VARCHAR NOT NULL,
    metric_definition VARCHAR,
    value DOUBLE,
    suppressed_flag BOOLEAN NOT NULL DEFAULT FALSE,
    source_id VARCHAR NOT NULL,
    source_sheet VARCHAR NOT NULL
);

-- GRAIN: institution x cohort_end_year x tracking_window_years x metric x
-- metric_definition. is_annual_release distinguishes the true 2023/2024
-- annual releases from the 2018-2022 cumulative cohort-analysis publications.
CREATE OR REPLACE TABLE fact_completion_cohort (
    institution_id VARCHAR NOT NULL,
    cohort_end_year INTEGER NOT NULL,
    tracking_window_years SMALLINT NOT NULL,
    equity_group_id VARCHAR NOT NULL DEFAULT 'not_disaggregated',
    metric VARCHAR NOT NULL,
    metric_definition VARCHAR,
    value DOUBLE,
    suppressed_flag BOOLEAN NOT NULL DEFAULT FALSE,
    is_annual_release BOOLEAN NOT NULL,
    source_id VARCHAR NOT NULL,
    source_sheet VARCHAR NOT NULL
);

-- GRAIN: geo_level x geo_code x year x index_family.
-- is_low_ses_calibration_target flags the Index of Education and Occupation
-- family specifically (DoE's own definition of "Low SES").
CREATE OR REPLACE TABLE fact_seifa (
    geo_level VARCHAR NOT NULL,
    geo_code VARCHAR NOT NULL,
    geo_name VARCHAR,
    year_value INTEGER NOT NULL,
    index_family VARCHAR NOT NULL,
    is_low_ses_calibration_target BOOLEAN NOT NULL DEFAULT FALSE,
    score DOUBLE,
    decile SMALLINT,
    usual_resident_population INTEGER,
    caution_flag_area BOOLEAN,
    caution_flag_boundary BOOLEAN,
    suppressed_flag BOOLEAN NOT NULL DEFAULT FALSE,
    source_id VARCHAR NOT NULL,
    source_sheet VARCHAR NOT NULL
);

-- GRAIN: institution x year x level x provider_type x year_scope x focus_area
CREATE OR REPLACE TABLE fact_ses_experience (
    institution_id VARCHAR NOT NULL,
    year_value INTEGER NOT NULL,
    level VARCHAR NOT NULL,
    provider_type VARCHAR NOT NULL,
    year_scope VARCHAR NOT NULL,
    focus_area VARCHAR NOT NULL,
    value DOUBLE,
    ci_low DOUBLE,
    ci_high DOUBLE,
    suppressed_flag BOOLEAN NOT NULL DEFAULT FALSE,
    source_id VARCHAR NOT NULL,
    source_sheet VARCHAR NOT NULL
);
"""

# S11 and S15 share the two DoE row-grouping layouts (`inline_state_pseudo_header`
# / `state_institution_columns`), so the normalizer is selected by
# `target_fact`, not by `header_style`, for grid-shaped rules.
_TARGET_FACT_NORMALIZERS = {
    "fact_enrolment_equity": doe_s11.normalize,
    "fact_retention_attrition": doe_s15.normalize,
    "fact_equity_performance": doe_s16.normalize,
    "fact_completion_cohort": doe_s17.normalize,
    "fact_seifa": abs_seifa.normalize,
}


def load_file_manifest(data_root: Path) -> dict[str, dict]:
    manifest_path = data_root / "manifests" / "file_manifest.jsonl"
    by_source: dict[str, dict] = {}
    with manifest_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            by_source[record["source_id"]] = record
    return by_source


def run_normalizers(
    rules: list[ExtractionRule],
    manifest_by_source: dict[str, dict],
    resolver: InstitutionResolver,
    *,
    project_root: Path,
) -> list[LongRecord]:
    """Run every extraction rule against its raw file and return all records."""

    records: list[LongRecord] = []
    for rule in rules:
        manifest_entry = manifest_by_source.get(rule.source_id)
        if manifest_entry is None:
            raise KeyError(f"No file_manifest.jsonl entry for source_id {rule.source_id!r}")
        raw_path = project_root / manifest_entry["raw_path"]
        source_year = int(manifest_entry["year"])

        if rule.header_style == "focus_area_columns":
            records.extend(qilt_ses.normalize(rule, raw_path, resolver, source_year=source_year))
            continue

        normalize_fn = _TARGET_FACT_NORMALIZERS[rule.target_fact]
        grid = read_grid(raw_path, rule.sheet, workbook_member=rule.workbook_member)
        records.extend(normalize_fn(rule, grid, resolver, source_year=source_year))
    return records


_TRAILING_YEAR = re.compile(r"(\d{4})$")


def _source_publication_year(source_id: str) -> int:
    match = _TRAILING_YEAR.search(source_id)
    return int(match.group(1)) if match else 0


def deduplicate_overlapping_publications(records: list[LongRecord]) -> list[LongRecord]:
    """Collapse records that describe the same fact row across multiple
    publication years to the most recently published version.

    DoE's wide-year tables are cumulative: every publication re-reports the
    entire history back to a fixed base year, so the same institution x
    year x metric row is present in several source files. Keeping every
    copy would double- (or 7x-) count rows in aggregate queries, so only the
    highest-publication-year source wins per natural key -- `dimensions`
    already carries whatever extra axes distinguish a fact row (tracking
    window, geography, QILT level/provider_type/year_scope), so including
    it in the key generalises correctly across every fact family without
    per-fact-specific logic.
    """

    best: dict[tuple, LongRecord] = {}
    for record in records:
        key = (
            record.target_fact,
            record.institution_raw,
            record.year,
            record.equity_group,
            record.metric,
            record.metric_definition,
            tuple(sorted(record.dimensions.items())),
        )
        existing = best.get(key)
        if existing is None or _source_publication_year(
            record.source_id
        ) >= _source_publication_year(existing.source_id):
            best[key] = record
    return list(best.values())


def build_warehouse(
    warehouse_path: Path,
    records: list[LongRecord],
    resolver: InstitutionResolver,
) -> int:
    """Rebuild the DuckDB warehouse from scratch given already-normalized records.

    Returns the number of fact rows actually loaded, after collapsing
    overlapping publication years.
    """

    records = deduplicate_overlapping_publications(records)
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(warehouse_path))
    try:
        connection.execute(DDL)
        _load_dims(connection, records, resolver)
        _load_facts(connection, records)
    finally:
        connection.close()
    return len(records)


def _executemany_if_any(connection: duckdb.DuckDBPyConnection, sql: str, rows: list[tuple]) -> None:
    if rows:
        connection.executemany(sql, rows)


def _load_dims(
    connection: duckdb.DuckDBPyConnection, records: list[LongRecord], resolver: InstitutionResolver
) -> None:
    institution_rows = [
        (
            inst.canonical_id,
            inst.canonical_name,
            inst.institution_type,
            inst.state,
            inst.is_multi_state,
            inst.peer_group_id,
        )
        for inst in resolver.all()
        if inst.canonical_id != "__nuhei_rollup__"
    ]
    _executemany_if_any(
        connection, "INSERT INTO dim_institution VALUES (?, ?, ?, ?, ?, ?)", institution_rows
    )

    equity_groups = sorted({record.equity_group for record in records})
    _executemany_if_any(
        connection,
        "INSERT INTO dim_equity_group VALUES (?, ?)",
        [(group, group.replace("_", " ").title()) for group in equity_groups],
    )

    years: set[int] = set()
    cohort_only_years: set[int] = set()
    for record in records:
        if record.year is not None:
            years.add(record.year)
        if (
            record.target_fact == "fact_completion_cohort"
            and record.metadata.get("is_annual_release") == "False"
        ):
            cohort_only_years.add(record.year)
    _executemany_if_any(
        connection,
        "INSERT INTO dim_year VALUES (?, ?)",
        [(year, year in cohort_only_years) for year in sorted(years)],
    )


def _load_facts(connection: duckdb.DuckDBPyConnection, records: list[LongRecord]) -> None:
    by_fact: dict[str, list[LongRecord]] = {}
    for record in records:
        by_fact.setdefault(record.target_fact, []).append(record)

    enrolment_rows = [
        (
            r.institution_raw,
            r.year,
            r.equity_group,
            r.metric,
            r.metric_definition,
            r.value,
            r.suppressed_flag,
            r.source_id,
            r.source_sheet,
        )
        for r in by_fact.get("fact_enrolment_equity", [])
    ]
    _executemany_if_any(
        connection,
        "INSERT INTO fact_enrolment_equity VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        enrolment_rows,
    )

    retention_rows = [
        (
            r.institution_raw,
            r.year,
            r.equity_group,
            r.metric,
            r.metric_definition,
            r.value,
            r.suppressed_flag,
            r.source_id,
            r.source_sheet,
        )
        for r in by_fact.get("fact_retention_attrition", [])
    ]
    _executemany_if_any(
        connection,
        "INSERT INTO fact_retention_attrition VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        retention_rows,
    )

    equity_perf_rows = [
        (
            r.institution_raw,
            r.year,
            r.equity_group,
            r.metric,
            r.metric_definition,
            r.value,
            r.suppressed_flag,
            r.source_id,
            r.source_sheet,
        )
        for r in by_fact.get("fact_equity_performance", [])
    ]
    _executemany_if_any(
        connection,
        "INSERT INTO fact_equity_performance VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        equity_perf_rows,
    )

    completion_rows = [
        (
            r.institution_raw,
            r.year,
            int(r.dimensions["tracking_window_years"]),
            r.equity_group,
            r.metric,
            r.metric_definition,
            r.value,
            r.suppressed_flag,
            r.metadata["is_annual_release"] == "True",
            r.source_id,
            r.source_sheet,
        )
        for r in by_fact.get("fact_completion_cohort", [])
    ]
    _executemany_if_any(
        connection,
        "INSERT INTO fact_completion_cohort VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        completion_rows,
    )

    seifa_rows = [
        (
            r.dimensions["geo_level"],
            r.dimensions["geo_code"],
            r.dimensions.get("geo_name") or None,
            r.year,
            r.dimensions["index_family"],
            r.dimensions["is_low_ses_calibration_target"] == "True",
            r.value,
            (int(r.measures["decile"]) if r.measures.get("decile") is not None else None),
            (int(r.measures["population"]) if r.measures.get("population") is not None else None),
            r.dimensions.get("caution_flag_area") == "True",
            r.dimensions.get("caution_flag_boundary") == "True",
            r.suppressed_flag,
            r.source_id,
            r.source_sheet,
        )
        for r in by_fact.get("fact_seifa", [])
    ]
    _executemany_if_any(
        connection,
        "INSERT INTO fact_seifa VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        seifa_rows,
    )

    ses_rows = [
        (
            r.institution_raw,
            r.year,
            r.dimensions["level"],
            r.dimensions["provider_type"],
            r.dimensions["year_scope"],
            r.metric,
            r.value,
            r.measures.get("ci_low"),
            r.measures.get("ci_high"),
            r.suppressed_flag,
            r.source_id,
            r.source_sheet,
        )
        for r in by_fact.get("fact_ses_experience", [])
    ]
    _executemany_if_any(
        connection,
        "INSERT INTO fact_ses_experience VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ses_rows,
    )
