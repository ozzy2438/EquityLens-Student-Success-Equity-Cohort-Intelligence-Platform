from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

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


def test_zip_inventory_records_contained_workbook(tmp_path: Path, xlsx_bytes: bytes) -> None:
    path = tmp_path / "report-tables.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("SES_Report_Tables.xlsx", xlsx_bytes)
        archive.writestr("SES_Report_Tables.ods", b"not inspected")

    sheets = inspect_workbook(path, "zip")
    assert len(sheets) == 2
    assert {sheet["workbook"] for sheet in sheets} == {"SES_Report_Tables.xlsx"}
    assert sheets[0]["name"] == "Summary"
    assert sheets[0]["rows"] == 2


def test_xlsx_inventory_repairs_incorrect_a1_dimension(tmp_path: Path, xlsx_bytes: bytes) -> None:
    source = BytesIO(xlsx_bytes)
    path = tmp_path / "incorrect-dimension.xlsx"
    with ZipFile(source) as input_archive, ZipFile(path, "w") as output_archive:
        for member in input_archive.infolist():
            content = input_archive.read(member.filename)
            if member.filename == "xl/worksheets/sheet1.xml":
                content = content.replace(b'<dimension ref="A1:B2"/>', b'<dimension ref="A1"/>')
            output_archive.writestr(member, content)

    sheets = inspect_workbook(path, "xlsx")
    assert sheets[0]["rows"] == 2
    assert sheets[0]["columns"] == 2
