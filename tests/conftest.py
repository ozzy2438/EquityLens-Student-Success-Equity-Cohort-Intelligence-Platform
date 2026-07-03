from __future__ import annotations

from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

from equitylens_ingestion.models import Source


@pytest.fixture
def source() -> Source:
    return Source(
        source_id="doe_s15_2024",
        publisher="Department of Education",
        dataset="Selected Higher Education Statistics",
        section="15",
        year=2024,
        status="active",
        publication_url="https://official.example/publication",
        download_url="https://official.example/download.xlsx",
        expected_format="xlsx",
        published_at="2025-09-08",
        allowed_hosts=("official.example",),
    )


@pytest.fixture
def xlsx_bytes() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Summary"
    sheet.append(["institution", "retention_rate"])
    sheet.append(["Example University", 88.5])
    hidden = workbook.create_sheet("Notes")
    hidden.sheet_state = "hidden"
    hidden["A1"] = "Publisher notes"
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


@pytest.fixture
def write_file(tmp_path: Path):
    def _write(content: bytes, name: str = "artifact.part") -> Path:
        path = tmp_path / name
        path.write_bytes(content)
        return path

    return _write
