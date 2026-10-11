"""
Shared pytest fixtures.

The API is authenticated and every user gets their own dataset session, so
HTTP tests need a registered user + loaded dataset. The DB URL points at a
temp file (set before api.db is imported anywhere), keeping the real
cyberrisk.db untouched.
"""

import os
import tempfile
import uuid
from pathlib import Path

# Must be set before api/db.py is imported (it reads DATABASE_URL at import).
_TMP_DB = Path(tempfile.mkdtemp(prefix="cyberrisk_test_")) / "test.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP_DB.as_posix()}")

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture(scope="session")
def client():
    """An authenticated TestClient with the demo dataset loaded."""
    c = TestClient(app)
    username = f"tester_{uuid.uuid4().hex[:10]}"
    resp = c.post(
        "/api/auth/register",
        json={"username": username, "password": "test-pass-123"},
    )
    assert resp.status_code == 201, resp.text
    c.headers.update({"Authorization": f"Bearer {resp.json()['token']}"})

    demo = c.post("/api/datasets/demo")
    assert demo.status_code == 200, demo.text
    return c
