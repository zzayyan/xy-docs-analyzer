"""Admin user management and changing your own password. The user store is faked; conftest.py signs every
request in as ADMIN."""
import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import ConstraintError

from app import auth
from app.api import app
from tests.conftest import ADMIN

client = TestClient(app, cookies={auth.COOKIE: "admin-token"})
BUDI = {"id": "u-budi", "username": "budi", "role": "user", "password": "rahasia1"}


@pytest.fixture
def users(monkeypatch):
    """Users by id, with the sessions each one still has."""
    store = {u["id"]: {**u} for u in (BUDI, {**ADMIN, "password": "admin123"})}
    ended: list[tuple[str, str | None]] = []

    def create_user(username: str, password: str, role: str = "user") -> dict:
        if any(u["username"] == username for u in store.values()):
            raise ConstraintError("taken")
        store["u-" + username] = {"id": "u-" + username, "username": username, "role": role, "password": password}
        return auth.public_user(store["u-" + username])

    def authenticate(username: str, password: str) -> dict | None:
        user = next((u for u in store.values() if u["username"] == username), None)
        return auth.public_user(user) if user and user["password"] == password else None

    def set_password(user_id: str, password: str, keep_token: str | None = None) -> None:
        store[user_id]["password"] = password
        ended.append((user_id, keep_token))

    monkeypatch.setattr(auth, "create_user", create_user)
    monkeypatch.setattr(auth, "authenticate", authenticate)
    monkeypatch.setattr(auth, "list_users", lambda: [auth.public_user(u) for u in store.values()])
    monkeypatch.setattr(auth, "get_user", lambda user_id: store.get(user_id))
    monkeypatch.setattr(auth, "delete_user", lambda user_id: store.pop(user_id))
    monkeypatch.setattr(auth, "set_role", lambda user_id, role: store[user_id].update(role=role))
    monkeypatch.setattr(auth, "set_password", set_password)
    return store, ended


def test_admin_creates_lists_and_deletes_users(users):
    store, _ = users
    created = client.post("/users", json={"username": " Siti ", "password": "panjang123"})
    assert created.status_code == 200
    assert created.json()["username"] == "siti"
    assert created.json()["role"] == "user"
    assert {u["username"] for u in client.get("/users").json()} == {"admin", "budi", "siti"}

    assert client.delete("/users/u-siti").status_code == 204
    assert "u-siti" not in store
    assert client.delete("/users/u-siti").status_code == 404


def test_new_users_are_checked(users):
    assert client.post("/users", json={"username": "budi", "password": "panjang123"}).status_code == 409
    assert client.post("/users", json={"username": "siti", "password": "pendek"}).status_code == 400
    assert client.post("/users", json={"username": "si ti", "password": "panjang123"}).status_code == 400
    assert client.post("/users", json={"username": "siti", "password": "panjang123", "role": "root"}).status_code == 422


def test_admin_resets_a_password_and_changes_a_role(users):
    store, ended = users
    assert client.patch("/users/u-budi", json={"password": "baru12345", "role": "admin"}).status_code == 204
    assert store["u-budi"]["password"] == "baru12345"
    assert store["u-budi"]["role"] == "admin"
    assert ended == [("u-budi", None)], "every session of budi ends"


def test_an_admin_never_deletes_or_demotes_themselves(users):
    store, _ = users
    assert client.delete(f"/users/{ADMIN['id']}").status_code == 409
    assert client.patch(f"/users/{ADMIN['id']}", json={"role": "user"}).status_code == 409
    assert store[ADMIN["id"]]["role"] == "admin"


def test_only_admins_manage_users(users):
    app.dependency_overrides[auth.require_user] = lambda: auth.public_user(BUDI)
    assert client.get("/users").status_code == 403
    assert client.post("/users", json={"username": "siti", "password": "panjang123"}).status_code == 403
    assert client.delete(f"/users/{ADMIN['id']}").status_code == 403


def test_changing_your_own_password_needs_the_current_one_and_keeps_this_session(users):
    store, ended = users
    wrong = client.post("/auth/password", json={"current": "salah", "new": "baru12345"})
    assert wrong.status_code == 403
    assert client.post("/auth/password", json={"current": "admin123", "new": "baru"}).status_code == 400
    assert client.post("/auth/password", json={"current": "admin123", "new": "baru12345"}).status_code == 204
    assert store[ADMIN["id"]]["password"] == "baru12345"
    assert ended == [(ADMIN["id"], "admin-token")]
