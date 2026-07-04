from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from equitylens_normalization.institution_map import load_institution_map
from equitylens_normalization.models import ExtractionRule
from equitylens_normalization.normalizers import doe_s15


@pytest.fixture
def resolver(tmp_path: Path):
    path = tmp_path / "institution_map.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "institutions": [
                    {
                        "canonical_id": "csu",
                        "canonical_name": "Charles Sturt University",
                        "type": "university",
                        "state": "nsw",
                        "aliases": ["Charles Sturt University"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return load_institution_map(path)


def test_wide_year_format_skips_sector_aggregates_and_reads_years(resolver) -> None:
    grid = pd.DataFrame(
        [
            ["State/Institution", "Rate"],
            [None, 2005, 2006, 2007],
            ["Australia", None, None, None],
            ["National Total", 14.86, 14.5, 14.61],  # real values, must be skipped as aggregate
            ["Table A Providers", 14.85, 14.51, 14.64],
            ["New South Wales", None, None, None],
            ["Charles Sturt University", 19.64, 20.97, "< 5"],
        ]
    )
    rule = ExtractionRule(
        source_id="doe_s15_2018",
        target_fact="fact_retention_attrition",
        header_style="inline_state_pseudo_header",
        sheet="1",
        options={
            "layout": "pseudo_header",
            "name_col": 0,
            "data_start_row": 1,
            "year_header_row": 1,
            "value_start_col": 1,
            "metric": "attrition_rate",
            "metric_definition": "new_adjusted__domestic__table_ab",
        },
    )
    records = doe_s15.normalize(rule, grid, resolver, source_year=2018)

    assert {r.institution_raw for r in records} == {"csu"}
    by_year = {r.year: (r.value, r.suppressed_flag) for r in records}
    assert by_year == {2005: (19.64, False), 2006: (20.97, False), 2007: (None, True)}
    assert all(r.equity_group == "not_disaggregated" for r in records)
    assert all(r.metric_definition == "new_adjusted__domestic__table_ab" for r in records)


def test_year_column_detection_stops_at_first_blank_header(resolver) -> None:
    grid = pd.DataFrame(
        [
            [None, 2005, 2006, None, 2008],  # gap after 2006 -- detection must stop there
            ["Charles Sturt University", 10, 20, 30, 40],
        ]
    )
    rule = ExtractionRule(
        source_id="doe_s15_2019",
        target_fact="fact_retention_attrition",
        header_style="inline_state_pseudo_header",
        sheet="1",
        options={
            "layout": "pseudo_header",
            "name_col": 0,
            "data_start_row": 1,
            "year_header_row": 0,
            "value_start_col": 1,
            "metric": "attrition_rate",
        },
    )
    records = doe_s15.normalize(rule, grid, resolver, source_year=2019)
    assert {r.year for r in records} == {2005, 2006}
