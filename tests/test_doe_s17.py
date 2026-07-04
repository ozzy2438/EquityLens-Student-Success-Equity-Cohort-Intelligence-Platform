from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from equitylens_normalization.institution_map import load_institution_map
from equitylens_normalization.models import ExtractionRule
from equitylens_normalization.normalizers import doe_s17


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


def test_grid_layout_parses_cohort_range_headers(resolver) -> None:
    grid = pd.DataFrame(
        [
            [None, None, "2005-2013", "2006-2014"],
            ["Table A institutions", None, None, None],
            ["New South Wales", "Charles Sturt University", 62.3, 61.3],
        ]
    )
    rule = ExtractionRule(
        source_id="doe_s17_2018",
        target_fact="fact_completion_cohort",
        header_style="s17_cohort_table",
        sheet="T4",
        options={
            "layout_kind": "grid",
            "name_col": 1,
            "state_col": 0,
            "header_row": 0,
            "data_start_row": 1,
            "value_start_col": 2,
            "tracking_window_years": 9,
            "metric_definition": "domestic_bachelor__table_ab",
            "is_annual_release": False,
        },
    )
    records = doe_s17.normalize(rule, grid, resolver, source_year=2018)
    assert {r.institution_raw for r in records} == {"csu"}
    by_year = {r.year: r.value for r in records}
    assert by_year == {2013: 62.3, 2014: 61.3}
    assert all(r.dimensions["tracking_window_years"] == "9" for r in records)
    assert all(r.metadata["is_annual_release"] == "False" for r in records)


def test_tidy_layout_parses_duration_and_timeframe(resolver) -> None:
    grid = pd.DataFrame(
        [
            ["State", "Institution", "Duration", "Timeframe", "Completed", "StillEnrolled"],
            ["National Totals", "Table A and B Providers", "Four Years", "2012-2015", 44.25, 34.24],
            ["New South Wales", "Charles Sturt University", "Four Years", "2012-2015", 62.3, 20.1],
            ["New South Wales", "Charles Sturt University", "Nine Years", "2007-2015", 79.3, 5.0],
        ]
    )
    rule = ExtractionRule(
        source_id="doe_s17_2024",
        target_fact="fact_completion_cohort",
        header_style="s17_cohort_table",
        sheet="17.3",
        options={
            "layout_kind": "tidy",
            "institution_col": 1,
            "duration_col": 2,
            "timeframe_col": 3,
            "data_start_row": 1,
            "metric_definition": "domestic_bachelor",
            "is_annual_release": True,
            "skip_institution_labels": ["Table A and B Providers"],
            "metric_columns": [
                {"column": 4, "metric": "completion_rate"},
                {"column": 5, "metric": "still_enrolled"},
            ],
        },
    )
    records = doe_s17.normalize(rule, grid, resolver, source_year=2024)
    assert {r.institution_raw for r in records} == {"csu"}
    completion = {
        (r.year, r.dimensions["tracking_window_years"]): r.value
        for r in records
        if r.metric == "completion_rate"
    }
    assert completion == {(2015, "4"): 62.3, (2015, "9"): 79.3}
