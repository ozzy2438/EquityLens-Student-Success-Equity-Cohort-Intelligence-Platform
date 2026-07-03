"""Append-only file provenance and replaceable source-registry snapshots."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from equitylens_ingestion.errors import IngestionError
from equitylens_ingestion.models import JsonObject, Source


def utc_now() -> str:
    """Return an RFC 3339 UTC timestamp."""

    return datetime.now(UTC).isoformat()


class ManifestStore:
    """Manage provenance records under an inter-process file lock."""

    def __init__(self, manifest_dir: Path, inventory_dir: Path) -> None:
        self.manifest_dir = manifest_dir
        self.inventory_dir = inventory_dir
        self.file_manifest = manifest_dir / "file_manifest.jsonl"
        self.source_manifest = manifest_dir / "source_manifest.json"
        self.workbook_inventory = inventory_dir / "workbook_inventory.jsonl"
        self.lock_path = manifest_dir / ".manifest.lock"

    def write_source_snapshot(self, sources: list[Source]) -> None:
        """Atomically replace the registry snapshot; it is state, not an event log."""

        with self.locked():
            source_records = [asdict(source) for source in sources]
            canonical = json.dumps(source_records, sort_keys=True, separators=(",", ":"))
            payload = {
                "schema_version": 1,
                "generated_at": utc_now(),
                "registry_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
                "sources": source_records,
            }
            temporary = self.source_manifest.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            os.replace(temporary, self.source_manifest)

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Serialize manifest reads, promotion decisions, and appends."""

        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def records(self) -> list[JsonObject]:
        """Read and validate the append-only file manifest."""

        return _read_jsonl(self.file_manifest)

    def inventory_records(self) -> list[JsonObject]:
        """Read and validate workbook inventory events."""

        return _read_jsonl(self.workbook_inventory)

    def append_file_record(self, record: JsonObject) -> None:
        _append_jsonl(self.file_manifest, record)

    def append_inventory_record(self, record: JsonObject) -> None:
        self.inventory_dir.mkdir(parents=True, exist_ok=True)
        _append_jsonl(self.workbook_inventory, record)


def _read_jsonl(path: Path) -> list[JsonObject]:
    if not path.exists():
        return []
    result: list[JsonObject] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IngestionError(f"Invalid JSONL in {path} at line {line_number}") from exc
        if not isinstance(value, dict):
            raise IngestionError(f"Non-object JSONL record in {path} at line {line_number}")
        result.append(value)
    return result


def _append_jsonl(path: Path, record: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(record, default=str, sort_keys=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
