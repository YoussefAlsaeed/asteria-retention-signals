from pathlib import Path

import pytest

from asteria.ingest.raw_store import RawStore, RawStoreError, SnapshotMeta, sha256_hex


def meta_for(content: bytes) -> SnapshotMeta:
    return SnapshotMeta(
        provider="eurostat",
        indicator_id="demo",
        dataset="ds",
        request_url="u",
        request_params=[("geo", "EL")],
        fetched_at="2026-09-28T00:00:00+00:00",
        http_status=200,
        sha256=sha256_hex(content),
        bytes=len(content),
        source_updated=None,
        observation_count=1,
    )


def test_round_trip_preserves_bytes_exactly(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    content = b'{"a":1}\r\n'  # CRLF must survive untouched
    assert store.write(content, meta_for(content)) == "created"
    read_back, meta = store.read("eurostat", "demo")
    assert read_back == content
    assert meta.request_params == [("geo", "EL")]


def test_identical_content_is_not_rewritten(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    store.write(b"v1", meta_for(b"v1"))
    assert store.write(b"v1", meta_for(b"v1")) == "unchanged"
    assert store.write(b"v2", meta_for(b"v2")) == "updated"
    assert store.read("eurostat", "demo")[0] == b"v2"


def test_tampered_payload_is_detected(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    store.write(b"original", meta_for(b"original"))
    (tmp_path / "eurostat" / "demo.json").write_bytes(b"edited")
    with pytest.raises(RawStoreError, match="checksum mismatch"):
        store.read("eurostat", "demo")


def test_missing_snapshot_explains_how_to_create_it(tmp_path: Path) -> None:
    with pytest.raises(RawStoreError, match="--mode live"):
        RawStore(tmp_path).read("eurostat", "demo")
