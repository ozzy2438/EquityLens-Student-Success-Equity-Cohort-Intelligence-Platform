"""Load and validate the centrally governed YAML source registry."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

from equitylens_ingestion.errors import ConfigurationError
from equitylens_ingestion.models import Source

_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_STATUSES = {"active", "manual_resolution_required", "retired"}
_FORMATS = {"xlsx", "xls", "csv"}


def _required(item: dict[str, object], key: str) -> object:
    value = item.get(key)
    if value is None or value == "":
        raise ConfigurationError(f"Source entry is missing required field: {key}")
    return value


def _validate_https(url: str, *, field_name: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ConfigurationError(f"{field_name} must be an absolute HTTPS URL: {url!r}")
    return url


def load_registry(path: Path) -> list[Source]:
    """Return validated sources, rejecting duplicate IDs and unsafe URLs."""

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"Cannot read source registry {path}: {exc}") from exc

    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ConfigurationError("sources.yml must declare schema_version: 1")
    raw_sources = document.get("sources")
    if not isinstance(raw_sources, list):
        raise ConfigurationError("sources.yml must contain a sources list")

    result: list[Source] = []
    seen: set[str] = set()
    for item in raw_sources:
        if not isinstance(item, dict):
            raise ConfigurationError("Every source entry must be a mapping")
        source_id = str(_required(item, "source_id"))
        if not _SOURCE_ID.fullmatch(source_id):
            raise ConfigurationError(f"Invalid source_id: {source_id!r}")
        if source_id in seen:
            raise ConfigurationError(f"Duplicate source_id: {source_id}")
        seen.add(source_id)

        status = str(_required(item, "status"))
        expected_format = str(_required(item, "expected_format")).lower()
        if status not in _STATUSES:
            raise ConfigurationError(f"Invalid status for {source_id}: {status}")
        if expected_format not in _FORMATS:
            raise ConfigurationError(f"Invalid expected_format for {source_id}: {expected_format}")

        publication_url = _validate_https(
            str(_required(item, "publication_url")), field_name="publication_url"
        )
        raw_download_url = item.get("download_url")
        download_url = (
            _validate_https(str(raw_download_url), field_name="download_url")
            if raw_download_url
            else None
        )
        if status == "active" and not download_url:
            raise ConfigurationError(f"Active source {source_id} requires download_url")

        allowed_hosts = tuple(str(host).lower() for host in item.get("allowed_hosts", []))
        if not allowed_hosts:
            raise ConfigurationError(f"Source {source_id} requires allowed_hosts")
        configured_hosts = {
            urlparse(url).hostname for url in (publication_url, download_url) if url is not None
        }
        if not configured_hosts.issubset(set(allowed_hosts)):
            raise ConfigurationError(f"Configured URL host is not allowed for source {source_id}")

        try:
            year = int(_required(item, "year"))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid year for {source_id}") from exc

        result.append(
            Source(
                source_id=source_id,
                publisher=str(_required(item, "publisher")),
                dataset=str(_required(item, "dataset")),
                section=str(_required(item, "section")),
                year=year,
                status=status,
                publication_url=publication_url,
                download_url=download_url,
                expected_format=expected_format,
                published_at=_optional_string(item.get("published_at")),
                modified_at=_optional_string(item.get("modified_at")),
                file_reference=_optional_string(item.get("file_reference")),
                allowed_hosts=allowed_hosts,
                notes=_optional_string(item.get("notes")),
            )
        )
    return result


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)


def select_sources(
    sources: list[Source],
    *,
    publisher: str | None = None,
    section: str | None = None,
    year: int | None = None,
    include_inactive: bool = False,
) -> list[Source]:
    """Apply deterministic CLI filters to the registry."""

    return [
        source
        for source in sources
        if (include_inactive or source.status == "active")
        and (publisher is None or source.publisher.casefold() == publisher.casefold())
        and (section is None or source.section.casefold() == section.casefold())
        and (year is None or source.year == year)
    ]
