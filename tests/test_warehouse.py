from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
import yaml

from equitylens_normalization.institution_map import load_institution_map
from equitylens_normalization.models import LongRecord
from equitylens_normalization.warehouse import build_warehouse, deduplicate_overlapping_publications


@pytest.fixture
def resolver(tmp_path: Path):
    path = tmp_path / "institution_map.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "institutions": [
                    {
                        "canonical_id": "acu",
                        "canonical_name": "Australian Catholic University",
                        "type": "university",
                        "state": "multi_state",
                        "is_multi_state": True,
                        "peer_group_id": "acu_peer_regional",
                        "aliases": ["Australian Catholic University"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return load_institution_map(path)


def _record(source_id: str, year: int, value: float) -> LongRecord:
    return LongRecord(
        source_id=source_id,
        source_sheet="1",
        target_fact="fact_retention_attrition",
        year=year,
        metric="retention_rate",
        value=value,
        suppressed_flag=False,
        institution_raw="acu",
        equity_group="not_disaggregated",
        metric_definition="new_adjusted__domestic__table_ab",
    )


def test_deduplicate_keeps_latest_publication_year() -> None:
    records = [
        _record("doe_s15_2018", 2010, value=80.0),
        _record("doe_s15_2019", 2010, value=81.0),  # revised figure, later publication wins
        _record("doe_s15_2019", 2011, value=82.0),
    ]
    deduped = deduplicate_overlapping_publications(records)
    assert len(deduped) == 2
    by_year = {r.year: r.value for r in deduped}
    assert by_year == {2010: 81.0, 2011: 82.0}


def test_deduplicate_is_a_no_op_for_disjoint_years() -> None:
    records = [_record("doe_s15_2018", 2005, 10.0), _record("doe_s15_2018", 2006, 20.0)]
    assert len(deduplicate_overlapping_publications(records)) == 2


def test_build_warehouse_loads_dims_and_facts(tmp_path: Path, resolver) -> None:
    records = [_record("doe_s15_2024", 2020, 89.26)]
    warehouse_path = tmp_path / "warehouse.duckdb"

    loaded = build_warehouse(warehouse_path, records, resolver)
    assert loaded == 1

    connection = duckdb.connect(str(warehouse_path), read_only=True)
    try:
        institution_row = connection.execute(
            "SELECT institution_name, peer_group_id, is_multi_state FROM dim_institution "
            "WHERE institution_id = 'acu'"
        ).fetchone()
        assert institution_row == ("Australian Catholic University", "acu_peer_regional", True)

        fact_row = connection.execute(
            "SELECT institution_id, year_value, value FROM fact_retention_attrition"
        ).fetchone()
        assert fact_row == ("acu", 2020, 89.26)
    finally:
        connection.close()
