import pytest

from app import auth
from app.api import app

ADMIN = {"id": "u-admin", "username": "admin", "role": "admin"}


@pytest.fixture(autouse=True)
def signed_in():
    """Every API test runs as a signed-in admin unless it takes the session away (tests/test_auth.py)."""
    app.dependency_overrides[auth.require_user] = lambda: ADMIN
    yield
    app.dependency_overrides.pop(auth.require_user, None)
