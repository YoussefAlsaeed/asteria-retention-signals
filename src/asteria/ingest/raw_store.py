"""Raw evidence store: one byte-exact payload plus a metadata sidecar per indicator.

Layout: <root>/<provider>/<indicator_id>.json and <indicator_id>.meta.json.
The payload is never parsed and rewritten, so it can be replayed and checksummed exactly.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from asteria.sources.base import SourceError


class RawStoreError(SourceError):
    """A stored snapshot is missing or does not match its recorded checksum."""


@dataclass(frozen=True)
class SnapshotMeta:
    provider: str
    indicator_id: str
    dataset: str
    request_url: str
    request_params: list[tuple[str, str]]
    fetched_at: str
    http_status: int
    sha256: str
    bytes: int
    source_updated: str | None
    observation_count: int


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class RawStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _paths(self, provider: str, indicator_id: str) -> tuple[Path, Path]:
        folder = self.root / provider
        return folder / f"{indicator_id}.json", folder / f"{indicator_id}.meta.json"

    def current_sha256(self, provider: str, indicator_id: str) -> str | None:
        _, meta_path = self._paths(provider, indicator_id)
        if not meta_path.exists():
            return None
        return str(json.loads(meta_path.read_text(encoding="utf-8"))["sha256"])

    def write(
        self, content: bytes, meta: SnapshotMeta
    ) -> Literal["created", "updated", "unchanged"]:
        """Store a validated payload. Identical content is left untouched (idempotent)."""
        previous = self.current_sha256(meta.provider, meta.indicator_id)
        if previous == meta.sha256:
            return "unchanged"
        payload_path, meta_path = self._paths(meta.provider, meta.indicator_id)
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(payload_path, content)
        _atomic_write(meta_path, (json.dumps(asdict(meta), indent=2) + "\n").encode("utf-8"))
        return "created" if previous is None else "updated"

    def read(self, provider: str, indicator_id: str) -> tuple[bytes, SnapshotMeta]:
        payload_path, meta_path = self._paths(provider, indicator_id)
        if not payload_path.exists() or not meta_path.exists():
            raise RawStoreError(
                f"no replay snapshot for {provider}/{indicator_id} under {self.root}; "
                "run `asteria ingest --mode live` first"
            )
        raw_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        raw_meta["request_params"] = [tuple(p) for p in raw_meta["request_params"]]
        meta = SnapshotMeta(**raw_meta)
        content = payload_path.read_bytes()
        actual = sha256_hex(content)
        if actual != meta.sha256:
            raise RawStoreError(
                f"checksum mismatch for {payload_path.name}: "
                f"recorded {meta.sha256[:12]}, found {actual[:12]}"
            )
        return content, meta


def _atomic_write(path: Path, content: bytes) -> None:
    """Write to a temp file then rename, so a crash never leaves a half-written file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(content)
    os.replace(tmp, path)
