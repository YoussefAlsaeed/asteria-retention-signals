from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asteria.api.app import create_app
from asteria.config import Settings
from asteria.context import load_context


@pytest.fixture(scope="session")
def client(built_data_dir: Path) -> TestClient:
    return TestClient(create_app(load_context(Settings(data_dir=built_data_dir))))


@pytest.fixture
def empty_client(tmp_path: Path) -> TestClient:
    """An API whose analytical product has not been built."""
    return TestClient(create_app(load_context(Settings(data_dir=tmp_path))))
