from pathlib import Path

from equitylens_ingestion.inventory import inspect_workbook


def test_xlsx_inventory_records_structure(write_file, xlsx_bytes: bytes) -> None:
    sheets = inspect_workbook(write_file(xlsx_bytes, "book.xlsx"), "xlsx")
    assert sheets == [
        {
            "position": 1,
            "name": "Summary",
            "visibility": "visible",
            "rows": 2,
            "columns": 2,
        },
        {
            "position": 2,
            "name": "Notes",
            "visibility": "hidden",
            "rows": 1,
            "columns": 1,
        },
    ]


def test_non_workbook_has_empty_inventory(tmp_path: Path) -> None:
    assert inspect_workbook(tmp_path / "unused.csv", "csv") == []


def test_xls_inventory_uses_sheet_visibility(monkeypatch, tmp_path: Path) -> None:
    class Sheet:
        def __init__(self, visibility: int) -> None:
            self.visibility = visibility
            self.nrows = 3
            self.ncols = 4

    class Book:
        def __init__(self) -> None:
            self.released = False
            self.sheets = [Sheet(0), Sheet(2)]

        def sheet_names(self):
            return ["Visible", "Internal"]

        def sheet_by_index(self, index):
            return self.sheets[index]

        def release_resources(self):
            self.released = True

    book = Book()
    monkeypatch.setattr(
        "equitylens_ingestion.inventory.xlrd.open_workbook", lambda *_args, **_kwargs: book
    )
    sheets = inspect_workbook(tmp_path / "legacy.part", "xls")
    assert [sheet["visibility"] for sheet in sheets] == ["visible", "very_hidden"]
    assert book.released is True
