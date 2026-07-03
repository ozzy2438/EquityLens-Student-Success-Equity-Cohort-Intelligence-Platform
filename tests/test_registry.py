from __future__ import annotations

from pathlib import Path

import pytest

from equitylens_ingestion.errors import ConfigurationError
from equitylens_ingestion.registry import load_registry, select_sources


def write_registry(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def valid_yaml(source_id: str = "source_1") -> str:
    return f"""
schema_version: 1
sources:
  - source_id: {source_id}
    publisher: Publisher
    dataset: Dataset
    section: '15'
    year: 2024
    status: active
    publication_url: https://official.example/page
    download_url: https://official.example/file.xlsx
    expected_format: xlsx
    allowed_hosts: [official.example]
"""


def test_load_valid_registry(tmp_path: Path) -> None:
    sources = load_registry(write_registry(tmp_path / "sources.yml", valid_yaml()))
    assert sources[0].source_id == "source_1"
    assert sources[0].year == 2024


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("schema_version: 1", "schema_version: 2", "schema_version"),
        ("source_1", "BAD ID", "Invalid source_id"),
        ("status: active", "status: unknown", "Invalid status"),
        ("expected_format: xlsx", "expected_format: pdf", "expected_format"),
        ("https://official.example/page", "http://official.example/page", "HTTPS"),
        ("allowed_hosts: [official.example]", "allowed_hosts: [other.example]", "not allowed"),
    ],
)
def test_invalid_registry_is_rejected(tmp_path: Path, old: str, new: str, message: str) -> None:
    path = write_registry(tmp_path / "sources.yml", valid_yaml().replace(old, new))
    with pytest.raises(ConfigurationError, match=message):
        load_registry(path)


def test_duplicate_source_id_is_rejected(tmp_path: Path) -> None:
    item = valid_yaml().split("sources:\n", 1)[1]
    body = valid_yaml() + item
    with pytest.raises(ConfigurationError, match="Duplicate"):
        load_registry(write_registry(tmp_path / "sources.yml", body))


def test_active_source_requires_download_url(tmp_path: Path) -> None:
    body = valid_yaml().replace("    download_url: https://official.example/file.xlsx\n", "")
    with pytest.raises(ConfigurationError, match="requires download_url"):
        load_registry(write_registry(tmp_path / "sources.yml", body))


def test_manual_source_may_omit_download_url(tmp_path: Path) -> None:
    body = valid_yaml().replace("status: active", "status: manual_resolution_required")
    body = body.replace("    download_url: https://official.example/file.xlsx\n", "")
    assert load_registry(write_registry(tmp_path / "sources.yml", body))[0].download_url is None


def test_select_sources_filters_and_excludes_inactive(source) -> None:
    inactive = type(source)(
        **{
            **{field: getattr(source, field) for field in source.__dataclass_fields__},
            "source_id": "older",
            "year": 2023,
            "status": "retired",
        }
    )
    assert select_sources([source, inactive], section="15", year=2024) == [source]
    assert select_sources([inactive], include_inactive=True) == [inactive]
    assert select_sources([source], publisher="department of education") == [source]


def test_production_registry_has_expected_governance() -> None:
    sources = load_registry(Path("config/sources.yml"))
    assert len(sources) == 31
    assert sum(source.status == "active" for source in sources) == 25
    assert {source.publisher for source in sources} == {
        "Department of Education",
        "QILT",
        "Australian Bureau of Statistics",
    }
