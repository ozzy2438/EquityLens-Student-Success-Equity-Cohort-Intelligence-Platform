from __future__ import annotations

import zipfile
from pathlib import Path

import openpyxl
import pandas as pd

from equitylens_normalization.readers.grid_reader import list_sheet_names, read_grid


def _write_xlsx(path: Path) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Table 1"
    sheet.append(["institution", "value"])
    sheet.append(["Example University", "< 5"])
    workbook.create_sheet("Notes")
    workbook.save(path)


def test_read_grid_from_plain_xlsx(tmp_path: Path) -> None:
    path = tmp_path / "book.xlsx"
    _write_xlsx(path)
    grid = read_grid(path, "Table 1")
    assert isinstance(grid, pd.DataFrame)
    assert grid.iloc[0, 0] == "institution"
    assert grid.iloc[1, 1] == "< 5"


def test_list_sheet_names_from_plain_xlsx(tmp_path: Path) -> None:
    path = tmp_path / "book.xlsx"
    _write_xlsx(path)
    assert list_sheet_names(path) == ["Table 1", "Notes"]


def test_read_grid_from_zip_member(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "inner.xlsx"
    _write_xlsx(xlsx_path)
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(xlsx_path, arcname="inner.xlsx")

    grid = read_grid(zip_path, "Table 1", workbook_member="inner.xlsx")
    assert grid.iloc[1, 0] == "Example University"
    assert list_sheet_names(zip_path, workbook_member="inner.xlsx") == ["Table 1", "Notes"]
