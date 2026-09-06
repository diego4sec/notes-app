"""The one check. Needs a real Postgres, because the schema uses text[] and
Postgres full-text search:

    docker compose up -d db
    cd api && uv run --extra dev pytest

Owners are random UUIDs per run, so the tests do not need cleanup and cannot
collide with each other or with dev data.
"""
import os
import subprocess
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://notes:notes@localhost:5432/notes"
)

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import REQUIRED_ROLE, User, check_role, current_user  # noqa: E402
from app.main import app  # noqa: E402

API_DIR = Path(__file__).resolve().parent.parent

ALICE = User(id=uuid.uuid4(), email="alice@example.com", name="Alice", roles=["notes-user"])
BOB = User(id=uuid.uuid4(), email="bob@example.com", name="Bob", roles=["notes-user"])


@pytest.fixture(scope="module", autouse=True)
def _migrated() -> None:
    subprocess.run(["alembic", "upgrade", "head"], cwd=API_DIR, check=True)


def as_user(user: User) -> TestClient:
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app)


def test_create_read_update_delete() -> None:
    c = as_user(ALICE)

    created = c.post("/api/notes", json={"title": "Groceries", "body": "milk", "tags": ["home"]})
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]

    assert c.get(f"/api/notes/{note_id}").json()["title"] == "Groceries"

    patched = c.patch(f"/api/notes/{note_id}", json={"body": "milk, eggs"})
    assert patched.status_code == 200
    assert patched.json()["body"] == "milk, eggs"
    assert patched.json()["tags"] == ["home"], "patch must not clear untouched fields"

    assert c.delete(f"/api/notes/{note_id}").status_code == 204
    # Soft delete must be invisible, not merely flagged.
    assert c.get(f"/api/notes/{note_id}").status_code == 404
    assert note_id not in [n["id"] for n in c.get("/api/notes").json()]


def test_owner_isolation() -> None:
    alice_note = as_user(ALICE).post("/api/notes", json={"title": "Alice private"}).json()

    bob = as_user(BOB)
    # 404, not 403: a 403 would confirm the note exists.
    assert bob.get(f"/api/notes/{alice_note['id']}").status_code == 404
    assert bob.patch(f"/api/notes/{alice_note['id']}", json={"title": "hijack"}).status_code == 404
    assert bob.delete(f"/api/notes/{alice_note['id']}").status_code == 404
    assert alice_note["id"] not in [n["id"] for n in bob.get("/api/notes").json()]


def test_search_and_tag_filter_stay_owner_scoped() -> None:
    marker = uuid.uuid4().hex[:12]
    as_user(ALICE).post("/api/notes", json={"title": f"kayak {marker}", "tags": ["sport"]})
    as_user(BOB).post("/api/notes", json={"title": f"kayak {marker}", "tags": ["sport"]})

    alice_hits = as_user(ALICE).get("/api/notes", params={"q": marker}).json()
    assert len(alice_hits) == 1, "search must not leak across owners"

    bob_tagged = as_user(BOB).get("/api/notes", params={"tag": "sport"}).json()
    assert len(bob_tagged) == 1
    assert "sport" in as_user(BOB).get("/api/tags").json()


def test_role_gate() -> None:
    check_role([REQUIRED_ROLE])  # entitled, must not raise
    for roles in ([], ["notes-admin"], ["some-other-app-user"]):
        with pytest.raises(HTTPException) as err:
            check_role(roles)
        assert err.value.status_code == 403


def test_rejects_invalid_payload() -> None:
    assert as_user(ALICE).post("/api/notes", json={"title": ""}).status_code == 422
    assert as_user(ALICE).post("/api/notes", json={}).status_code == 422
