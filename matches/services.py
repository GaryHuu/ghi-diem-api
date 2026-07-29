"""Business-logic layer.

Faithful port of ``src/services/match/index.ts`` (zero-sum validation, autoFill
recompute, toggle autoFill side effects). Every read-modify-write on the
``scores`` JSON runs inside a transaction with ``select_for_update`` on the
Match row to avoid clobbering.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from . import errors
from .models import Match, Player, ShareLink


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def current_game_number(players: list[Player]) -> int:
    """Number of games in the match, derived from the first player's scores.

    Mirrors FE ``getCurrentGameNumber``: ``players.find(Boolean)?.scores.length || 1``.
    """
    for player in players:
        return len(player.scores) or 1
    return 1


def _score_at(player: Player, index: int) -> int:
    scores = player.scores
    if 0 <= index < len(scores):
        return scores[index] or 0
    return 0


def _is_name_duplicate(players: list[Player], name: str, exclude_id: int | None = None) -> bool:
    target = name.strip().lower()
    return any(
        p.name.strip().lower() == target and (exclude_id is None or p.id != exclude_id)
        for p in players
    )


def _validate_all_game_scores(players: list[Player], game_count: int) -> None:
    """Zero-sum rule enforced at the game boundary (port of ``validateAllGameScores``)."""
    if len(players) < 2:
        raise errors.BusinessError(errors.MATCH_MIN_PLAYERS)

    for game_index in range(game_count):
        total = sum(_score_at(p, game_index) for p in players)
        if total == 0:
            continue
        if game_index == game_count - 1:
            raise errors.BusinessError(errors.GAME_CURRENT_SCORE_NOT_ZERO)
        raise errors.BusinessError(errors.game_score_not_zero(game_index + 1))


def recalculate_auto_fill_player(match: Match, game_index: int) -> None:
    """Recompute the autoFill player's score for a game = -sum(others).

    Port of ``recalculateAutoFillPlayer``; called after every score write.
    """
    players = list(match.players.all())
    auto_player = next((p for p in players if p.auto_fill), None)
    if auto_player is None:
        return

    other_sum = sum(_score_at(p, game_index) for p in players if p.id != auto_player.id)
    while len(auto_player.scores) <= game_index:
        auto_player.scores.append(0)
    auto_player.scores[game_index] = -other_sum
    auto_player.save(update_fields=["scores"])


# --------------------------------------------------------------------------- #
# Match CRUD
# --------------------------------------------------------------------------- #
def create_match(device_id, name: str, players_data: list[dict]) -> Match:
    if not name or not name.strip():
        raise errors.BusinessError(errors.MATCH_NAME_REQUIRED)

    with transaction.atomic():
        match = Match.objects.create(name=name, device_id=device_id)
        seen: list[Player] = []
        for order, pdata in enumerate(players_data):
            pname = (pdata.get("name") or "").strip()
            if not pname:
                raise errors.BusinessError(errors.PLAYER_NAME_REQUIRED)
            if _is_name_duplicate(seen, pname):
                raise errors.BusinessError(errors.player_name_exists(pname))
            player = Player.objects.create(
                match=match,
                name=pname,
                scores=[0],
                avatar=pdata.get("avatar"),
                order=order,
            )
            seen.append(player)
    return match


def get_matches(device_id) -> list[Match]:
    return list(
        Match.objects.filter(device_id=device_id, deleted_at__isnull=True)
        .prefetch_related("players")
    )


def touch_match(match: Match) -> None:
    """Refresh ``updated_at``.

    Django skips ``auto_now`` fields unless they are listed in
    ``update_fields``, and most mutations only write ``Player`` rows, so every
    mutating path has to say so explicitly.
    """
    match.save(update_fields=["updated_at"])


def delete_match(match: Match) -> None:
    """Soft delete: hide from user-facing views, keep the row for the admin."""
    match.deleted_at = timezone.now()
    match.save(update_fields=["deleted_at", "updated_at"])


def restore_match(match: Match) -> None:
    """Undo a soft delete (admin only)."""
    match.deleted_at = None
    match.save(update_fields=["deleted_at", "updated_at"])


# --------------------------------------------------------------------------- #
# Players
# --------------------------------------------------------------------------- #
def add_player(match_id: int, name: str, avatar: str | None = None) -> Player:
    if not name or not name.strip():
        raise errors.BusinessError(errors.PLAYER_NAME_REQUIRED)
    name = name.strip()

    with transaction.atomic():
        match = Match.objects.select_for_update().get(id=match_id)
        players = list(match.players.all())
        if _is_name_duplicate(players, name):
            raise errors.BusinessError(errors.player_name_exists(name))

        game_count = current_game_number(players)
        next_order = max((p.order for p in players), default=-1) + 1
        player = Player.objects.create(
            match=match,
            name=name,
            scores=[0] * game_count,
            avatar=avatar,
            order=next_order,
        )
        touch_match(match)
        return player


def update_player(match_id: int, player_id: int, fields: dict) -> Player:
    with transaction.atomic():
        match = Match.objects.select_for_update().get(id=match_id)
        players = list(match.players.all())
        player = next((p for p in players if p.id == player_id), None)
        if player is None:
            raise errors.BusinessError(errors.PLAYER_NOT_FOUND)

        update_cols: list[str] = []
        if "name" in fields and fields["name"] is not None:
            new_name = fields["name"].strip()
            if not new_name:
                raise errors.BusinessError(errors.PLAYER_NAME_REQUIRED)
            if _is_name_duplicate(players, new_name, exclude_id=player.id):
                raise errors.BusinessError(errors.PLAYER_NAME_EXISTS)
            player.name = new_name
            update_cols.append("name")
        if "gap" in fields:
            player.gap = fields["gap"]
            update_cols.append("gap")
        if "avatar" in fields:
            player.avatar = fields["avatar"]
            update_cols.append("avatar")
        if "order" in fields and fields["order"] is not None:
            player.order = fields["order"]
            update_cols.append("order")

        if update_cols:
            player.save(update_fields=update_cols)
            touch_match(match)
        return player


def delete_player(match_id: int, player_id: int) -> None:
    with transaction.atomic():
        match = Match.objects.select_for_update().get(id=match_id)
        deleted, _ = match.players.filter(id=player_id).delete()
        if not deleted:
            raise errors.BusinessError(errors.PLAYER_NOT_FOUND)
        touch_match(match)


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def update_score(match_id: int, player_id: int, game_index: int, value) -> Match:
    if value is None:
        raise errors.BusinessError(errors.GAME_SCORE_INVALID)
    if game_index is None or game_index < 0:
        raise errors.BusinessError(errors.GAME_NUMBER_INVALID)

    with transaction.atomic():
        match = Match.objects.select_for_update().get(id=match_id)
        player = match.players.filter(id=player_id).first()
        if player is None:
            raise errors.BusinessError(errors.PLAYER_NOT_FOUND)
        if game_index >= len(player.scores):
            raise errors.BusinessError(errors.GAME_NUMBER_INVALID)

        player.scores[game_index] = value
        player.save(update_fields=["scores"])

        recalculate_auto_fill_player(match, game_index)
        touch_match(match)
    return match


def next_game(match_id: int) -> Match:
    with transaction.atomic():
        match = Match.objects.select_for_update().get(id=match_id)
        players = list(match.players.all())
        _validate_all_game_scores(players, current_game_number(players))
        for player in players:
            player.scores.append(0)
            player.save(update_fields=["scores"])
        touch_match(match)
    return match


def end_game(match_id: int) -> Match:
    with transaction.atomic():
        match = Match.objects.select_for_update().get(id=match_id)
        players = list(match.players.all())
        _validate_all_game_scores(players, current_game_number(players))
        match.status = Match.Status.ENDED
        match.save(update_fields=["status", "updated_at"])
    return match


def toggle_player_auto_fill(match_id: int, player_id: int) -> Match:
    """Port of ``togglePlayerAutoFill``: only one autoFill at a time; enabling
    recomputes the target's current-game score = -sum(others)."""
    with transaction.atomic():
        match = Match.objects.select_for_update().get(id=match_id)
        players = list(match.players.all())
        target = next((p for p in players if p.id == player_id), None)
        if target is None:
            raise errors.BusinessError(errors.PLAYER_NOT_FOUND)

        game_index = current_game_number(players) - 1
        enabling = not target.auto_fill

        for p in players:
            if p.auto_fill:
                p.auto_fill = False
                p.save(update_fields=["auto_fill"])

        if enabling:
            target.auto_fill = True
            other_sum = sum(
                _score_at(p, game_index) for p in players if p.id != target.id
            )
            while len(target.scores) <= game_index:
                target.scores.append(0)
            target.scores[game_index] = -other_sum
            target.save(update_fields=["auto_fill", "scores"])

        touch_match(match)
    return match


# --------------------------------------------------------------------------- #
# Share links
# --------------------------------------------------------------------------- #
def get_or_create_share_link(match: Match) -> ShareLink:
    """Idempotent for ``view`` links: returns the existing view link if present."""
    existing = match.share_links.filter(permission=ShareLink.Permission.VIEW).first()
    if existing:
        return existing
    return ShareLink.objects.create(match=match, permission=ShareLink.Permission.VIEW)


def get_match_by_token(token: str) -> Match | None:
    link = (
        ShareLink.objects.select_related("match")
        .filter(token=token, match__deleted_at__isnull=True)
        .first()
    )
    return link.match if link else None
