from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from equitylens_normalization.institution_map import load_institution_map
from equitylens_normalization.models import ExtractionRule
from equitylens_normalization.normalizers import doe_s11


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
                        "aliases": ["Australian Catholic University"],
                    },
                    {
                        "canonical_id": "csu",
                        "canonical_name": "Charles Sturt University",
                        "type": "university",
                        "state": "nsw",
                        "aliases": ["Charles Sturt University"],
                    },
                    {
                        "canonical_id": "__nuhei_rollup__",
                        "canonical_name": "Non-University Higher Education Institutions",
                        "type": "nuhei",
                        "state": "unknown",
                        "aliases": ["Non-University Higher Education Institutions"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return load_institution_map(path)


def test_pseudo_header_era_extracts_equity_columns(resolver) -> None:
    grid = pd.DataFrame(
        [
            ["State/Institution", "NESB", "Disability", "All Students"],
            ["New South Wales", None, None, None],
            ["Charles Sturt University", 100, 50, 500],
            ["Multi-State", None, None, None],
            ["Australian Catholic University", "< 5", "np", 200],
            ["Non-University Higher Education Institutions", 10, 5, 50],
            ["TOTAL", 110, 55, 750],
        ]
    )
    rule = ExtractionRule(
        source_id="doe_s11_2018",
        target_fact="fact_enrolment_equity",
        header_style="inline_state_pseudo_header",
        sheet="3",
        options={
            "layout": "pseudo_header",
            "name_col": 0,
            "data_start_row": 1,
            "metric": "commencing_domestic_students",
            "equity_columns": [
                {"column": 1, "equity_group": "non_english_speaking_background"},
                {"column": 2, "equity_group": "disability"},
                {"column": 3, "equity_group": "all_students"},
            ],
        },
    )
    records = doe_s11.normalize(rule, grid, resolver, source_year=2018)

    csu = [r for r in records if r.institution_raw == "csu"]
    assert len(csu) == 3
    assert {(r.equity_group, r.value, r.suppressed_flag) for r in csu} == {
        ("non_english_speaking_background", 100.0, False),
        ("disability", 50.0, False),
        ("all_students", 500.0, False),
    }
    assert all(r.state_raw == "New South Wales" for r in csu)

    acu = [r for r in records if r.institution_raw == "acu"]
    assert acu[0].state_raw == "Multi-State"
    suppressed = {r.equity_group: r.suppressed_flag for r in acu}
    assert suppressed["non_english_speaking_background"] is True
    assert suppressed["disability"] is True
    values = {r.equity_group: r.value for r in acu}
    assert values["non_english_speaking_background"] is None
    assert values["disability"] is None

    # The NUHEI rollup row must not appear as a per-institution fact row.
    assert all(r.institution_raw not in ("__nuhei_rollup__",) for r in records)
    assert len(records) == 6  # csu (3) + acu (3), rollup and TOTAL both excluded


def test_two_column_era_blank_fills_state(resolver) -> None:
    grid = pd.DataFrame(
        [
            ["State", "Institution", "NESB", "All Students"],
            ["New South Wales", "Charles Sturt University", 120, 600],
            [None, "Charles Sturt University", 999, 999],  # unrealistic 2nd row, still same state
            ["Multi-State", "Australian Catholic University", 80, 300],
        ]
    )
    rule = ExtractionRule(
        source_id="doe_s11_2021",
        target_fact="fact_enrolment_equity",
        header_style="state_institution_columns",
        sheet="11.3",
        options={
            "layout": "two_column",
            "name_col": 1,
            "state_col": 0,
            "data_start_row": 1,
            "metric": "commencing_domestic_students",
            "equity_columns": [
                {"column": 2, "equity_group": "non_english_speaking_background"},
                {"column": 3, "equity_group": "all_students"},
            ],
        },
    )
    records = doe_s11.normalize(rule, grid, resolver, source_year=2021)
    acu = [r for r in records if r.institution_raw == "acu"]
    assert acu[0].state_raw == "Multi-State"
