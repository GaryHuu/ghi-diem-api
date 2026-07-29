"""Admin can soft delete and restore any match, across devices."""
import uuid

import pytest

from matches import services
from matches.models import Match

from .test_admin_api import _auth_headers


@pytest.fixture
def other_device_match():
    """Owned by a device that is not the caller: the admin still controls it."""
    return services.create_match(
        uuid.uuid4(), "Someone else's", [{"name": "Alice"}, {"name": "Bob"}]
    )


@pytest.mark.django_db
def test_delete_soft_deletes_and_hides_from_owner(client, other_device_match):
    device_id = other_device_match.device_id

    resp = client.delete(
        f"/admin/matches/{other_device_match.id}", headers=_auth_headers(client)
    )
    assert resp.status_code == 200
    assert resp.json()["deletedAt"] is not None
    assert Match.objects.get(id=other_device_match.id).deleted_at is not None
    # The owner's list hides it, but the row survives for the admin.
    assert services.get_matches(device_id) == []


@pytest.mark.django_db
def test_restore_brings_the_match_back_for_the_owner(client, other_device_match):
    device_id = other_device_match.device_id
    services.delete_match(other_device_match)

    resp = client.post(
        f"/admin/matches/{other_device_match.id}/restore", headers=_auth_headers(client)
    )
    assert resp.status_code == 200
    assert resp.json()["deletedAt"] is None
    assert Match.objects.get(id=other_device_match.id).deleted_at is None
    assert [m.id for m in services.get_matches(device_id)] == [other_device_match.id]


@pytest.mark.django_db
def test_actions_are_idempotent(client, other_device_match):
    path = f"/admin/matches/{other_device_match.id}"
    headers = _auth_headers(client)

    client.delete(path, headers=headers)
    first_deleted_at = Match.objects.get(id=other_device_match.id).deleted_at
    # Deleting twice must not move the timestamp.
    assert client.delete(path, headers=headers).status_code == 200
    assert Match.objects.get(id=other_device_match.id).deleted_at == first_deleted_at

    assert client.post(f"{path}/restore", headers=headers).status_code == 200
    assert client.post(f"{path}/restore", headers=headers).status_code == 200
    assert Match.objects.get(id=other_device_match.id).deleted_at is None


@pytest.mark.django_db
def test_delete_and_restore_require_the_bearer_token(client, other_device_match):
    path = f"/admin/matches/{other_device_match.id}"
    assert client.delete(path).status_code == 401
    assert client.post(f"{path}/restore").status_code == 401
    # A device id is not a substitute for admin auth.
    device_header = {"X-Device-Id": str(other_device_match.device_id)}
    assert client.delete(path, headers=device_header).status_code == 401
    assert Match.objects.get(id=other_device_match.id).deleted_at is None


@pytest.mark.django_db
def test_unknown_match_returns_404(client):
    headers = _auth_headers(client)
    assert client.delete("/admin/matches/999999", headers=headers).status_code == 404
    assert (
        client.post("/admin/matches/999999/restore", headers=headers).status_code == 404
    )
