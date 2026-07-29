"""``Match.updated_at`` tracks the last activity on a match.

The interesting part is that most mutations only write ``Player`` rows, so
without an explicit touch the timestamp would never move.
"""
import uuid

import pytest

from matches import services
from matches.models import Match


@pytest.fixture
def match(device_id):
    return services.create_match(device_id, "Tracked", [{"name": "Alice"}, {"name": "Bob"}])


def _updated_at(match_id: int):
    return Match.objects.get(id=match_id).updated_at


@pytest.mark.django_db
def test_score_write_moves_updated_at(match):
    before = _updated_at(match.id)
    services.update_score(match.id, match.players.first().id, 0, 5)
    assert _updated_at(match.id) > before


@pytest.mark.django_db
def test_player_and_round_mutations_move_updated_at(match):
    player_id = match.players.first().id

    checkpoints = [
        lambda: services.add_player(match.id, "Carol"),
        lambda: services.update_player(match.id, player_id, {"name": "Alice 2"}),
        lambda: services.toggle_player_auto_fill(match.id, player_id),
        lambda: services.next_game(match.id),
        lambda: services.delete_player(match.id, player_id),
    ]
    for mutate in checkpoints:
        before = _updated_at(match.id)
        mutate()
        assert _updated_at(match.id) > before


@pytest.mark.django_db
def test_end_and_delete_move_updated_at(match):
    before = _updated_at(match.id)
    services.end_game(match.id)
    after_end = _updated_at(match.id)
    assert after_end > before

    services.delete_match(Match.objects.get(id=match.id))
    assert _updated_at(match.id) > after_end


@pytest.mark.django_db
def test_admin_list_is_ordered_by_updated_at(client):
    from .test_admin_api import _auth_headers

    older = services.create_match(uuid.uuid4(), "Older", [{"name": "A"}, {"name": "B"}])
    newer = services.create_match(uuid.uuid4(), "Newer", [{"name": "C"}, {"name": "D"}])

    # Touching the older match must float it to the top of the admin list even
    # though it was created first.
    services.update_score(older.id, older.players.first().id, 0, 3)

    body = client.get("/admin/matches", headers=_auth_headers(client)).json()
    assert [m["name"] for m in body["items"][:2]] == ["Older", "Newer"]
    assert body["items"][0]["updatedAt"] > body["items"][1]["updatedAt"]
    assert newer.id != older.id


@pytest.mark.django_db
def test_end_user_list_keeps_created_at_order(device_id):
    first = services.create_match(device_id, "First", [{"name": "A"}, {"name": "B"}])
    second = services.create_match(device_id, "Second", [{"name": "C"}, {"name": "D"}])
    services.update_score(first.id, first.players.first().id, 0, 1)

    names = [m.name for m in services.get_matches(device_id)]
    assert names == ["Second", "First"]
