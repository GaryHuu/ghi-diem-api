"""Health endpoint: public, reflects DB + Redis reachability."""
import pytest

from matches import health


@pytest.mark.django_db
def test_health_ok(client, monkeypatch):
    monkeypatch.setattr(health, "check_redis", lambda: True)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": True, "redis": True}


@pytest.mark.django_db
def test_health_redis_down_503(client, monkeypatch):
    monkeypatch.setattr(health, "check_redis", lambda: False)
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json() == {"status": "down", "db": True, "redis": False}


@pytest.mark.django_db
def test_health_db_down_503(client, monkeypatch):
    monkeypatch.setattr(health, "check_db", lambda: False)
    monkeypatch.setattr(health, "check_redis", lambda: True)
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json() == {"status": "down", "db": False, "redis": True}


def test_check_redis_unreachable_returns_false(settings):
    settings.REDIS_URL = "redis://127.0.0.1:1/0"
    assert health.check_redis() is False


@pytest.mark.django_db
def test_health_public_url_path(monkeypatch):
    """Pin the full public path (URLconf + middleware), which TestClient bypasses."""
    from django.test import Client

    monkeypatch.setattr(health, "check_redis", lambda: True)
    resp = Client().get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
