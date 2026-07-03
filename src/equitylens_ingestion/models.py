"""Typed domain models used across the ingestion gateway."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Source:
    """One authoritative public-data artifact in the source registry."""

    source_id: str
    publisher: str
    dataset: str
    section: str
    year: int
    status: str
    publication_url: str
    download_url: str | None
    expected_format: str
    published_at: str | None = None
    modified_at: str | None = None
    file_reference: str | None = None
    allowed_hosts: tuple[str, ...] = field(default_factory=tuple)
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadMetadata:
    """HTTP metadata captured without interpreting publisher content."""

    requested_url: str
    final_url: str
    content_type: str | None
    content_length: int
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True, slots=True)
class DownloadedFile:
    """Validated temporary artifact awaiting immutable promotion."""

    path: Path
    sha256: str
    size_bytes: int
    metadata: DownloadMetadata


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Outcome for one source, suitable for CLI and automation."""

    source_id: str
    outcome: str
    raw_path: str | None = None
    sha256: str | None = None
    message: str | None = None


JsonObject = dict[str, Any]
