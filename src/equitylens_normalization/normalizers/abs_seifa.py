"""ABS SEIFA normalizer.

Each summary sheet (`Table 1`) carries four index families side by side
(IRSD, IRSAD, IER, IEO) over a 2-row merged header: a family-name row and a
`Score`/`Decile` sub-header row. Column layout differs between the postcode
(POA) and SA2 sheets (SA2 has an extra geo-name column shifting every
subsequent column by one), so column indices are supplied per source in
`extraction_map.yml` rather than assumed in code. DoE's own Section 11
footnote defines "Low SES" as the bottom 25% of the **Index of Education and
Occupation** specifically -- `is_low_ses_calibration_target` flags that one
family; the other three are retained but are not the equity calibration
target.
"""

from __future__ import annotations

import pandas as pd

from equitylens_normalization.institution_map import InstitutionResolver
from equitylens_normalization.models import ExtractionRule, LongRecord
from equitylens_normalization.normalizers._shared import parse_value


def normalize(
    rule: ExtractionRule,
    grid: pd.DataFrame,
    _resolver: InstitutionResolver,
    *,
    source_year: int,
) -> list[LongRecord]:
    options = rule.options
    geo_level = options["geo_level"]
    geo_code_column = options["geo_code_column"]
    geo_name_column = options.get("geo_name_column")
    population_column = options.get("population_column")
    caution_flag_columns = options.get("caution_flag_columns", [])
    data_start_row = options["data_start_row"]

    records: list[LongRecord] = []
    for row_index in range(data_start_row, len(grid)):
        code_cell = grid.iloc[row_index, geo_code_column]
        if pd.isna(code_cell):
            continue
        geo_code = str(code_cell).strip()

        geo_name = ""
        if geo_name_column is not None:
            name_cell = grid.iloc[row_index, geo_name_column]
            geo_name = "" if pd.isna(name_cell) else str(name_cell).strip()

        population_value = None
        if population_column is not None:
            population_value, _ = parse_value(grid.iloc[row_index, population_column])

        caution_area = len(caution_flag_columns) >= 1 and not pd.isna(
            grid.iloc[row_index, caution_flag_columns[0]]
        )
        caution_boundary = len(caution_flag_columns) >= 2 and not pd.isna(
            grid.iloc[row_index, caution_flag_columns[1]]
        )

        for entry in options["index_families"]:
            score_value, score_suppressed = parse_value(grid.iloc[row_index, entry["score_col"]])
            decile_value, decile_suppressed = parse_value(grid.iloc[row_index, entry["decile_col"]])
            records.append(
                LongRecord(
                    source_id=rule.source_id,
                    source_sheet=rule.sheet or "",
                    target_fact=rule.target_fact,
                    year=source_year,
                    metric="seifa_index",
                    value=score_value,
                    suppressed_flag=score_suppressed or decile_suppressed,
                    institution_raw=None,
                    state_raw=None,
                    equity_group="not_disaggregated",
                    metric_definition=entry["family"],
                    dimensions={
                        "geo_level": geo_level,
                        "geo_code": geo_code,
                        "geo_name": geo_name,
                        "index_family": entry["family"],
                        "is_low_ses_calibration_target": str(
                            bool(entry.get("is_low_ses_calibration_target", False))
                        ),
                        "caution_flag_area": str(caution_area),
                        "caution_flag_boundary": str(caution_boundary),
                    },
                    measures={"decile": decile_value, "population": population_value},
                )
            )
    return records
