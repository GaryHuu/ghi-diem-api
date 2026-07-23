import uuid

import pytest
from ninja.testing import TestClient

from matches import services
from matches.api import api


@pytest.fixture(autouse=True)
def in_memory_channel_layer(settings):
    """Use the in-memory channel layer for all tests (no Redis needed)."""
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }


@pytest.fixture
def device_id():
    return uuid.uuid4()


@pytest.fixture
def other_device_id():
    return uuid.uuid4()


@pytest.fixture
def client():
    return TestClient(api)


@pytest.fixture
def headers(device_id):
    return {"X-Device-Id": str(device_id)}


@pytest.fixture
def two_player_match(device_id):
    """A match owned by ``device_id`` with two players (one game, scores [0])."""
    return services.create_match(
        device_id,
        "Test Match",
        [{"name": "Alice"}, {"name": "Bob"}],
    )
