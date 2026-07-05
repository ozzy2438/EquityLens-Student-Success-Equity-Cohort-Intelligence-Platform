"""Cross-source semantic reconciliation checks -- the actual quality gate of
the normalization phase.

Ingestion-layer tests verify file integrity; these checks verify that the
*numbers* make sense together: rates within a valid range, no implausible
year-over-year swings, and no institution where one fact family's story
(retention) flatly contradicts another's (completion).
"""

from __future__ import annotations

import duckdb

from equitylens_normalization.models import ReconciliationFinding

RATE_JUMP_THRESHOLD_POINTS = 15.0
RETENTION_VS_COMPLETION_HIGH_RETENTION = 85.0
RETENTION_VS_COMPLETION_LOW_COMPLETION = 25.0
BASE_COUNT_TOLERANCE_RATIO = 0.10

# Declared grain per fact table (docs/schema.md). This is the generic
# invariant that would have caught, structurally, the class of bug that
# recurred three times while building this warehouse -- S16's
# indigenous/first_nations and domestic_national_total/all_domestic label
# drift, and S17's domestic_bachelor/domestic_bachelor__table_ab
# metric_definition mismatch. Every one of those bugs let two source eras
# report the same real-world fact under two different key values, so no row
# ever technically violated its OWN table's grain -- the duplication was
# only visible by noticing two near-identical values for what should have
# been one number. `check_fact_grain_uniqueness` catches true grain
# violations (the same key appearing twice, which should never happen after
# `warehouse.deduplicate_overlapping_publications`); it is not, by itself, a
# substitute for the manual-inspection habit that actually found those three
# bugs, but every current key duplication -- any future dedup regression --
# is now caught automatically rather than by chance.
_FACT_GRAINS: dict[str, tuple[str, ...]] = {
    "fact_enrolment_equity": (
        "institution_id",
        "year_value",
        "equity_group_id",
        "metric",
        "metric_definition",
    ),
    "fact_retention_attrition": (
        "institution_id",
        "year_value",
        "equity_group_id",
        "metric",
        "metric_definition",
    ),
    "fact_equity_performance": (
        "institution_id",
        "year_value",
        "equity_group_id",
        "metric",
        "metric_definition",
    ),
    "fact_completion_cohort": (
        "institution_id",
        "cohort_end_year",
        "tracking_window_years",
        "equity_group_id",
        "metric",
        "metric_definition",
    ),
    "fact_seifa": ("geo_level", "geo_code", "year_value", "index_family"),
    "fact_ses_experience": (
        "institution_id",
        "year_value",
        "level",
        "provider_type",
        "year_scope",
        "focus_area",
    ),
}


def check_rate_bounds(connection: duckdb.DuckDBPyConnection) -> list[ReconciliationFinding]:
    """Flag any retention/attrition/success/completion value outside [0, 100]."""

    findings: list[ReconciliationFinding] = []
    queries = [
        ("fact_retention_attrition", "year_value"),
        ("fact_completion_cohort", "cohort_end_year"),
    ]
    for table, year_column in queries:
        rows = connection.execute(
            f"""
            SELECT institution_id, {year_column} AS year_value, metric, metric_definition, value
            FROM {table}
            WHERE value IS NOT NULL AND (value < 0 OR value > 100)
            """
        ).fetchall()
        for institution_id, year_value, metric, metric_definition, value in rows:
            findings.append(
                ReconciliationFinding(
                    check_name="rate_bounds",
                    severity="error",
                    institution_id=institution_id,
                    year_value=year_value,
                    message=(
                        f"{table}.{metric} ({metric_definition}) = {value} is outside the "
                        "valid 0-100 range"
                    ),
                    context={"table": table, "metric": metric, "value": value},
                )
            )
    return findings


def check_year_over_year_jumps(
    connection: duckdb.DuckDBPyConnection,
) -> list[ReconciliationFinding]:
    """Flag institution x metric series with a >15 percentage-point jump between
    consecutive years."""

    findings: list[ReconciliationFinding] = []
    rows = connection.execute(
        """
        WITH ordered AS (
            SELECT
                institution_id, metric, metric_definition, year_value, value,
                LAG(value) OVER (
                    PARTITION BY institution_id, metric, metric_definition
                    ORDER BY year_value
                ) AS previous_value,
                LAG(year_value) OVER (
                    PARTITION BY institution_id, metric, metric_definition
                    ORDER BY year_value
                ) AS previous_year
            FROM fact_retention_attrition
            WHERE value IS NOT NULL
        )
        SELECT
            institution_id, metric, metric_definition, year_value, value,
            previous_value, previous_year
        FROM ordered
        WHERE previous_value IS NOT NULL
          AND ABS(value - previous_value) > ?
        """,
        [RATE_JUMP_THRESHOLD_POINTS],
    ).fetchall()
    for (
        institution_id,
        metric,
        metric_definition,
        year_value,
        value,
        previous_value,
        previous_year,
    ) in rows:
        findings.append(
            ReconciliationFinding(
                check_name="year_over_year_jump",
                severity="warning",
                institution_id=institution_id,
                year_value=year_value,
                message=(
                    f"{metric} ({metric_definition}) jumped from {previous_value} in "
                    f"{previous_year} to {value} in {year_value}, a swing greater than "
                    f"{RATE_JUMP_THRESHOLD_POINTS} points"
                ),
                context={"metric": metric, "previous_value": previous_value, "value": value},
            )
        )
    return findings


def check_retention_vs_completion_plausibility(
    connection: duckdb.DuckDBPyConnection,
) -> list[ReconciliationFinding]:
    """Flag institutions where high commencing-cohort retention coexists with an
    implausibly low four-year completion rate for a cohort starting the same year."""

    rows = connection.execute(
        """
        SELECT
            r.institution_id, r.year_value AS commencing_year, r.value AS retention_rate,
            c.value AS completion_rate
        FROM fact_retention_attrition r
        JOIN fact_completion_cohort c
          ON c.institution_id = r.institution_id
         AND c.tracking_window_years = 4
         AND (c.cohort_end_year - 4) = r.year_value
        WHERE r.metric = 'retention_rate'
          AND c.metric = 'completion_rate'
          AND r.value IS NOT NULL
          AND c.value IS NOT NULL
          AND r.value >= ?
          AND c.value <= ?
        """,
        [RETENTION_VS_COMPLETION_HIGH_RETENTION, RETENTION_VS_COMPLETION_LOW_COMPLETION],
    ).fetchall()
    findings: list[ReconciliationFinding] = []
    for institution_id, commencing_year, retention_rate, completion_rate in rows:
        findings.append(
            ReconciliationFinding(
                check_name="retention_vs_completion_plausibility",
                severity="warning",
                institution_id=institution_id,
                year_value=commencing_year,
                message=(
                    f"Commencing-year retention of {retention_rate}% for the {commencing_year} "
                    f"cohort is implausible alongside a four-year completion rate of only "
                    f"{completion_rate}%"
                ),
                context={"retention_rate": retention_rate, "completion_rate": completion_rate},
            )
        )
    return findings


def check_enrolment_vs_performance_base_counts(
    connection: duckdb.DuckDBPyConnection,
) -> list[ReconciliationFinding]:
    """Flag institution x year pairs where Section 11's commencing domestic
    student count disagrees with Section 16's base count by more than 10%."""

    rows = connection.execute(
        """
        SELECT
            e.institution_id, e.year_value, e.value AS s11_value, p.value AS s16_value
        FROM fact_enrolment_equity e
        JOIN fact_equity_performance p
          ON p.institution_id = e.institution_id
         AND p.year_value = e.year_value
         AND p.equity_group_id = 'all_domestic'
         AND p.metric = 'access_numbers'
        WHERE e.equity_group_id = 'all_students'
          AND e.value IS NOT NULL
          AND p.value IS NOT NULL
          AND e.value > 0
          AND ABS(e.value - p.value) / e.value > ?
        """,
        [BASE_COUNT_TOLERANCE_RATIO],
    ).fetchall()
    findings: list[ReconciliationFinding] = []
    for institution_id, year_value, s11_value, s16_value in rows:
        findings.append(
            ReconciliationFinding(
                check_name="enrolment_vs_performance_base_counts",
                severity="warning",
                institution_id=institution_id,
                year_value=year_value,
                message=(
                    f"Section 11 commencing domestic count ({s11_value}) and Section 16 base "
                    f"count ({s16_value}) disagree by more than "
                    f"{BASE_COUNT_TOLERANCE_RATIO:.0%}"
                ),
                context={"s11_value": s11_value, "s16_value": s16_value},
            )
        )
    return findings


def check_fact_grain_uniqueness(
    connection: duckdb.DuckDBPyConnection,
) -> list[ReconciliationFinding]:
    """Every fact table must have exactly one row per its own declared grain
    (`_FACT_GRAINS`, matching docs/schema.md). A violation here means
    `warehouse.deduplicate_overlapping_publications` let two rows through
    under the identical key -- which should be structurally impossible after
    a build, so any finding here is an `error`, not a `warning`."""

    findings: list[ReconciliationFinding] = []
    for table, grain_columns in _FACT_GRAINS.items():
        columns_sql = ", ".join(grain_columns)
        rows = connection.execute(
            f"""
            SELECT {columns_sql}, COUNT(*) AS n
            FROM {table}
            GROUP BY {columns_sql}
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for row in rows:
            *key_values, count = row
            key_description = ", ".join(
                f"{col}={value}" for col, value in zip(grain_columns, key_values, strict=True)
            )
            institution_id = key_values[0] if grain_columns[0] == "institution_id" else None
            findings.append(
                ReconciliationFinding(
                    check_name="fact_grain_uniqueness",
                    severity="error",
                    institution_id=institution_id,
                    year_value=None,
                    message=(
                        f"{table} has {count} rows for grain ({key_description}) -- "
                        "expected exactly 1"
                    ),
                    context={"table": table, "count": count},
                )
            )
    return findings


ALL_CHECKS = (
    check_rate_bounds,
    check_year_over_year_jumps,
    check_retention_vs_completion_plausibility,
    check_enrolment_vs_performance_base_counts,
    check_fact_grain_uniqueness,
)


def run_all_checks(connection: duckdb.DuckDBPyConnection) -> list[ReconciliationFinding]:
    findings: list[ReconciliationFinding] = []
    for check in ALL_CHECKS:
        findings.extend(check(connection))
    return findings
