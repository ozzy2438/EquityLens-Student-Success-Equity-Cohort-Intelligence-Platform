"""QILT Student Experience Survey normalizer.

Of QILT's 172 report-table sheets, only those matching `rule.sheet_pattern`
(a regex full-matched against the workbook's real sheet names, e.g.
`FOCUS_UG_UNI_1Y_INST_CI`) are institution-grain; the rest are national/
state/category rollups out of scope for `fact_ses_experience`. Scope is
further narrowed to university-level, single-latest-year (`1Y`) sheets --
QILT's NUHEI-level sheets list ~100 small colleges with no DoE counterpart
and no bearing on ACU peer benchmarking, and multi-year trend sheets
(`17-YY` etc.) are a different grain than this fact's single-year rows. See
`docs/schema.md` for the disclosed scope note.

Cell values are packed strings like `"83.6 (82.8, 84.3)"` (point estimate +
90% CI) or, when the estimate is exactly 100%, a bare `"100.0"` with no CI --
`rule.options["value_pattern"]` must accommodate both, and does.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from equitylens_normalization.institution_map import InstitutionResolver
from equitylens_normalization.models import ExtractionRule, LongRecord
from equitylens_normalization.normalizers._shared import is_aggregate_row, slugify
from equitylens_normalization.readers.grid_reader import list_sheet_names, read_grid


def normalize(
    rule: ExtractionRule,
    workbook_path: Path,
    resolver: InstitutionResolver,
    *,
    source_year: int,
) -> list[LongRecord]:
    options = rule.options
    sheet_pattern = re.compile(rule.sheet_pattern or "")
    value_pattern = re.compile(options["value_pattern"])
    name_pattern = re.compile(options["sheet_name_pattern"])
    header_row = options["header_row"]
    institution_col = options["institution_col"]
    data_start_row = options["data_start_row"]

    records: list[LongRecord] = []
    for sheet in list_sheet_names(workbook_path, workbook_member=rule.workbook_member):
        if not sheet_pattern.fullmatch(sheet):
            continue
        name_match = name_pattern.fullmatch(sheet)
        if not name_match:
            raise ValueError(
                f"QILT sheet {sheet!r} matched sheet_pattern but not sheet_name_pattern"
            )
        level = name_match.group("level").lower()
        provider_type = name_match.group("provider_type").lower()
        year_scope = name_match.group("year_scope").lower()

        grid = read_grid(workbook_path, sheet, workbook_member=rule.workbook_member)
        focus_area_columns: dict[int, str] = {}
        for column in range(institution_col + 1, grid.shape[1]):
            cell = grid.iloc[header_row, column]
            if pd.isna(cell):
                continue
            focus_area_columns[column] = slugify(cell)

        for row_index in range(data_start_row, len(grid)):
            institution_cell = grid.iloc[row_index, institution_col]
            if pd.isna(institution_cell):
                continue
            institution_raw = str(institution_cell).strip()
            if is_aggregate_row(institution_raw, tuple(options.get("skip_institution_labels", ()))):
                continue
            institution = resolver.resolve(institution_raw, context=f"{rule.source_id}:{sheet}")

            for column, focus_area in focus_area_columns.items():
                raw_cell = grid.iloc[row_index, column]
                value: float | None
                ci_low: float | None
                ci_high: float | None
                suppressed = False
                if pd.isna(raw_cell):
                    value = ci_low = ci_high = None
                else:
                    text = str(raw_cell).strip()
                    match = value_pattern.match(text)
                    if not match:
                        raise ValueError(
                            f"Unparseable QILT value {text!r} in {sheet!r} "
                            f"row {row_index} col {column}"
                        )
                    value = float(match.group("value"))
                    ci_low = float(match.group("ci_low")) if match.group("ci_low") else None
                    ci_high = float(match.group("ci_high")) if match.group("ci_high") else None

                records.append(
                    LongRecord(
                        source_id=rule.source_id,
                        source_sheet=sheet,
                        target_fact=rule.target_fact,
                        year=source_year,
                        metric=focus_area,
                        value=value,
                        suppressed_flag=suppressed,
                        institution_raw=institution.canonical_id,
                        state_raw=None,
                        equity_group="not_disaggregated",
                        metric_definition=None,
                        dimensions={
                            "level": level,
                            "provider_type": provider_type,
                            "year_scope": year_scope,
                        },
                        measures={"ci_low": ci_low, "ci_high": ci_high},
                    )
                )
    return records
