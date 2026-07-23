import json
import uuid

import pytest
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from ninja.testing import TestClient

from matches import services
from matches.api import api

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return TestClient(api)


def _login(client, username="admin", password="1"):
    return client.post("/admin/login", json={"username": username, "password": password})


def _auth_headers(client):
    token = _login(client).json()["token"]
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# Admin seed
# --------------------------------------------------------------------------- #
def test_admin_password_is_hashed():
    admin = User.objects.get(username="admin")
    assert admin.password != "1"
    assert admin.password.startswith("pbkdf2_")


def test_seed_idempotent():
    assert User.objects.filter(username="admin").count() == 1
    # Re-running the same get_or_create keeps the row count at 1.
    User.objects.get_or_create(
        username="admin",
        defaults={"password": make_password("1"), "is_staff": True},
    )
    assert User.objects.filter(username="admin").count() == 1


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #
def test_login_ok_returns_token(client):
    resp = _login(client)
    assert resp.status_code == 200
    assert resp.json()["token"]


def test_login_wrong_password_401(client):
    resp = _login(client, password="wrong")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Sai tên đăng nhập hoặc mật khẩu"


# --------------------------------------------------------------------------- #
# Auth on protected routes
# --------------------------------------------------------------------------- #
def test_matches_requires_auth_header(client):
    resp = client.get("/admin/matches")
    assert resp.status_code == 401


def test_matches_garbage_token_401(client):
    resp = client.get(
        "/admin/matches", headers={"Authorization": "Bearer not-a-valid-token"}
    )
    assert resp.status_code == 401


def test_token_works_on_matches(client):
    resp = client.get("/admin/matches", headers=_auth_headers(client))
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# List across devices
# --------------------------------------------------------------------------- #
def test_list_returns_matches_from_different_devices(client):
    dev_a = uuid.uuid4()
    dev_b = uuid.uuid4()
    services.create_match(dev_a, "Match A", [{"name": "Alice"}, {"name": "Bob"}])
    services.create_match(dev_b, "Match B", [{"name": "Carol"}, {"name": "Dave"}])

    resp = client.get("/admin/matches", headers=_auth_headers(client))
    assert resp.status_code == 200
    body = resp.json()
    names = {m["name"] for m in body}
    assert {"Match A", "Match B"} <= names
    match = body[0]
    assert set(match.keys()) == {
        "id",
        "name",
        "isFinished",
        "total",
        "playerCount",
        "createdAt",
        "deviceId",
    }
    assert match["playerCount"] == 2
    # deviceId is admin-only: exposed here (behind the Bearer token) for the
    # dashboard's device column/filter, never on shared/owner read-models.
    assert match["deviceId"] in {str(dev_a), str(dev_b)}


# --------------------------------------------------------------------------- #
# Detail (no device_id leak)
# --------------------------------------------------------------------------- #
def test_detail_has_no_device_id(client):
    dev = uuid.uuid4()
    m = services.create_match(dev, "Solo", [{"name": "Alice"}, {"name": "Bob"}])
    resp = client.get(f"/admin/matches/{m.id}", headers=_auth_headers(client))
    assert resp.status_code == 200
    body = resp.json()
    assert "device_id" not in json.dumps(body)
    assert "deviceId" not in json.dumps(body)
    assert body["current"] == body["total"]


def test_detail_unknown_404(client):
    resp = client.get("/admin/matches/999999", headers=_auth_headers(client))
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Auth composition guards (device credential never substitutes Bearer; expiry)
# --------------------------------------------------------------------------- #
def test_valid_device_id_alone_is_rejected(client):
    resp = client.get(
        "/admin/matches", headers={"X-Device-Id": str(uuid.uuid4())}
    )
    assert resp.status_code == 401


def test_expired_token_is_rejected(client, monkeypatch):
    from django.core import signing

    from matches import admin_api

    token = signing.dumps({"u": 1}, salt="admin-api")

    original_loads = signing.loads

    def loads_with_zero_max_age(value, **kwargs):
        kwargs["max_age"] = -1
        return original_loads(value, **kwargs)

    monkeypatch.setattr(admin_api.signing, "loads", loads_with_zero_max_age)
    resp = client.get(
        "/admin/matches", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401
