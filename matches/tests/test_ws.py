import json

import pytest
from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

from matches import services
from matches.broadcast import broadcast_match
from matches.routing import websocket_urlpatterns

pytestmark = pytest.mark.django_db(transaction=True)

application = URLRouter(websocket_urlpatterns)


async def _make_shared_match():
    match = await sync_to_async(services.create_match)(
        __import__("uuid").uuid4(),
        "WS Match",
        [{"name": "Alice", "avatar": "data:image/png;base64,AAAA"}, {"name": "Bob"}],
    )
    link = await sync_to_async(services.get_or_create_share_link)(match)
    return match, link


async def test_consumer_initial_snapshot_has_avatars_but_no_device_id():
    match, link = await _make_shared_match()
    communicator = WebsocketCommunicator(application, f"/ws/share/{link.token}")
    connected, _ = await communicator.connect()
    assert connected

    message = await communicator.receive_json_from()
    assert message["type"] == "match.snapshot"
    data = message["data"]
    assert data["current"] == data["total"]
    # camelCase shape identical to REST, never the owner credential.
    assert "isFinished" in data
    dumped = json.dumps(message)
    assert "device_id" not in dumped
    assert "deviceId" not in dumped
    # Initial snapshot carries avatars so the viewer can seed its cache.
    avatars = {p["name"]: p["avatar"] for p in data["players"]}
    assert avatars["Alice"] == "data:image/png;base64,AAAA"
    assert avatars["Bob"] is None

    await communicator.disconnect()


async def test_unknown_token_rejected():
    communicator = WebsocketCommunicator(application, "/ws/share/nope")
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()


async def test_broadcast_delivers_snapshot_to_group():
    match, link = await _make_shared_match()
    communicator = WebsocketCommunicator(application, f"/ws/share/{link.token}")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.receive_json_from()  # drain initial snapshot

    # A mutation followed by broadcast_match must reach the connected viewer.
    # Default (score-path) broadcasts stay light: no avatar key.
    await sync_to_async(broadcast_match)(match.id)
    message = await communicator.receive_json_from()
    assert message["type"] == "match.snapshot"
    assert message["data"]["id"] == match.id
    for player in message["data"]["players"]:
        assert "avatar" not in player

    # Player add/update broadcasts include avatars so edits reach live viewers.
    await sync_to_async(broadcast_match)(match.id, include_avatars=True)
    message = await communicator.receive_json_from()
    avatars = {p["name"]: p["avatar"] for p in message["data"]["players"]}
    assert avatars["Alice"] == "data:image/png;base64,AAAA"

    await communicator.disconnect()


async def test_viewer_messages_are_ignored():
    match, link = await _make_shared_match()
    communicator = WebsocketCommunicator(application, f"/ws/share/{link.token}")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.receive_json_from()  # drain initial snapshot

    # Viewer (permission=view) sends a write attempt; it must be silently ignored.
    await communicator.send_json_to({"type": "edit", "data": {"value": 1}})
    assert await communicator.receive_nothing() is True

    await communicator.disconnect()
