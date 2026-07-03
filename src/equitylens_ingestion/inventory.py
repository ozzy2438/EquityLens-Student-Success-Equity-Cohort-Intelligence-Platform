"""Workbook structure inventory without transforming raw data."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import xlrd

from equitylens_ingestion.models import JsonObject


def inspect_workbook(path: Path, expected_format: str) -> list[JsonObject]:
    """Return sheet names, order, visibility, and observed dimensions."""

    if expected_format == "xlsx":
        # A file object avoids openpyxl rejecting the required `.part` suffix.
        with path.open("rb") as handle:
            workbook = openpyxl.load_workbook(handle, read_only=True, data_only=False)
            try:
                return [
                    {
                        "position": position,
                        "name": sheet.title,
                        "visibility": sheet.sheet_state,
                        "rows": sheet.max_row,
                        "columns": sheet.max_column,
                    }
                    for position, sheet in enumerate(workbook.worksheets, start=1)
                ]
            finally:
                workbook.close()
    if expected_format == "xls":
        workbook = xlrd.open_workbook(path, on_demand=True)
        try:
            sheets: list[JsonObject] = []
            visibility_labels = {0: "visible", 1: "hidden", 2: "very_hidden"}
            for position, sheet_name in enumerate(workbook.sheet_names(), start=1):
                sheet = workbook.sheet_by_index(position - 1)
                sheets.append(
                    {
                        "position": position,
                        "name": sheet_name,
                        "visibility": visibility_labels.get(sheet.visibility, "unknown"),
                        "rows": sheet.nrows,
                        "columns": sheet.ncols,
                    }
                )
            return sheets
        finally:
            workbook.release_resources()
    return []
