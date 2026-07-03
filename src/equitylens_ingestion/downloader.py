"""Streaming HTTP download with temporary files and provenance capture."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from equitylens_ingestion.errors import DownloadError
from equitylens_ingestion.models import DownloadedFile, DownloadMetadata, Source
from equitylens_ingestion.validation import validate_download

DEFAULT_MAX_BYTES = 150 * 1024 * 1024
CHUNK_SIZE = 64 * 1024


class Downloader:
    """Download one source to a `.part` file without exposing partial raw data."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        max_bytes: int = DEFAULT_MAX_BYTES,
        client: httpx.Client | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self._client = client

    def download(self, source: Source, staging_dir: Path) -> DownloadedFile:
        """Stream, hash, validate, and return an artifact in staging."""

        if not source.download_url:
            raise DownloadError(f"Source {source.source_id} has no download URL")
        staging_dir.mkdir(parents=True, exist_ok=True)
        part_path = staging_dir / f"{source.source_id}-{uuid4().hex}.part"
        client = self._client or httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={"User-Agent": "EquityLens-Ingestion/0.1 (+governed-public-data)"},
        )
        owns_client = self._client is None
        try:
            return self._stream(client, source, part_path)
        except httpx.HTTPError as exc:
            part_path.unlink(missing_ok=True)
            raise DownloadError(f"HTTP download failed for {source.source_id}: {exc}") from exc
        except Exception:
            part_path.unlink(missing_ok=True)
            raise
        finally:
            if owns_client:
                client.close()

    def _stream(self, client: httpx.Client, source: Source, part_path: Path) -> DownloadedFile:
        assert source.download_url is not None
        digest = hashlib.sha256()
        size = 0
        with client.stream("GET", source.download_url) as response:
            response.raise_for_status()
            final_host = (urlparse(str(response.url)).hostname or "").lower()
            if final_host not in source.allowed_hosts:
                raise DownloadError(
                    f"Redirected to non-authoritative host {final_host!r} for {source.source_id}"
                )
            declared_length = _parse_content_length(response.headers.get("content-length"))
            if declared_length is not None and declared_length > self.max_bytes:
                raise DownloadError(
                    f"Declared content length {declared_length} exceeds limit {self.max_bytes}"
                )
            with part_path.open("xb") as handle:
                for chunk in response.iter_bytes(CHUNK_SIZE):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise DownloadError(
                            f"Download exceeded configured limit of {self.max_bytes} bytes"
                        )
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())

            content_type = response.headers.get("content-type")
            validate_download(part_path, source.expected_format, content_type)
            metadata = DownloadMetadata(
                requested_url=source.download_url,
                final_url=str(response.url),
                content_type=content_type,
                content_length=size,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
            )
        return DownloadedFile(
            path=part_path,
            sha256=digest.hexdigest(),
            size_bytes=size,
            metadata=metadata,
        )


def _parse_content_length(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
