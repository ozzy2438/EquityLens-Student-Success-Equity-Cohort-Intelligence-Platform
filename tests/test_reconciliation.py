from __future__ import annotations

import duckdb
import pytest

from equitylens_normalization.reconciliation import (
    check_enrolment_vs_performance_base_counts,
    check_rate_bounds,
    check_retention_vs_completion_plausibility,
    check_year_over_year_jumps,
    run_all_checks,
)
from equitylens_normalization.warehouse import DDL


@pytest.fixture
def connection():
    conn = duckdb.connect(":memory:")
    conn.execute(DDL)
    yield conn
    conn.close()


def _insert_retention(conn, rows: list[tuple]) -> None:
    conn.executemany(
        "INSERT INTO fact_retention_attrition VALUES "
        "(?, ?, 'not_disaggregated', ?, ?, ?, FALSE, 'src', 'sheet')",
        rows,
    )


def _insert_completion(conn, rows: list[tuple]) -> None:
    conn.executemany(
        "INSERT INTO fact_completion_cohort VALUES "
        "(?, ?, ?, 'not_disaggregated', ?, 'domestic_bachelor', ?, FALSE, TRUE, 'src', 'sheet')",
        rows,
    )


def test_check_rate_bounds_flags_out_of_range_values(connection) -> None:
    _insert_retention(
        connection,
        [
            ("acu", 2020, "retention_rate", "adj", 85.0),
            ("acu", 2021, "retention_rate", "adj", 104.0),  # out of 0-100 range
            ("acu", 2022, "retention_rate", "adj", -5.0),  # out of range
        ],
    )
    findings = check_rate_bounds(connection)
    assert len(findings) == 2
    assert {f.year_value for f in findings} == {2021, 2022}
    assert all(f.severity == "error" for f in findings)


def test_check_rate_bounds_ignores_in_range_values(connection) -> None:
    _insert_retention(connection, [("acu", 2020, "retention_rate", "adj", 85.0)])
    assert check_rate_bounds(connection) == []


def test_check_year_over_year_jumps_flags_large_swings(connection) -> None:
    _insert_retention(
        connection,
        [
            ("acu", 2019, "attrition_rate", "adj", 15.0),
            ("acu", 2020, "attrition_rate", "adj", 45.0),  # +30pp jump
            ("acu", 2021, "attrition_rate", "adj", 47.0),  # small, unflagged
        ],
    )
    findings = check_year_over_year_jumps(connection)
    assert len(findings) == 1
    assert findings[0].year_value == 2020


def test_check_retention_vs_completion_flags_implausible_pair(connection) -> None:
    _insert_retention(connection, [("acu", 2015, "retention_rate", "adj", 90.0)])
    _insert_completion(connection, [("acu", 2019, 4, "completion_rate", 10.0)])
    findings = check_retention_vs_completion_plausibility(connection)
    assert len(findings) == 1
    assert findings[0].institution_id == "acu"


def test_check_retention_vs_completion_ignores_other_metrics(connection) -> None:
    _insert_retention(connection, [("acu", 2015, "retention_rate", "adj", 90.0)])
    # Same cohort, but this is the "never_came_back" outcome, not completion --
    # must not be mistaken for a low completion rate (regression test for the
    # missing c.metric filter bug).
    _insert_completion(connection, [("acu", 2019, 4, "never_came_back", 10.0)])
    assert check_retention_vs_completion_plausibility(connection) == []


def test_check_enrolment_vs_performance_base_counts_flags_disagreement(connection) -> None:
    connection.execute(
        "INSERT INTO fact_enrolment_equity VALUES "
        "('acu', 2023, 'all_students', 'commencing_domestic_students', "
        "NULL, 1000, FALSE, 'src', 'sheet')"
    )
    connection.execute(
        "INSERT INTO fact_equity_performance VALUES "
        "('acu', 2023, 'all_domestic', 'commencing_domestic_students', "
        "NULL, 800, FALSE, 'src', 'sheet')"
    )
    findings = check_enrolment_vs_performance_base_counts(connection)
    assert len(findings) == 1


def test_run_all_checks_aggregates_every_check(connection) -> None:
    _insert_retention(connection, [("acu", 2021, "retention_rate", "adj", 150.0)])
    findings = run_all_checks(connection)
    assert any(f.check_name == "rate_bounds" for f in findings)
