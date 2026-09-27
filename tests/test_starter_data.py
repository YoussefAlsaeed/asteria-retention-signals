"""The starter pack is evidence: its bytes must match the supplied manifest."""

import hashlib
import json
from pathlib import Path

import pytest

STARTER = Path(__file__).resolve().parents[1] / "data" / "raw-or-fixtures" / "starter"
MANIFEST = json.loads((STARTER / "assessment_data_manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("entry", MANIFEST["files"], ids=lambda e: e["name"])
def test_starter_file_matches_manifest(entry: dict[str, object]) -> None:
    data = (STARTER / str(entry["name"])).read_bytes()
    assert len(data) == entry["bytes"]
    assert hashlib.sha256(data).hexdigest() == entry["sha256"]
