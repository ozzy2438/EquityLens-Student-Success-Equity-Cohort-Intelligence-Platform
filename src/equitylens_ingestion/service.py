"""Orchestration for immutable raw promotion and provenance recording."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from equitylens_ingestion.downloader import Downloader
from equitylens_ingestion.inventory import inspect_workbook
from equitylens_ingestion.manifest import ManifestStore, utc_now
from equitylens_ingestion.models import IngestionResult, JsonObject, Source

LOGGER = logging.getLogger(__name__)


class IngestionService:
    """Ingest source artifacts while preserving byte-level immutability."""

    def __init__(
        self,
        *,
        data_root: Path,
        downloader: Downloader | None = None,
        store: ManifestStore | None = None,
    ) -> None:
        self.data_root = data_root
        self.raw_root = data_root / "raw"
        self.staging_root = self.raw_root / ".staging"
        self.downloader = downloader or Downloader()
        self.store = store or ManifestStore(data_root / "manifests", data_root / "inventory")

    def ingest_all(self, sources: list[Source]) -> list[IngestionResult]:
        """Ingest each selected source independently and preserve all outcomes."""

        results: list[IngestionResult] = []
        for source in sources:
            try:
                results.append(self.ingest_one(source))
            except Exception as exc:  # Continue batch while returning an actionable failure.
                LOGGER.exception(
                    "source_ingestion_failed",
                    extra={"source_id": source.source_id, "error_type": type(exc).__name__},
                )
                results.append(
                    IngestionResult(
                        source_id=source.source_id,
                        outcome="failed",
                        message=str(exc),
                    )
                )
        return results

    def ingest_one(self, source: Source) -> IngestionResult:
        """Download, validate, inventory, and atomically promote one source."""

        if source.status != "active":
            return IngestionResult(
                source_id=source.source_id,
                outcome="skipped",
                message=f"source status is {source.status}",
            )
        LOGGER.info("source_ingestion_started", extra={"source_id": source.source_id})
        downloaded = self.downloader.download(source, self.staging_root)
        try:
            with self.store.locked():
                existing = [
                    record
                    for record in self.store.records()
                    if record.get("source_id") == source.source_id
                ]
                duplicate = next(
                    (record for record in existing if record.get("sha256") == downloaded.sha256),
                    None,
                )
                if duplicate:
                    inventory_exists = any(
                        record.get("record_id") == duplicate.get("record_id")
                        for record in self.store.inventory_records()
                    )
                    if not inventory_exists:
                        sheets = inspect_workbook(downloaded.path, source.expected_format)
                        self.store.append_inventory_record(
                            {
                                "schema_version": 1,
                                "record_id": duplicate["record_id"],
                                "source_id": source.source_id,
                                "sha256": downloaded.sha256,
                                "inspected_at": utc_now(),
                                "format": source.expected_format,
                                "sheet_count": len(sheets),
                                "sheets": sheets,
                                "recovered": True,
                            }
                        )
                    LOGGER.info(
                        "source_unchanged",
                        extra={"source_id": source.source_id, "sha256": downloaded.sha256},
                    )
                    return IngestionResult(
                        source_id=source.source_id,
                        outcome="unchanged",
                        raw_path=str(duplicate["raw_path"]),
                        sha256=downloaded.sha256,
                    )

                destination = self._destination(source, downloaded.sha256)
                sheets = inspect_workbook(downloaded.path, source.expected_format)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    downloaded.path.unlink(missing_ok=True)
                else:
                    os.replace(downloaded.path, destination)
                    destination.chmod(0o444)

                previous = existing[-1] if existing else None
                ingested_at = utc_now()
                record_id = str(uuid4())
                file_record: JsonObject = {
                    "schema_version": 1,
                    "record_id": record_id,
                    "source_id": source.source_id,
                    "publisher": source.publisher,
                    "dataset": source.dataset,
                    "section": source.section,
                    "year": source.year,
                    "publication_url": source.publication_url,
                    "published_at": source.published_at,
                    "modified_at": source.modified_at,
                    "file_reference": source.file_reference,
                    "ingested_at": ingested_at,
                    "raw_path": destination.relative_to(self.data_root.parent).as_posix(),
                    "sha256": downloaded.sha256,
                    "size_bytes": downloaded.size_bytes,
                    "format": source.expected_format,
                    "http": asdict(downloaded.metadata),
                    "supersedes_record_id": previous.get("record_id") if previous else None,
                    "supersedes_sha256": previous.get("sha256") if previous else None,
                }
                inventory_record: JsonObject = {
                    "schema_version": 1,
                    "record_id": record_id,
                    "source_id": source.source_id,
                    "sha256": downloaded.sha256,
                    "inspected_at": ingested_at,
                    "format": source.expected_format,
                    "sheet_count": len(sheets),
                    "sheets": sheets,
                }
                self.store.append_file_record(file_record)
                self.store.append_inventory_record(inventory_record)

            LOGGER.info(
                "source_ingested",
                extra={
                    "source_id": source.source_id,
                    "sha256": downloaded.sha256,
                    "raw_path": str(destination),
                },
            )
            return IngestionResult(
                source_id=source.source_id,
                outcome="ingested",
                raw_path=file_record["raw_path"],
                sha256=downloaded.sha256,
            )
        finally:
            downloaded.path.unlink(missing_ok=True)

    def _destination(self, source: Source, checksum: str) -> Path:
        publisher = _slug(source.publisher)
        dataset = _slug(source.dataset)
        filename = f"{checksum}__{source.source_id}.{source.expected_format}"
        return self.raw_root / publisher / dataset / str(source.year) / source.source_id / filename


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
