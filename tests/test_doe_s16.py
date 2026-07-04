from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from equitylens_normalization.institution_map import load_institution_map
from equitylens_normalization.models import ExtractionRule
from equitylens_normalization.normalizers import doe_s16


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
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return load_institution_map(path)


def test_flat_group_category_layout_resolves_seifa_vintage(resolver) -> None:
    grid = pd.DataFrame(
        [
            [None, None, "All Domestic(2.05)", None, "Low SES by SA1(5.09)", None],
            [
                "Group",
                "Category",
                2020,
                2021,
                "2021 (2016 SEIFA)",
                "2021 (2021 SEIFA)",
            ],
            ["Australia", "National Total", 1000, 1100, 200, 210],
            ["State and Territory", "New South Wales", 400, 420, 80, 82],
            ["Higher Education Institution", "Australian Catholic University", 90, 95, 12, 13],
        ]
    )
    rule = ExtractionRule(
        source_id="doe_s16_2024",
        target_fact="fact_equity_performance",
        header_style="s16_institution_block",
        sheet="16.1",
        options={
            "layout": "flat_group_category",
            "group_col": 0,
            "category_col": 1,
            "category_header_row": 0,
            "year_header_row": 1,
            "data_start_row": 2,
            "value_start_col": 2,
            "metric": "commencing_domestic_students",
        },
    )
    records = doe_s16.normalize(rule, grid, resolver, source_year=2024)

    # Only the institution-grain row contributes facts.
    assert {r.institution_raw for r in records} == {"acu"}
    by_key = {(r.equity_group, r.year): (r.value, r.metric_definition) for r in records}
    assert by_key[("all_domestic", 2020)] == (90.0, None)
    assert by_key[("all_domestic", 2021)] == (95.0, None)
    assert by_key[("low_ses_by_sa1", 2021)] in {(12.0, "2016 SEIFA"), (13.0, "2021 SEIFA")}
    # Both SEIFA vintages for 2021 must be kept distinct, not collapsed.
    vintages = {r.metric_definition for r in records if r.equity_group == "low_ses_by_sa1"}
    assert vintages == {"2016 SEIFA", "2021 SEIFA"}


def test_legacy_equity_group_labels_are_canonicalised(resolver) -> None:
    # "Indigenous"/"Domestic National Total" (pre-2020 wording) and
    # "First Nations"/"All Domestic" (current wording) are the same underlying
    # equity group -- confirmed empirically by identical overlapping-year
    # values in the real corpus. Without canonicalisation they would sit as
    # separate equity_group_id values and a query for one would silently miss
    # the other era's years.
    grid = pd.DataFrame(
        [
            [None, None, "Domestic National Total", "Indigenous(b)"],
            ["Group", "Category", 2018, 2018],
            ["Higher Education Institution", "Australian Catholic University", 500, 189],
        ]
    )
    rule = ExtractionRule(
        source_id="doe_s16_2019",
        target_fact="fact_equity_performance",
        header_style="s16_institution_block",
        sheet="1a",
        options={
            "layout": "flat_group_category",
            "group_col": 0,
            "category_col": 1,
            "category_header_row": 0,
            "year_header_row": 1,
            "data_start_row": 2,
            "value_start_col": 2,
            "metric": "access_numbers",
        },
    )
    records = doe_s16.normalize(rule, grid, resolver, source_year=2019)
    assert {r.equity_group for r in records} == {"all_domestic", "first_nations"}


def test_comma_separated_footnote_markers_are_stripped_from_equity_labels(resolver) -> None:
    # "First Address Regional(d,e)" must collapse to the same equity_group as
    # a cleanly-footnoted "First Address Regional" from another year -- an
    # earlier version of the footnote-stripping regex only matched a single
    # token with no internal punctuation, so "(d,e)" survived and produced a
    # spurious "first_address_regional_d_e" alongside the real label.
    grid = pd.DataFrame(
        [
            [None, None, "First Address Regional(d,e)"],
            ["Group", "Category", 2019],
            ["Higher Education Institution", "Australian Catholic University", 42],
        ]
    )
    rule = ExtractionRule(
        source_id="doe_s16_2019",
        target_fact="fact_equity_performance",
        header_style="s16_institution_block",
        sheet="1a",
        options={
            "layout": "flat_group_category",
            "group_col": 0,
            "category_col": 1,
            "category_header_row": 0,
            "year_header_row": 1,
            "data_start_row": 2,
            "value_start_col": 2,
            "metric": "access_numbers",
        },
    )
    records = doe_s16.normalize(rule, grid, resolver, source_year=2019)
    assert records[0].equity_group == "first_address_regional"


def test_pseudo_header_single_column_layout_ignores_state_aggregates(resolver) -> None:
    grid = pd.DataFrame(
        [
            [None, "Domestic National Total", None],
            [None, 2018, 2019],
            ["Australia", None, None],
            ["National Total", 500, 520],  # real values, must not be resolved as an institution
            ["New South Wales", 200, 210],  # state aggregate, also not an institution
            ["Higher Education Institution", None, None],
            ["Australian Catholic University", 80, 85],
        ]
    )
    rule = ExtractionRule(
        source_id="doe_s16_2018",
        target_fact="fact_equity_performance",
        header_style="s16_institution_block",
        sheet="1a",
        options={
            "layout": "pseudo_header_single_column",
            "name_col": 0,
            "category_header_row": 0,
            "year_header_row": 1,
            "data_start_row": 2,
            "value_start_col": 1,
            "metric": "access_numbers",
        },
    )
    records = doe_s16.normalize(rule, grid, resolver, source_year=2018)
    assert {r.institution_raw for r in records} == {"acu"}
    assert {(r.year, r.value) for r in records} == {(2018, 80.0), (2019, 85.0)}
