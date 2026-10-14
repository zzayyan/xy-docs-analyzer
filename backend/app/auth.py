"""Accounts and sessions. A session is a random token in an HttpOnly cookie (so img/iframe/EventSource send
it too), stored hashed on a Session node so logout or a deleted user ends it at once."""
import hashlib
import hmac
import secrets
import time
import uuid

from fastapi import Depends, HTTPException, Request

from app.config import settings
from app.db import graph

COOKIE = "session"
SESSION_DAYS = 7
PUBLIC_PATHS = {"/auth/login"}

USER_BY_NAME = "MATCH (u:User {username: $username}) RETURN u {.*} AS user"
CREATE_USER = """
CREATE (u:User {id: $id, username: $username, password_hash: $password_hash, role: $role, created_at: timestamp()})
RETURN u {.*} AS user
"""
COUNT_USERS = "MATCH (u:User) RETURN count(u) AS n"
CREATE_SESSION = """
MATCH (u:User {id: $user_id})
CREATE (u)-[:HAS_SESSION]->(:Session {id: $id, user_id: $user_id, expires_at: $expires_at})
"""
SESSION_USER = """
MATCH (u:User)-[:HAS_SESSION]->(s:Session {id: $id})
WHERE s.expires_at > timestamp()
RETURN u {.id, .username, .role} AS user
"""
DELETE_SESSION = "MATCH (s:Session {id: $id}) DETACH DELETE s"
LIST_USERS = "MATCH (u:User) RETURN u {.id, .username, .role, .created_at} AS user ORDER BY u.username"
GET_USER = "MATCH (u:User {id: $id}) RETURN u {.*} AS user"
DELETE_USER = "MATCH (u:User {id: $id}) OPTIONAL MATCH (u)-[:HAS_SESSION]->(s:Session) DETACH DELETE u, s"
SET_USER = "MATCH (u:User {id: $id}) SET u += $props"
END_SESSIONS = "MATCH (:User {id: $id})-[:HAS_SESSION]->(s:Session) WHERE s.id <> coalesce($keep, '') DETACH DELETE s"
DELETE_EXPIRED_SESSIONS = "MATCH (s:Session) WHERE s.expires_at <= timestamp() DETACH DELETE s"


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    _, salt, _ = stored.split("$")
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)), stored)


# Verified against for unknown usernames, so timing does not reveal which names exist
DUMMY_HASH = hash_password(secrets.token_hex(8))


def normalize(username: str) -> str:
    return username.strip().lower()


def public_user(user: dict) -> dict:
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


def create_user(username: str, password: str, role: str = "user") -> dict:
    [row] = graph().query(CREATE_USER, {
        "id": str(uuid.uuid4()), "username": normalize(username),
        "password_hash": hash_password(password), "role": role,
    })
    return public_user(row["user"])


def list_users() -> list[dict]:
    return [row["user"] for row in graph().query(LIST_USERS)]


def get_user(user_id: str) -> dict | None:
    rows = graph().query(GET_USER, {"id": user_id})
    return rows[0]["user"] if rows else None


def delete_user(user_id: str) -> None:
    graph().query(DELETE_USER, {"id": user_id})


def set_role(user_id: str, role: str) -> None:
    graph().query(SET_USER, {"id": user_id, "props": {"role": role}})


def set_password(user_id: str, password: str, keep_token: str | None = None) -> None:
    # Ends every other session: whoever knew the old password is out
    graph().query(SET_USER, {"id": user_id, "props": {"password_hash": hash_password(password)}})
    graph().query(END_SESSIONS, {"id": user_id, "keep": token_id(keep_token) if keep_token else None})


def authenticate(username: str, password: str) -> dict | None:
    rows = graph().query(USER_BY_NAME, {"username": normalize(username)})
    stored = rows[0]["user"] if rows else None
    # ponytail: no attempt limit, scrypt's ~50 ms is the only brake; add lockout or rate limit if exposed
    matches = verify_password(password, stored["password_hash"] if stored else DUMMY_HASH)
    if stored is None or not matches:
        return None
    return public_user(stored)


def token_id(token: str) -> str:
    # Only the hash is stored: a leaked database holds no usable session
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(user_id: str) -> str:
    graph().query(DELETE_EXPIRED_SESSIONS)
    token = secrets.token_urlsafe(32)
    expires_at = int((time.time() + SESSION_DAYS * 86400) * 1000)
    graph().query(CREATE_SESSION, {"id": token_id(token), "user_id": user_id, "expires_at": expires_at})
    return token


def end_session(token: str) -> None:
    graph().query(DELETE_SESSION, {"id": token_id(token)})


def session_user(token: str) -> dict | None:
    rows = graph().query(SESSION_USER, {"id": token_id(token)})
    return rows[0]["user"] if rows else None


def require_user(request: Request) -> dict | None:
    if request.url.path in PUBLIC_PATHS:
        return None
    token = request.cookies.get(COOKIE)
    user = session_user(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="not signed in")
    return user


def require_admin(user: dict = Depends(require_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="admins only")
    return user


def ensure_admin() -> None:
    """Only while no user exists, so editing .env later never resets anyone's password."""
    if graph().query(COUNT_USERS)[0]["n"]:
        return
    if not (settings.admin_username and settings.admin_password):
        print("no users yet: set ADMIN_USERNAME and ADMIN_PASSWORD in .env and restart to create the first admin")
        return
    create_user(settings.admin_username, settings.admin_password, role="admin")
    print(f"created admin {normalize(settings.admin_username)!r}")
