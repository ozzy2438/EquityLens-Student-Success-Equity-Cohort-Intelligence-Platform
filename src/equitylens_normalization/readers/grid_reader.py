"""Uniform raw-cell-grid access for `.xls`, `.xlsx`, and zip-contained workbooks.

Both legacy `.xls` (via `xlrd`) and modern `.xlsx` (via `openpyxl`) are read
through `pandas.read_excel(..., header=None, dtype=object)`, which returns the
sheet as a plain 2D grid of publisher values -- numbers as floats, text
(including suppression tokens like ``"< 5"`` and ``"np"``) as strings,
genuinely empty cells as NaN. Normalizers interpret this grid themselves;
this module only handles *access*, never structure.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd


def read_grid(path: Path, sheet: str, *, workbook_member: str | None = None) -> pd.DataFrame:
    """Return one sheet as a header-less, dtype-preserving grid."""

    if workbook_member is not None:
        with zipfile.ZipFile(path) as archive:
            data = archive.read(workbook_member)
        return pd.read_excel(io.BytesIO(data), sheet_name=sheet, header=None, dtype=object)
    return pd.read_excel(path, sheet_name=sheet, header=None, dtype=object)


def list_sheet_names(path: Path, *, workbook_member: str | None = None) -> list[str]:
    """Return the ordered sheet names of a workbook (or a zip member workbook)."""

    if workbook_member is not None:
        with zipfile.ZipFile(path) as archive:
            data = archive.read(workbook_member)
        return pd.ExcelFile(io.BytesIO(data)).sheet_names
    return pd.ExcelFile(path).sheet_names
