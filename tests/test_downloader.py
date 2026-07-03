from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from equitylens_ingestion.downloader import Downloader
from equitylens_ingestion.errors import DownloadError, ValidationError


class Chunks(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_download_streams_valid_file_and_hashes(tmp_path: Path, source, xlsx_bytes: bytes) -> None:
    client = client_for(
        lambda request: httpx.Response(
            200,
            content=xlsx_bytes,
            headers={"content-type": "application/octet-stream", "etag": '"abc"'},
            request=request,
        )
    )
    result = Downloader(client=client).download(source, tmp_path)
    assert result.path.suffix == ".part"
    assert result.sha256 == hashlib.sha256(xlsx_bytes).hexdigest()
    assert result.size_bytes == len(xlsx_bytes)
    assert result.metadata.etag == '"abc"'
    client.close()


def test_http_failure_removes_part_file(tmp_path: Path, source) -> None:
    client = client_for(lambda request: httpx.Response(503, request=request))
    with pytest.raises(DownloadError, match="HTTP download failed"):
        Downloader(client=client).download(source, tmp_path)
    assert list(tmp_path.glob("*.part")) == []
    client.close()


def test_validation_failure_removes_part_file(tmp_path: Path, source) -> None:
    client = client_for(
        lambda request: httpx.Response(200, content=b"<html>no</html>", request=request)
    )
    with pytest.raises(ValidationError, match="HTML"):
        Downloader(client=client).download(source, tmp_path)
    assert list(tmp_path.glob("*.part")) == []
    client.close()


def test_declared_size_limit_is_enforced(tmp_path: Path, source) -> None:
    client = client_for(
        lambda request: httpx.Response(
            200, content=b"12345", headers={"content-length": "100"}, request=request
        )
    )
    with pytest.raises(DownloadError, match="Declared content length"):
        Downloader(client=client, max_bytes=10).download(source, tmp_path)
    client.close()


def test_streamed_size_limit_is_enforced(tmp_path: Path, source) -> None:
    client = client_for(
        lambda request: httpx.Response(
            200, stream=Chunks([b"12345", b"67890", b"x"]), request=request
        )
    )
    with pytest.raises(DownloadError, match="exceeded"):
        Downloader(client=client, max_bytes=10).download(source, tmp_path)
    assert list(tmp_path.glob("*.part")) == []
    client.close()


def test_redirect_to_non_allowlisted_host_is_rejected(
    tmp_path: Path, source, xlsx_bytes: bytes
) -> None:
    def handler(request):
        if request.url.host == "official.example":
            return httpx.Response(
                302, headers={"location": "https://mirror.example/file.xlsx"}, request=request
            )
        return httpx.Response(200, content=xlsx_bytes, request=request)

    client = client_for(handler)
    with pytest.raises(DownloadError, match="non-authoritative"):
        Downloader(client=client).download(source, tmp_path)
    client.close()


def test_invalid_content_length_is_ignored(tmp_path: Path, source, xlsx_bytes: bytes) -> None:
    client = client_for(
        lambda request: httpx.Response(
            200,
            stream=Chunks([xlsx_bytes]),
            headers={"content-length": "unknown"},
            request=request,
        )
    )
    assert Downloader(client=client).download(source, tmp_path).size_bytes == len(xlsx_bytes)
    client.close()
