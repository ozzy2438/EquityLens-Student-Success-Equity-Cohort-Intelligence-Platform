from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

from equitylens_ingestion.manifest import ManifestStore
from equitylens_ingestion.models import DownloadedFile, DownloadMetadata
from equitylens_ingestion.service import IngestionService


class FakeDownloader:
    def __init__(self, payloads: list[bytes]) -> None:
        self.payloads = iter(payloads)
        self.calls = 0

    def download(self, source, staging_dir: Path) -> DownloadedFile:
        self.calls += 1
        payload = next(self.payloads)
        staging_dir.mkdir(parents=True, exist_ok=True)
        path = staging_dir / f"fake-{self.calls}.part"
        path.write_bytes(payload)
        return DownloadedFile(
            path=path,
            sha256=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
            metadata=DownloadMetadata(
                requested_url=source.download_url,
                final_url=source.download_url,
                content_type="application/octet-stream",
                content_length=len(payload),
                etag=None,
                last_modified=None,
            ),
        )


def make_service(tmp_path: Path, payloads: list[bytes]) -> IngestionService:
    return IngestionService(data_root=tmp_path / "data", downloader=FakeDownloader(payloads))


def test_first_ingestion_promotes_immutable_file_and_manifests(
    tmp_path: Path, source, xlsx_bytes: bytes
) -> None:
    service = make_service(tmp_path, [xlsx_bytes])
    result = service.ingest_one(source)
    assert result.outcome == "ingested"
    raw_path = tmp_path / result.raw_path
    assert raw_path.read_bytes() == xlsx_bytes
    assert stat.S_IMODE(raw_path.stat().st_mode) == 0o444
    records = service.store.records()
    assert records[0]["sha256"] == hashlib.sha256(xlsx_bytes).hexdigest()
    assert records[0]["supersedes_record_id"] is None
    assert service.store.inventory_records()[0]["sheet_count"] == 2


def test_identical_rerun_is_idempotent(tmp_path: Path, source, xlsx_bytes: bytes) -> None:
    service = make_service(tmp_path, [xlsx_bytes, xlsx_bytes])
    first = service.ingest_one(source)
    second = service.ingest_one(source)
    assert first.outcome == "ingested"
    assert second.outcome == "unchanged"
    assert len(service.store.records()) == 1
    assert len(service.store.inventory_records()) == 1
    assert len(list((tmp_path / "data/raw").rglob("*.xlsx"))) == 1
    assert list((tmp_path / "data/raw/.staging").glob("*.part")) == []


def test_changed_bytes_create_linked_version(tmp_path: Path, source, xlsx_bytes: bytes) -> None:
    changed = xlsx_bytes + b"publisher-correction"
    service = make_service(tmp_path, [xlsx_bytes, changed])
    first = service.ingest_one(source)
    second = service.ingest_one(source)
    records = service.store.records()
    assert second.outcome == "ingested"
    assert first.raw_path != second.raw_path
    assert records[1]["supersedes_record_id"] == records[0]["record_id"]
    assert records[1]["supersedes_sha256"] == records[0]["sha256"]
    assert len(list((tmp_path / "data/raw").rglob("*.xlsx"))) == 2


def test_missing_inventory_is_recovered_on_duplicate(
    tmp_path: Path, source, xlsx_bytes: bytes
) -> None:
    service = make_service(tmp_path, [xlsx_bytes, xlsx_bytes])
    service.ingest_one(source)
    service.store.workbook_inventory.unlink()
    result = service.ingest_one(source)
    inventory = service.store.inventory_records()
    assert result.outcome == "unchanged"
    assert len(inventory) == 1
    assert inventory[0]["recovered"] is True


def test_inactive_source_is_skipped_without_download(source, tmp_path: Path) -> None:
    inactive = type(source)(
        **{
            **{field: getattr(source, field) for field in source.__dataclass_fields__},
            "status": "manual_resolution_required",
            "download_url": None,
        }
    )
    downloader = FakeDownloader([])
    result = IngestionService(data_root=tmp_path / "data", downloader=downloader).ingest_one(
        inactive
    )
    assert result.outcome == "skipped"
    assert downloader.calls == 0


def test_batch_isolates_failure(source, tmp_path: Path) -> None:
    class FailingDownloader:
        def download(self, _source, _staging_dir):
            raise RuntimeError("network down")

    service = IngestionService(data_root=tmp_path / "data", downloader=FailingDownloader())
    results = service.ingest_all([source])
    assert results[0].outcome == "failed"
    assert results[0].message == "network down"


def test_source_snapshot_is_replaceable_and_fingerprinted(tmp_path: Path, source) -> None:
    store = ManifestStore(tmp_path / "manifests", tmp_path / "inventory")
    store.write_source_snapshot([source])
    first = json.loads(store.source_manifest.read_text())
    store.write_source_snapshot([source])
    second = json.loads(store.source_manifest.read_text())
    assert first["registry_sha256"] == second["registry_sha256"]
    assert len(second["sources"]) == 1
    assert not store.source_manifest.with_suffix(".json.tmp").exists()
