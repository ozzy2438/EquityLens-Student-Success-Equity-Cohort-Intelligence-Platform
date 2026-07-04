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


ALL_CHECKS = (
    check_rate_bounds,
    check_year_over_year_jumps,
    check_retention_vs_completion_plausibility,
    check_enrolment_vs_performance_base_counts,
)


def run_all_checks(connection: duckdb.DuckDBPyConnection) -> list[ReconciliationFinding]:
    findings: list[ReconciliationFinding] = []
    for check in ALL_CHECKS:
        findings.extend(check(connection))
    return findings
