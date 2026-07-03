"""Content validation performed before raw artifacts are promoted."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path, PurePosixPath

from equitylens_ingestion.errors import ValidationError

_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
_HTML_PREFIXES = (b"<!doctype html", b"<html", b"<head", b"<body")
_XLSX_MEMBERS = {"[Content_Types].xml", "xl/workbook.xml"}
_TABULAR_ARCHIVE_SUFFIXES = {".csv", ".xls", ".xlsx"}


def looks_like_html(prefix: bytes) -> bool:
    """Detect common HTML error and access-denied response bodies."""

    normalized = prefix.lstrip(b"\xef\xbb\xbf\x00\t\r\n ").lower()
    return any(normalized.startswith(marker) for marker in _HTML_PREFIXES)


def validate_download(path: Path, expected_format: str, content_type: str | None) -> None:
    """Reject empty, HTML, corrupt, or format-mismatched downloads."""

    if not path.is_file() or path.stat().st_size == 0:
        raise ValidationError("Downloaded file is empty")
    with path.open("rb") as handle:
        prefix = handle.read(4096)
    lowered_type = (content_type or "").lower()
    if "text/html" in lowered_type or looks_like_html(prefix):
        raise ValidationError("Publisher returned HTML instead of a data file")

    if expected_format == "xlsx":
        _validate_xlsx(path)
    elif expected_format == "xls":
        if not prefix.startswith(_OLE_SIGNATURE):
            raise ValidationError("File does not have the legacy Excel OLE signature")
    elif expected_format == "csv":
        _validate_csv(path)
    elif expected_format == "zip":
        _validate_zip(path)
    else:  # Defensive: registry validation should prevent this branch.
        raise ValidationError(f"Unsupported expected format: {expected_format}")


def _validate_xlsx(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        raise ValidationError("File is not a valid XLSX ZIP container")
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            missing = _XLSX_MEMBERS - names
            if missing:
                raise ValidationError(
                    f"XLSX container is missing required members: {sorted(missing)}"
                )
            corrupt_member = archive.testzip()
            if corrupt_member:
                raise ValidationError(f"XLSX contains corrupt member: {corrupt_member}")
    except zipfile.BadZipFile as exc:
        raise ValidationError("File is not a readable XLSX container") from exc


def _validate_csv(path: Path) -> None:
    try:
        sample = path.read_text(encoding="utf-8-sig")[:8192]
    except UnicodeDecodeError as exc:
        raise ValidationError("CSV is not valid UTF-8") from exc
    if "\x00" in sample:
        raise ValidationError("CSV contains binary null bytes")
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        first_row = next(csv.reader(io.StringIO(sample), dialect))
    except (csv.Error, StopIteration) as exc:
        raise ValidationError("CSV delimiter or first row could not be parsed") from exc
    if len(first_row) < 2:
        raise ValidationError("CSV must contain at least two columns")


def _validate_zip(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        raise ValidationError("File is not a valid ZIP container")
    try:
        with zipfile.ZipFile(path) as archive:
            members = [member for member in archive.namelist() if not member.endswith("/")]
            if any(_unsafe_archive_member(member) for member in members):
                raise ValidationError("ZIP contains an unsafe member path")
            tabular_members = [
                member
                for member in members
                if PurePosixPath(member).suffix.lower() in _TABULAR_ARCHIVE_SUFFIXES
            ]
            if not tabular_members:
                raise ValidationError("ZIP does not contain a supported tabular data file")
            corrupt_member = archive.testzip()
            if corrupt_member:
                raise ValidationError(f"ZIP contains corrupt member: {corrupt_member}")
    except zipfile.BadZipFile as exc:
        raise ValidationError("File is not a readable ZIP container") from exc


def _unsafe_archive_member(member: str) -> bool:
    normalized = PurePosixPath(member.replace("\\", "/"))
    return normalized.is_absolute() or ".." in normalized.parts
