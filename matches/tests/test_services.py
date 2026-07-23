import pytest

from matches import errors, services
from matches.models import Match

pytestmark = pytest.mark.django_db


def _set_scores(match, values_by_index):
    """Helper: set player scores directly, ordered by player order."""
    players = list(match.players.all())
    for i, player in enumerate(players):
        for game_index, value in values_by_index.get(i, {}).items():
            while len(player.scores) <= game_index:
                player.scores.append(0)
            player.scores[game_index] = value
        player.save()


def test_next_game_rejects_non_zero_sum(two_player_match):
    match = two_player_match
    # Alice 5, Bob 0 -> sum 5, not zero.
    _set_scores(match, {0: {0: 5}})
    with pytest.raises(errors.BusinessError) as exc:
        services.next_game(match.id)
    assert exc.value.message == errors.GAME_CURRENT_SCORE_NOT_ZERO


def test_next_game_accepts_zero_sum_and_appends_game(two_player_match):
    match = two_player_match
    _set_scores(match, {0: {0: 5}, 1: {0: -5}})
    services.next_game(match.id)
    players = list(match.players.all())
    assert all(len(p.scores) == 2 for p in players)
    assert services.current_game_number(players) == 2


def test_end_game_rejects_non_zero_sum(two_player_match):
    match = two_player_match
    _set_scores(match, {0: {0: 3}})
    with pytest.raises(errors.BusinessError) as exc:
        services.end_game(match.id)
    assert exc.value.message == errors.GAME_CURRENT_SCORE_NOT_ZERO
    match.refresh_from_db()
    assert match.status == Match.Status.PLAYING


def test_end_game_marks_ended_on_zero_sum(two_player_match):
    match = two_player_match
    _set_scores(match, {0: {0: 4}, 1: {0: -4}})
    services.end_game(match.id)
    match.refresh_from_db()
    assert match.status == Match.Status.ENDED


def test_next_game_requires_min_two_players(device_id):
    match = services.create_match(device_id, "Solo", [{"name": "Only"}])
    with pytest.raises(errors.BusinessError) as exc:
        services.next_game(match.id)
    assert exc.value.message == errors.MATCH_MIN_PLAYERS


def test_update_score_recomputes_autofill_player(two_player_match):
    match = two_player_match
    alice, bob = list(match.players.all())
    # Bob is the autoFill player.
    services.toggle_player_auto_fill(match.id, bob.id)
    # Owner writes Alice's score; Bob must become the negation.
    services.update_score(match.id, alice.id, 0, 7)
    bob.refresh_from_db()
    assert bob.scores[0] == -7
    # And the game is zero-sum as a result.
    alice.refresh_from_db()
    assert alice.scores[0] + bob.scores[0] == 0


def test_toggle_autofill_turns_off_other_players(device_id):
    match = services.create_match(
        device_id, "Three", [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    )
    a, b, c = list(match.players.all())
    services.toggle_player_auto_fill(match.id, a.id)
    services.toggle_player_auto_fill(match.id, b.id)
    a.refresh_from_db()
    b.refresh_from_db()
    c.refresh_from_db()
    assert b.auto_fill is True
    assert a.auto_fill is False
    assert c.auto_fill is False


def test_toggle_autofill_off_when_toggled_twice(two_player_match):
    match = two_player_match
    alice, _ = list(match.players.all())
    services.toggle_player_auto_fill(match.id, alice.id)
    services.toggle_player_auto_fill(match.id, alice.id)
    alice.refresh_from_db()
    assert alice.auto_fill is False


def test_add_player_gets_zeros_for_existing_games(two_player_match):
    match = two_player_match
    _set_scores(match, {0: {0: 2}, 1: {0: -2}})
    services.next_game(match.id)  # now 2 games
    new_player = services.add_player(match.id, "Carol")
    assert new_player.scores == [0, 0]


def test_duplicate_player_name_rejected(two_player_match):
    match = two_player_match
    with pytest.raises(errors.BusinessError) as exc:
        services.add_player(match.id, "alice")  # case-insensitive dup
    assert "Alice" in exc.value.message or "alice" in exc.value.message
