from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from equitylens_calibration.targets import (
    assign_tolerance_tier,
    build_target_set,
    compute_completion_targets,
    compute_enrolment_share_targets,
    compute_rate_targets,
    compute_seifa_targets,
    save_target_set,
)
from equitylens_normalization.warehouse import DDL


@pytest.fixture
def connection():
    conn = duckdb.connect(":memory:")
    conn.execute(DDL)
    yield conn
    conn.close()


@pytest.mark.parametrize(
    ("n", "suppressed", "expected_tier"),
    [
        (500, False, "n>=200"),
        (200, False, "n>=200"),
        (199, False, "50<=n<200"),
        (50, False, "50<=n<200"),
        (49, False, "10<=n<50"),
        (10, False, "10<=n<50"),
        (9, False, "n<10_or_suppressed"),
        (None, False, "n<10_or_suppressed"),
        (500, True, "n<10_or_suppressed"),
    ],
)
def test_assign_tolerance_tier(n, suppressed, expected_tier) -> None:
    tier = assign_tolerance_tier(n, suppressed=suppressed)
    assert tier.name == expected_tier
    if expected_tier == "n<10_or_suppressed":
        assert tier.tolerance_pp is None
    else:
        assert tier.tolerance_pp is not None


def _insert_enrolment(conn, rows: list[tuple]) -> None:
    conn.executemany(
        "INSERT INTO fact_enrolment_equity VALUES (?, ?, ?, ?, ?, ?, ?, 'src', 'sheet')", rows
    )


def test_enrolment_share_target_computes_percentage(connection) -> None:
    _insert_enrolment(
        connection,
        [
            ("acu", 2023, "all_students", "commencing_domestic_students", None, 10000.0, False),
            ("acu", 2023, "low_ses_sa1", "commencing_domestic_students", None, 1200.0, False),
        ],
    )
    targets = compute_enrolment_share_targets(connection, 2023)
    assert len(targets) == 1
    assert targets[0].share_pct == 12.0
    assert targets[0].imputed_target_flag is False
    assert targets[0].tolerance_pp == 1.0


def test_enrolment_share_target_imputes_suppressed_cell_from_sector_average(connection) -> None:
    _insert_enrolment(
        connection,
        [
            ("acu", 2023, "all_students", "commencing_domestic_students", None, 10000.0, False),
            ("acu", 2023, "first_nations", "commencing_domestic_students", None, None, True),
            ("csu", 2023, "all_students", "commencing_domestic_students", None, 5000.0, False),
            ("csu", 2023, "first_nations", "commencing_domestic_students", None, 500.0, False),
        ],
    )
    targets = compute_enrolment_share_targets(connection, 2023)
    acu_target = next(t for t in targets if t.institution_id == "acu")
    assert acu_target.imputed_target_flag is True
    assert acu_target.imputation_source == "sector_average_share_2023"
    # CSU's own share (500/5000=10%) is the only non-suppressed observation,
    # so it becomes the sector average ACU is imputed from.
    assert acu_target.share_pct == 10.0


def _insert_equity_performance(conn, rows: list[tuple]) -> None:
    conn.executemany(
        "INSERT INTO fact_equity_performance VALUES (?, ?, ?, ?, ?, ?, ?, 'src', 'sheet')", rows
    )


def test_rate_target_joins_access_numbers_for_tolerance_tier(connection) -> None:
    _insert_equity_performance(
        connection,
        [
            ("acu", 2023, "remote", "retention_rate", None, 66.78, False),
            ("acu", 2023, "remote", "access_numbers", None, 35.0, False),
            ("acu", 2023, "disability", "retention_rate", None, 83.76, False),
            ("acu", 2023, "disability", "access_numbers", None, 704.0, False),
        ],
    )
    targets = compute_rate_targets(connection, 2023, "retention_rate")
    by_group = {t.equity_group_id: t for t in targets}
    assert by_group["remote"].n == 35.0
    assert by_group["remote"].tolerance_tier == "10<=n<50"
    assert by_group["disability"].tolerance_tier == "n>=200"


def test_rate_targets_include_all_domestic_as_its_own_target(connection) -> None:
    # Regression test: an earlier version excluded `all_domestic` entirely,
    # copying the Section 11 enrolment-share pattern where the analogous
    # `all_students` row is purely a denominator -- for rates, `all_domestic`
    # is a directly published, large-N institutional rate that Step 3 needs
    # as the anchor its per-equity-group logit deltas are computed against.
    _insert_equity_performance(
        connection,
        [
            ("acu", 2023, "all_domestic", "retention_rate", None, 82.91, False),
            ("acu", 2023, "all_domestic", "access_numbers", None, 10034.0, False),
        ],
    )
    targets = compute_rate_targets(connection, 2023, "retention_rate")
    by_group = {t.equity_group_id: t for t in targets}
    assert "all_domestic" in by_group
    assert by_group["all_domestic"].value == 82.91
    assert by_group["all_domestic"].tolerance_tier == "n>=200"


def test_rate_target_without_matching_access_numbers_is_excluded_from_gate(connection) -> None:
    _insert_equity_performance(
        connection,
        [("acu", 2023, "undergraduate_low_ses_by_sa1", "retention_rate", None, 82.28, False)],
    )
    targets = compute_rate_targets(connection, 2023, "retention_rate")
    assert targets[0].n is None
    assert targets[0].tolerance_pp is None
    assert targets[0].tolerance_tier == "n<10_or_suppressed"


def test_rate_target_imputes_suppressed_value_from_sector_average(connection) -> None:
    _insert_equity_performance(
        connection,
        [
            ("acu", 2023, "first_nations", "retention_rate", None, None, True),
            ("csu", 2023, "first_nations", "retention_rate", None, 75.0, False),
            ("une", 2023, "first_nations", "retention_rate", None, 85.0, False),
        ],
    )
    targets = compute_rate_targets(connection, 2023, "retention_rate")
    acu_target = next(t for t in targets if t.institution_id == "acu")
    assert acu_target.imputed_target_flag is True
    assert acu_target.value == 80.0  # average of 75.0 and 85.0
    assert acu_target.imputation_source == "sector_average_retention_rate_2023"


def test_seifa_targets_sum_to_100_percent(connection) -> None:
    connection.executemany(
        "INSERT INTO fact_seifa VALUES "
        "('poa', ?, NULL, 2021, 'ieo', TRUE, ?, ?, ?, NULL, NULL, FALSE, 'src', 'sheet')",
        [
            ("0800", 1000.0, 1, 100),
            ("0810", 1000.0, 10, 300),
        ],
    )
    targets = compute_seifa_targets(connection)
    assert len(targets) == 2
    assert round(sum(t.share_pct for t in targets), 1) == 100.0


def test_completion_targets_pick_most_recent_cohort_per_window(connection) -> None:
    connection.executemany(
        "INSERT INTO fact_completion_cohort VALUES "
        "(?, ?, ?, 'not_disaggregated', 'completion_rate', 'domestic_bachelor__table_ab', "
        "?, FALSE, TRUE, 'src', 'sheet')",
        [
            ("acu", 2018, 4, 39.45),
            ("acu", 2020, 4, 41.54),  # most recent window=4 cohort
            ("acu", 2015, 9, 77.45),
            ("acu", 2016, 9, 77.85),  # most recent window=9 cohort
        ],
    )
    targets = compute_completion_targets(connection, institution_id="acu")
    by_window = {t.tracking_window_years: t for t in targets}
    assert by_window[4].cohort_end_year == 2020
    assert by_window[4].value == 41.54
    assert by_window[9].cohort_end_year == 2016
    assert by_window[9].value == 77.85
    assert all(t.tolerance_pp == 2.0 for t in targets)


def test_save_target_set_is_versioned_and_deduplicates_identical_content(tmp_path: Path) -> None:
    target_set = {
        "target_version": "v1",
        "reference_year": 2023,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "warehouse_path": "x",
        "warehouse_sha256": "abc",
        "git_commit": "def",
        "targets": {
            "enrolment_share": [],
            "retention_rate": [],
            "success_rate": [],
            "seifa_decile_share": [],
        },
    }
    first_path = save_target_set(target_set, tmp_path)
    assert first_path.name == "targets_v1_2023ref.json"

    # Saving identical content again must not create a duplicate file.
    second_path = save_target_set(target_set, tmp_path)
    assert second_path == first_path
    assert len(list(tmp_path.glob("*.json"))) == 1

    # Saving different content for the same version/year gets a new file,
    # never silently overwriting the previous one.
    changed = {**target_set, "generated_at": "2026-02-01T00:00:00+00:00"}
    third_path = save_target_set(changed, tmp_path)
    assert third_path != first_path
    assert first_path.exists()
    assert third_path.exists()


def test_build_target_set_embeds_reproducibility_metadata(tmp_path: Path, connection) -> None:
    _insert_enrolment(
        connection,
        [("acu", 2023, "all_students", "commencing_domestic_students", None, 100.0, False)],
    )
    connection.close()

    warehouse_path = tmp_path / "warehouse.duckdb"
    conn = duckdb.connect(str(warehouse_path))
    conn.execute(DDL)
    conn.executemany(
        "INSERT INTO fact_enrolment_equity VALUES (?, ?, ?, ?, ?, ?, ?, 'src', 'sheet')",
        [("acu", 2023, "all_students", "commencing_domestic_students", None, 100.0, False)],
    )
    conn.close()

    target_set = build_target_set(warehouse_path, reference_year=2023, project_root=tmp_path)
    assert target_set["target_version"] == "v3"
    assert target_set["reference_year"] == 2023
    assert len(target_set["warehouse_sha256"]) == 64
    assert "generated_at" in target_set
    # git_commit is None outside a git repo (tmp_path is not one) -- still a
    # valid, honest value rather than a fabricated placeholder.
    assert target_set["git_commit"] is None

    path = save_target_set(target_set, tmp_path / "calibration")
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["warehouse_sha256"] == target_set["warehouse_sha256"]
