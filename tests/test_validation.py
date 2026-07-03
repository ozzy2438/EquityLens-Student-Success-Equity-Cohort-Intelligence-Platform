from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from equitylens_ingestion.errors import ValidationError
from equitylens_ingestion.validation import looks_like_html, validate_download


@pytest.mark.parametrize(
    "body",
    [b"<html>denied</html>", b"  <!DOCTYPE HTML><title>Error</title>", b"\xef\xbb\xbf<body>x"],
)
def test_html_detection(body: bytes) -> None:
    assert looks_like_html(body)


def test_valid_xlsx_is_accepted(write_file, xlsx_bytes: bytes) -> None:
    validate_download(
        write_file(xlsx_bytes),
        "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def test_html_content_type_is_rejected(write_file) -> None:
    with pytest.raises(ValidationError, match="HTML"):
        validate_download(write_file(b"access denied"), "xlsx", "text/html; charset=utf-8")


def test_html_body_is_rejected_even_with_excel_mime(write_file) -> None:
    with pytest.raises(ValidationError, match="HTML"):
        validate_download(write_file(b"<html>error</html>"), "xlsx", "application/octet-stream")


def test_empty_file_is_rejected(write_file) -> None:
    with pytest.raises(ValidationError, match="empty"):
        validate_download(write_file(b""), "csv", "text/csv")


def test_non_zip_xlsx_is_rejected(write_file) -> None:
    with pytest.raises(ValidationError, match="ZIP"):
        validate_download(write_file(b"not excel"), "xlsx", None)


def test_xlsx_missing_workbook_member_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "x")
    with pytest.raises(ValidationError, match="missing required"):
        validate_download(path, "xlsx", None)


def test_valid_and_invalid_xls_signatures(write_file) -> None:
    validate_download(write_file(bytes.fromhex("D0CF11E0A1B11AE1") + b"x"), "xls", None)
    with pytest.raises(ValidationError, match="OLE"):
        validate_download(write_file(b"PK fake", "bad.xls"), "xls", None)


def test_valid_csv_is_accepted(write_file) -> None:
    validate_download(write_file(b"institution,rate\nA,90\n"), "csv", "text/csv")


@pytest.mark.parametrize("body", [b"only-one-column\nvalue\n", b"a\x00b,c\n"])
def test_invalid_csv_is_rejected(write_file, body: bytes) -> None:
    with pytest.raises(ValidationError):
        validate_download(write_file(body), "csv", "text/csv")
