from __future__ import annotations

import pandas as pd

from equitylens_normalization.models import ExtractionRule
from equitylens_normalization.normalizers import abs_seifa


def test_poa_layout_flags_ieo_as_low_ses_target() -> None:
    grid = pd.DataFrame(
        [
            [None, "IRSD", None, "IEO", None, None, None],
            ["POA", "Score", "Decile", "Score", "Decile", "Population", None],
            ["0800", 1064.3, 9, 1089.6, 9, 7149, None],
            ["0810", "np", 7, 1047.6, 8, 34330, None],
        ]
    )
    rule = ExtractionRule(
        source_id="abs_seifa_poa_2021",
        target_fact="fact_seifa",
        header_style="two_row_merged_seifa",
        sheet="Table 1",
        options={
            "geo_level": "poa",
            "geo_code_column": 0,
            "data_start_row": 2,
            "population_column": 5,
            "caution_flag_columns": [],
            "index_families": [
                {"family": "irsd", "score_col": 1, "decile_col": 2},
                {
                    "family": "ieo",
                    "score_col": 3,
                    "decile_col": 4,
                    "is_low_ses_calibration_target": True,
                },
            ],
        },
    )
    records = abs_seifa.normalize(rule, grid, None, source_year=2021)

    ieo = [
        r for r in records if r.metric_definition == "ieo" and r.dimensions["geo_code"] == "0800"
    ]
    assert ieo[0].value == 1089.6
    assert ieo[0].dimensions["is_low_ses_calibration_target"] == "True"

    irsd_suppressed = [
        r for r in records if r.metric_definition == "irsd" and r.dimensions["geo_code"] == "0810"
    ]
    assert irsd_suppressed[0].suppressed_flag is True
    assert irsd_suppressed[0].value is None
    assert irsd_suppressed[0].dimensions["is_low_ses_calibration_target"] == "False"


def test_sa2_layout_includes_geo_name() -> None:
    grid = pd.DataFrame(
        [
            ["SA2 Code", "SA2 Name", "Score", "Decile"],
            ["101021007", "Braidwood", 1024, 6],
        ]
    )
    rule = ExtractionRule(
        source_id="abs_seifa_sa2_2021",
        target_fact="fact_seifa",
        header_style="two_row_merged_seifa",
        sheet="Table 1",
        options={
            "geo_level": "sa2",
            "geo_code_column": 0,
            "geo_name_column": 1,
            "data_start_row": 1,
            "index_families": [{"family": "irsd", "score_col": 2, "decile_col": 3}],
        },
    )
    records = abs_seifa.normalize(rule, grid, None, source_year=2021)
    assert records[0].dimensions["geo_name"] == "Braidwood"
    assert records[0].measures["decile"] == 6.0
