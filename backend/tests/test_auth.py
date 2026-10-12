"""Sign-in and the session cookie. The HTTP tests fake the user store; the last test runs the real Cypher
and needs Neo4j (docker compose up -d), like test_smoke.py."""
import uuid

import pytest
from fastapi.testclient import TestClient

import app.store as store_module
from app import auth
from app.api import app
from app.db import graph

USER = {"id": "u1", "username": "budi", "role": "user"}


@pytest.fixture(autouse=True)
def signed_out(monkeypatch):
    """Drops conftest's signed-in override and keeps sessions in a dict."""
    app.dependency_overrides.pop(auth.require_user, None)
    sessions: dict[str, dict] = {}

    def start_session(user_id: str) -> str:
        token = f"t{len(sessions)}"
        sessions[token] = USER
        return token

    monkeypatch.setattr(auth, "authenticate", lambda u, p: USER if (u, p) == ("budi", "rahasia") else None)
    monkeypatch.setattr(auth, "start_session", start_session)
    monkeypatch.setattr(auth, "session_user", lambda token: sessions.get(token))
    monkeypatch.setattr(auth, "end_session", lambda token: sessions.pop(token, None))
    monkeypatch.setattr(store_module, "list_files", lambda: [])
    return sessions


def test_every_route_but_login_needs_a_session():
    client = TestClient(app)
    assert client.get("/documents").status_code == 401
    assert client.get("/documents/d1/original").status_code == 401
    assert client.get("/chat/stream", params={"doc_id": "d1", "question": "q"}).status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_wrong_password_is_refused_and_sets_no_cookie():
    client = TestClient(app)
    response = client.post("/auth/login", json={"username": "budi", "password": "salah"})
    assert response.status_code == 401
    assert auth.COOKIE not in response.cookies


def test_login_sets_an_httponly_cookie_that_opens_every_route_until_logout(signed_out):
    client = TestClient(app)
    response = client.post("/auth/login", json={"username": "budi", "password": "rahasia"})
    assert response.status_code == 200
    assert response.json() == USER
    assert "httponly" in response.headers["set-cookie"].lower()

    assert client.get("/auth/me").json() == USER
    assert client.get("/documents").status_code == 200

    assert client.post("/auth/logout").status_code == 204
    assert signed_out == {}, "the session is gone server-side, not just the cookie"
    assert client.get("/documents").status_code == 401


def test_a_cookie_the_server_does_not_know_is_refused():
    client = TestClient(app, cookies={auth.COOKIE: "forged"})
    assert client.get("/documents").status_code == 401


def test_password_hash_verifies_only_its_own_password():
    stored = auth.hash_password("rahasia")
    assert auth.verify_password("rahasia", stored)
    assert not auth.verify_password("Rahasia", stored)
    assert "rahasia" not in stored
    assert auth.hash_password("rahasia") != stored, "salted"


def test_users_and_sessions_in_neo4j(monkeypatch):
    monkeypatch.undo()  # the real authenticate/start_session/session_user/end_session
    name = f"test-{uuid.uuid4().hex[:8]}"
    try:
        user = auth.create_user(f"  {name.upper()} ", "rahasia")
        assert user["username"] == name, "usernames are trimmed and lowercased"
        assert auth.authenticate(name, "salah") is None
        assert auth.authenticate("nobody-" + name, "rahasia") is None
        assert auth.authenticate(name.upper(), "rahasia") == user

        token = auth.start_session(user["id"])
        assert auth.session_user(token) == user
        stored = graph().query("MATCH (s:Session {user_id: $id}) RETURN s.id AS id", {"id": user["id"]})
        assert stored and stored[0]["id"] != token, "only the token's hash is stored"
        auth.end_session(token)
        assert auth.session_user(token) is None
    finally:
        graph().query("MATCH (u:User {username: $name}) OPTIONAL MATCH (u)-[:HAS_SESSION]->(s) DETACH DELETE u, s",
                      {"name": name})


def test_first_admin_comes_from_env_only_while_no_user_exists(monkeypatch):
    created: list[tuple] = []
    monkeypatch.setattr(auth, "create_user", lambda *args, **kwargs: created.append((*args, kwargs)))
    monkeypatch.setattr(auth.settings, "admin_username", "admin")
    monkeypatch.setattr(auth.settings, "admin_password", "rahasia")
    for users, expected in ((1, []), (0, [("admin", "rahasia", {"role": "admin"})])):
        monkeypatch.setattr(auth, "graph", lambda n=users: type("G", (), {"query": lambda self, q: [{"n": n}]})())
        created.clear()
        auth.ensure_admin()
        assert created == expected
