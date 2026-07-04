"""Section 15 (attrition, success, retention) normalizer.

Each S15 sheet is a single metric/metric_definition combination (e.g. "New
Adjusted Attrition Rate, domestic, Table A/B providers") in wide-year format:
one column per commencing-cohort year. The year range grows with every
publication (2005-2017 in 2018, 2005-2018 in 2019, ...), so `value_columns`
is auto-detected as the contiguous run of non-null cells in
`year_header_row` starting at `value_start_col`, rather than enumerated per
sheet. Institution tables carry no equity-group split, so `equity_group` is
always `not_disaggregated`. Row grouping reuses the same
`inline_state_pseudo_header` / `state_institution_columns` mechanism as
Section 11; sector-aggregate rows ("Australia", "National Total", "Table
A/B Providers") that precede the first real state group carry real values
(not all-null), so they are skipped via the shared `is_aggregate_row` label
check rather than the pseudo-header null-column detector.
"""

from __future__ import annotations

import pandas as pd

from equitylens_normalization.institution_map import InstitutionResolver
from equitylens_normalization.models import ExtractionRule, LongRecord
from equitylens_normalization.normalizers._shared import (
    DEFAULT_STOP_MARKERS,
    DEFAULT_SUPPRESSED_TOKENS,
    is_aggregate_row,
    iter_institution_rows,
    parse_value,
)
from equitylens_normalization.normalizers.doe_s11 import ROLLUP_INSTITUTION_ID


def normalize(
    rule: ExtractionRule,
    grid: pd.DataFrame,
    resolver: InstitutionResolver,
    *,
    source_year: int,
) -> list[LongRecord]:
    options = rule.options
    year_header_row = options["year_header_row"]
    value_start_col = options["value_start_col"]

    years: dict[int, int] = {}
    column = value_start_col
    while column < grid.shape[1] and not pd.isna(grid.iloc[year_header_row, column]):
        years[column] = int(float(grid.iloc[year_header_row, column]))
        column += 1
    value_columns = tuple(years.keys())

    suppressed_tokens = tuple(options.get("suppressed_tokens", DEFAULT_SUPPRESSED_TOKENS))
    stop_markers = tuple(options.get("stop_markers", DEFAULT_STOP_MARKERS))
    metric = options["metric"]
    metric_definition = options.get("metric_definition")

    records: list[LongRecord] = []
    for state_raw, institution_raw, row_index in iter_institution_rows(
        grid,
        layout=options["layout"],
        name_col=options["name_col"],
        value_columns=value_columns,
        state_col=options.get("state_col"),
        data_start_row=options["data_start_row"],
        stop_markers=stop_markers,
    ):
        if is_aggregate_row(institution_raw, tuple(options.get("skip_institution_labels", ()))):
            continue
        institution = resolver.resolve(institution_raw, context=f"{rule.source_id}:{rule.sheet}")
        if institution.canonical_id == ROLLUP_INSTITUTION_ID:
            continue

        for column in value_columns:
            raw_value = grid.iloc[row_index, column]
            value, suppressed = parse_value(raw_value, suppressed_tokens)
            records.append(
                LongRecord(
                    source_id=rule.source_id,
                    source_sheet=rule.sheet or "",
                    target_fact=rule.target_fact,
                    year=years[column],
                    metric=metric,
                    value=value,
                    suppressed_flag=suppressed,
                    institution_raw=institution.canonical_id,
                    state_raw=state_raw,
                    equity_group="not_disaggregated",
                    metric_definition=metric_definition,
                )
            )
    return records
