"""Ninja schemas + serialization builders.

Output is camelCase (via alias generator) to mirror ``src/utils/types``. The
model ``status`` (playing|ended) is serialized as ``isFinished: bool``. Neither
the shared read-model nor the WS snapshot ever contains ``device_id`` (owner
credential) -- there is a test asserting this.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ninja import Schema
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

from .models import Match, Player
from .services import current_game_number


class CamelSchema(Schema):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# --------------------------------------------------------------------------- #
# Output schemas
# --------------------------------------------------------------------------- #
class PlayerSchema(CamelSchema):
    id: int
    name: str
    scores: list[Optional[int]]
    gap: Optional[int] = None
    auto_fill: bool = False
    avatar: Optional[str] = None


class MatchSchema(CamelSchema):
    """Owner read-model. No ``device_id``."""

    id: int
    name: str
    created_at: datetime
    is_finished: bool
    total: int
    players: list[PlayerSchema]


class SharedMatchSchema(CamelSchema):
    """Shared/public read-model. ``current == total``. No ``device_id``."""

    id: int
    name: str
    is_finished: bool
    total: int
    current: int
    players: list[PlayerSchema]


class AdminMatchSchema(CamelSchema):
    """Admin listing read-model (all devices). No ``device_id``."""

    id: int
    name: str
    is_finished: bool
    total: int
    player_count: int
    created_at: datetime


class TokenSchema(CamelSchema):
    token: str


class ErrorSchema(Schema):
    detail: str


# --------------------------------------------------------------------------- #
# Input schemas
# --------------------------------------------------------------------------- #
class PlayerCreateIn(CamelSchema):
    name: str
    avatar: Optional[str] = None


class CreateMatchIn(CamelSchema):
    name: str
    players: list[PlayerCreateIn] = []


class AddPlayerIn(CamelSchema):
    name: str
    avatar: Optional[str] = None


class UpdatePlayerIn(CamelSchema):
    name: Optional[str] = None
    gap: Optional[int] = None
    avatar: Optional[str] = None
    order: Optional[int] = None


class UpdateScoreIn(CamelSchema):
    player_id: int
    game_index: int
    value: int


# --------------------------------------------------------------------------- #
# Serialization builders (snake keys; ninja dumps camelCase by alias)
# --------------------------------------------------------------------------- #
def serialize_player(player: Player, include_avatar: bool = True) -> dict:
    data = {
        "id": player.id,
        "name": player.name,
        "scores": player.scores,
        "gap": player.gap,
        "auto_fill": player.auto_fill,
    }
    if include_avatar:
        data["avatar"] = player.avatar
    return data


def build_match(match: Match) -> dict:
    players = list(match.players.all())
    return {
        "id": match.id,
        "name": match.name,
        "created_at": match.created_at,
        "is_finished": match.status == Match.Status.ENDED,
        "total": current_game_number(players),
        "players": [serialize_player(p) for p in players],
    }


def build_shared(match: Match) -> dict:
    data = build_match(match)
    data["current"] = data["total"]
    return data


def build_admin_match(match: Match) -> dict:
    players = list(match.players.all())
    return {
        "id": match.id,
        "name": match.name,
        "is_finished": match.status == Match.Status.ENDED,
        "total": current_game_number(players),
        "player_count": len(players),
        "created_at": match.created_at,
    }


def build_snapshot(match: Match, include_avatars: bool = False) -> dict:
    """WS payload: shared read-model dumped camelCase (same shape as REST).

    ``avatar`` (heavy Base64) rides along only on the initial connect snapshot
    and on player add/update broadcasts (the mutations that can change it);
    score-path broadcasts stay light and the FE merges avatars from its cache.
    """
    data = SharedMatchSchema(**build_shared(match)).model_dump(by_alias=True)
    if not include_avatars:
        for player in data["players"]:
            player.pop("avatar", None)
    return data
