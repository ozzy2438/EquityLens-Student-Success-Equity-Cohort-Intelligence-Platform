"""Section 17 (completion cohort) normalizer.

S17 spans four concrete sheet shapes tied to specific source_ids, not just
file format:

- `doe_s17_2018`..`doe_s17_2022` (historical cumulative "Completion Rates
  Cohort Analyses" publications, sheets `T1`..`T12`) and `doe_s17_2023`
  (sheets `17.1`..`17.12`) share a **grid** layout: `State | Institution`
  (state blank-filled down) followed by cohort-range columns
  (`"2005-2013"`-style headers) for one fixed tracking window per sheet.
- `doe_s17_2024` restructured to an already-**tidy** layout in its
  institution-level sheet (`17.3`): one row per institution x duration x
  timeframe, with four outcome columns. Its `17.1`/`17.2` sheets are
  national-level demographic/NUHEI breakdowns with no per-institution rows
  and are intentionally out of scope (see `docs/schema.md`).

`cohort_end_year` is always the second year in a `"<start>-<end>"` range
header/cell; `is_annual_release` distinguishes the true 2023/2024 annual
releases from the 2018-2022 cumulative publications, per rule option.
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

_DURATION_YEARS = {"Four Years": 4, "Six Years": 6, "Nine Years": 9}


def _cohort_end_year(range_text: str) -> int:
    return int(str(range_text).strip().split("-")[-1])


def _normalize_grid(
    rule: ExtractionRule,
    grid: pd.DataFrame,
    resolver: InstitutionResolver,
) -> list[LongRecord]:
    options = rule.options
    header_row = options["header_row"]
    value_start_col = options["value_start_col"]

    cohort_end_years: dict[int, int] = {}
    column = value_start_col
    while column < grid.shape[1] and not pd.isna(grid.iloc[header_row, column]):
        cohort_end_years[column] = _cohort_end_year(grid.iloc[header_row, column])
        column += 1
    value_columns = tuple(cohort_end_years.keys())
    suppressed_tokens = tuple(options.get("suppressed_tokens", DEFAULT_SUPPRESSED_TOKENS))
    stop_markers = tuple(options.get("stop_markers", DEFAULT_STOP_MARKERS))
    tracking_window = options["tracking_window_years"]
    metric_definition = options.get("metric_definition")
    is_annual_release = options["is_annual_release"]

    records: list[LongRecord] = []
    for _state_raw, institution_raw, row_index in iter_institution_rows(
        grid,
        layout="two_column",
        name_col=options["name_col"],
        state_col=options["state_col"],
        value_columns=value_columns,
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
                    year=cohort_end_years[column],
                    metric="completion_rate",
                    value=value,
                    suppressed_flag=suppressed,
                    institution_raw=institution.canonical_id,
                    state_raw=None,
                    equity_group="not_disaggregated",
                    metric_definition=metric_definition,
                    dimensions={"tracking_window_years": str(tracking_window)},
                    metadata={"is_annual_release": str(is_annual_release)},
                )
            )
    return records


def _normalize_tidy(
    rule: ExtractionRule,
    grid: pd.DataFrame,
    resolver: InstitutionResolver,
) -> list[LongRecord]:
    options = rule.options
    institution_col = options["institution_col"]
    duration_col = options["duration_col"]
    timeframe_col = options["timeframe_col"]
    metric_columns = options["metric_columns"]
    skip_labels = set(options.get("skip_institution_labels", ()))
    suppressed_tokens = tuple(options.get("suppressed_tokens", DEFAULT_SUPPRESSED_TOKENS))
    metric_definition = options.get("metric_definition")
    is_annual_release = options["is_annual_release"]

    records: list[LongRecord] = []
    for row_index in range(options["data_start_row"], len(grid)):
        row = grid.iloc[row_index]
        institution_cell = row[institution_col]
        if pd.isna(institution_cell):
            continue
        institution_raw = str(institution_cell).strip()
        if is_aggregate_row(institution_raw, tuple(skip_labels)):
            continue
        duration_cell = row[duration_col]
        if pd.isna(duration_cell) or str(duration_cell).strip() not in _DURATION_YEARS:
            continue

        institution = resolver.resolve(institution_raw, context=f"{rule.source_id}:{rule.sheet}")
        if institution.canonical_id == ROLLUP_INSTITUTION_ID:
            continue

        tracking_window = _DURATION_YEARS[str(duration_cell).strip()]
        cohort_end_year = _cohort_end_year(row[timeframe_col])
        for entry in metric_columns:
            raw_value = row[entry["column"]]
            value, suppressed = parse_value(raw_value, suppressed_tokens)
            records.append(
                LongRecord(
                    source_id=rule.source_id,
                    source_sheet=rule.sheet or "",
                    target_fact=rule.target_fact,
                    year=cohort_end_year,
                    metric=entry["metric"],
                    value=value,
                    suppressed_flag=suppressed,
                    institution_raw=institution.canonical_id,
                    state_raw=None,
                    equity_group="not_disaggregated",
                    metric_definition=metric_definition,
                    dimensions={"tracking_window_years": str(tracking_window)},
                    metadata={"is_annual_release": str(is_annual_release)},
                )
            )
    return records


def normalize(
    rule: ExtractionRule,
    grid: pd.DataFrame,
    resolver: InstitutionResolver,
    *,
    source_year: int,
) -> list[LongRecord]:
    layout_kind = rule.options["layout_kind"]
    if layout_kind == "grid":
        return _normalize_grid(rule, grid, resolver)
    if layout_kind == "tidy":
        return _normalize_tidy(rule, grid, resolver)
    raise ValueError(f"Unknown S17 layout_kind: {layout_kind!r}")
