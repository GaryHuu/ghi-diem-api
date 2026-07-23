import json

import pytest

pytestmark = pytest.mark.django_db


def _create_match(client, headers, players=("Alice", "Bob")):
    resp = client.post(
        "/matches",
        json={"name": "M", "players": [{"name": p} for p in players]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.content
    return resp.json()


# --------------------------------------------------------------------------- #
# Device auth
# --------------------------------------------------------------------------- #
def test_missing_device_header_401(client):
    resp = client.get("/matches")
    assert resp.status_code == 401


def test_invalid_device_header_401(client):
    resp = client.get("/matches", headers={"X-Device-Id": "not-a-uuid"})
    assert resp.status_code == 401


def test_valid_device_header_ok(client, headers):
    resp = client.get("/matches", headers=headers)
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# Ownership
# --------------------------------------------------------------------------- #
def test_wrong_device_forbidden_on_write(client, headers, other_device_id):
    match = _create_match(client, headers)
    player_id = match["players"][0]["id"]
    resp = client.put(
        f"/matches/{match['id']}/scores",
        json={"playerId": player_id, "gameIndex": 0, "value": 3},
        headers={"X-Device-Id": str(other_device_id)},
    )
    assert resp.status_code == 403


def test_wrong_device_forbidden_on_read(client, headers, other_device_id):
    match = _create_match(client, headers)
    resp = client.get(
        f"/matches/{match['id']}",
        headers={"X-Device-Id": str(other_device_id)},
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Serialization shape (camelCase, isFinished, no device_id)
# --------------------------------------------------------------------------- #
def test_match_response_shape(client, headers):
    match = _create_match(client, headers)
    assert set(match.keys()) == {"id", "name", "createdAt", "isFinished", "total", "players"}
    assert match["isFinished"] is False
    assert match["total"] == 1
    player = match["players"][0]
    assert set(player.keys()) == {"id", "name", "scores", "gap", "autoFill", "avatar"}
    assert "device_id" not in json.dumps(match)


def test_update_score_returns_snapshot(client, headers):
    match = _create_match(client, headers)
    pid = match["players"][0]["id"]
    resp = client.put(
        f"/matches/{match['id']}/scores",
        json={"playerId": pid, "gameIndex": 0, "value": 9},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    scored = next(p for p in body["players"] if p["id"] == pid)
    assert scored["scores"][0] == 9


def test_zero_sum_rejected_via_api(client, headers):
    match = _create_match(client, headers)
    pid = match["players"][0]["id"]
    client.put(
        f"/matches/{match['id']}/scores",
        json={"playerId": pid, "gameIndex": 0, "value": 5},
        headers=headers,
    )
    resp = client.post(f"/matches/{match['id']}/next-game", headers=headers)
    assert resp.status_code == 400
    assert "không bằng 0" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# Share
# --------------------------------------------------------------------------- #
def test_share_is_idempotent(client, headers):
    match = _create_match(client, headers)
    t1 = client.post(f"/matches/{match['id']}/share", headers=headers).json()["token"]
    t2 = client.post(f"/matches/{match['id']}/share", headers=headers).json()["token"]
    assert t1 == t2


def test_shared_endpoint_public_no_device_id(client, headers):
    match = _create_match(client, headers)
    token = client.post(f"/matches/{match['id']}/share", headers=headers).json()["token"]
    # No device header on the shared route.
    resp = client.get(f"/shared/{token}")
    assert resp.status_code == 200
    body = resp.json()
    assert "device_id" not in json.dumps(body)
    assert "deviceId" not in json.dumps(body)


def test_shared_read_model_current_equals_total(client, headers):
    match = _create_match(client, headers)
    token = client.post(f"/matches/{match['id']}/share", headers=headers).json()["token"]
    body = client.get(f"/shared/{token}").json()
    assert body["current"] == body["total"]


def test_shared_unknown_token_404(client):
    resp = client.get("/shared/does-not-exist")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Broadcast after mutation
# --------------------------------------------------------------------------- #
def test_broadcast_called_after_score_mutation(client, headers, monkeypatch):
    calls = []
    monkeypatch.setattr("matches.api.broadcast_match", lambda mid: calls.append(mid))
    match = _create_match(client, headers)
    pid = match["players"][0]["id"]
    client.put(
        f"/matches/{match['id']}/scores",
        json={"playerId": pid, "gameIndex": 0, "value": 1},
        headers=headers,
    )
    assert calls == [match["id"]]
