"""Section 16 (equity performance) normalizer.

S16 institution tables have no per-row state column at all, and use one of
two row-grouping layouts depending on era:

- `layout: "flat_group_category"` (2021+ `.xlsx`): a `Group` column stacks
  three pseudo-header blocks ("Australia", "State and Territory", "Higher
  Education Institution") with the block label repeated on every row; only
  the last block is institution grain.
- `layout: "pseudo_header_single_column"` (2018-2020 `.xls`): a single name
  column where state-aggregate rows ("Australia", "New South Wales", ...)
  carry real values (not blank, so they are not detected as pseudo-headers
  by a null-column check) and only a literal `"Higher Education
  Institution"` divider row (which *is* all-blank) marks where real
  per-institution rows begin -- rows are kept only once that divider has
  been seen, discarding the preceding state-aggregate rows without
  attempting to resolve them as institutions.

Both layouts share the same 2-row merged header: a ffilled equity-group
category label row, then a year row that is sometimes SEIFA/ASGS-vintage
qualified (e.g. `"2021 (2016 SEIFA)"` vs `"2021 (2021 SEIFA)"`), kept
distinct as `metric_definition` rather than collapsed.
"""

from __future__ import annotations

import pandas as pd

from equitylens_normalization.institution_map import InstitutionResolver
from equitylens_normalization.models import ExtractionRule, LongRecord
from equitylens_normalization.normalizers._shared import (
    DEFAULT_SUPPRESSED_TOKENS,
    parse_value,
    parse_year_vintage,
    slugify,
    strip_footnote_markers,
)
from equitylens_normalization.normalizers.doe_s11 import ROLLUP_INSTITUTION_ID

INSTITUTION_GROUP_LABEL = "Higher Education Institution"

# Column header text for the same equity-group concept drifted across eras;
# confirmed empirically by comparing overlapping-year values for the same
# institution before and after each rename (identical figures under both
# labels, e.g. ACU's 2015-2019 "Indigenous" access numbers exactly match its
# "First Nations" figures for the same years in later publications). Without
# this map the two labels would sit as separate `equity_group_id` values and
# a query for one would silently miss the other's years.
_EQUITY_GROUP_ALIASES = {
    "indigenous": "first_nations",
    "domestic_national_total": "all_domestic",
}


def _canonical_equity_group(label: str) -> str:
    slug = slugify(label)
    return _EQUITY_GROUP_ALIASES.get(slug, slug)


def _build_column_labels(
    grid: pd.DataFrame, *, header_row: int, value_start_col: int
) -> dict[int, str]:
    labels: dict[int, str] = {}
    current_label: str | None = None
    for column in range(value_start_col, grid.shape[1]):
        cell = grid.iloc[header_row, column]
        if not pd.isna(cell):
            current_label = strip_footnote_markers(str(cell))
        if current_label is not None:
            labels[column] = current_label
    return labels


def _build_year_vintage(
    grid: pd.DataFrame, *, header_row: int, value_start_col: int
) -> dict[int, tuple[int, str | None]]:
    year_vintage: dict[int, tuple[int, str | None]] = {}
    for column in range(value_start_col, grid.shape[1]):
        cell = grid.iloc[header_row, column]
        if pd.isna(cell):
            continue
        year_vintage[column] = parse_year_vintage(cell)
    return year_vintage


def _iter_institution_rows_flat_group_category(grid, options):
    group_col = options["group_col"]
    category_col = options["category_col"]
    for row_index in range(options["data_start_row"], len(grid)):
        group_cell = grid.iloc[row_index, group_col]
        if pd.isna(group_cell) or str(group_cell).strip() != INSTITUTION_GROUP_LABEL:
            continue
        institution_cell = grid.iloc[row_index, category_col]
        if pd.isna(institution_cell):
            continue
        yield row_index, str(institution_cell).strip()


def _iter_institution_rows_pseudo_header_single_column(grid, options):
    name_col = options["name_col"]
    value_start_col = options["value_start_col"]
    n_cols = grid.shape[1]
    seen_institution_divider = False
    for row_index in range(options["data_start_row"], len(grid)):
        name_cell = grid.iloc[row_index, name_col]
        if pd.isna(name_cell):
            continue
        name_text = str(name_cell).strip()
        all_values_null = all(
            pd.isna(grid.iloc[row_index, c]) for c in range(value_start_col, n_cols)
        )
        if all_values_null:
            seen_institution_divider = name_text == INSTITUTION_GROUP_LABEL
            continue
        if not seen_institution_divider:
            continue
        yield row_index, name_text


_ROW_ITERATORS = {
    "flat_group_category": _iter_institution_rows_flat_group_category,
    "pseudo_header_single_column": _iter_institution_rows_pseudo_header_single_column,
}


def normalize(
    rule: ExtractionRule,
    grid: pd.DataFrame,
    resolver: InstitutionResolver,
    *,
    source_year: int,
) -> list[LongRecord]:
    options = rule.options
    category_header_row = options["category_header_row"]
    year_header_row = options["year_header_row"]
    value_start_col = options["value_start_col"]
    suppressed_tokens = tuple(options.get("suppressed_tokens", DEFAULT_SUPPRESSED_TOKENS))
    metric = options["metric"]

    equity_group_labels = _build_column_labels(
        grid, header_row=category_header_row, value_start_col=value_start_col
    )
    year_vintage = _build_year_vintage(
        grid, header_row=year_header_row, value_start_col=value_start_col
    )

    row_iterator = _ROW_ITERATORS[options["layout"]]

    records: list[LongRecord] = []
    for row_index, institution_raw in row_iterator(grid, options):
        institution = resolver.resolve(institution_raw, context=f"{rule.source_id}:{rule.sheet}")
        if institution.canonical_id == ROLLUP_INSTITUTION_ID:
            continue

        for column, (year, vintage) in year_vintage.items():
            equity_label = equity_group_labels.get(column)
            if equity_label is None:
                continue
            raw_value = grid.iloc[row_index, column]
            value, suppressed = parse_value(raw_value, suppressed_tokens)
            records.append(
                LongRecord(
                    source_id=rule.source_id,
                    source_sheet=rule.sheet or "",
                    target_fact=rule.target_fact,
                    year=year,
                    metric=metric,
                    value=value,
                    suppressed_flag=suppressed,
                    institution_raw=institution.canonical_id,
                    state_raw=None,
                    equity_group=_canonical_equity_group(equity_label),
                    metric_definition=vintage,
                )
            )
    return records
