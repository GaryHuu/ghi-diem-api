"""Ninja REST API.

All ``/api/matches*`` routes require the ``X-Device-Id`` header and are scoped to
that device (wrong device on a specific match => 403). ``/api/shared/{token}`` is
public (no device auth). Every successful mutation broadcasts a WS snapshot.
"""
from ninja import NinjaAPI
from ninja.errors import HttpError

from . import errors, services
from .admin_api import admin_router
from .auth import device_auth
from .broadcast import broadcast_match
from .models import Match
from .schemas import (
    AddPlayerIn,
    CreateMatchIn,
    ErrorSchema,
    MatchSchema,
    SharedMatchSchema,
    TokenSchema,
    UpdatePlayerIn,
    UpdateScoreIn,
    build_match,
    build_shared,
)

api = NinjaAPI(title="Ghi Diem API", auth=device_auth)
api.add_router("/admin", admin_router)


@api.exception_handler(errors.BusinessError)
def on_business_error(request, exc: errors.BusinessError):
    return api.create_response(request, {"detail": exc.message}, status=400)


DEVICE_FORBIDDEN = "Không có quyền truy cập trận đấu này"


def _owned_match(request, match_id: int) -> Match:
    match = Match.objects.filter(id=match_id).first()
    if match is None:
        raise HttpError(404, errors.MATCH_NOT_FOUND)
    if match.device_id != request.auth:
        raise HttpError(403, DEVICE_FORBIDDEN)
    return match


def _match_response(match_id: int) -> dict:
    return build_match(Match.objects.get(id=match_id))


# --------------------------------------------------------------------------- #
# Matches
# --------------------------------------------------------------------------- #
@api.get("/matches", response=list[MatchSchema], by_alias=True)
def list_matches(request):
    return [build_match(m) for m in services.get_matches(request.auth)]


@api.post("/matches", response={200: MatchSchema, 400: ErrorSchema}, by_alias=True)
def create_match(request, payload: CreateMatchIn):
    match = services.create_match(
        request.auth,
        payload.name,
        [p.dict() for p in payload.players],
    )
    return _match_response(match.id)


@api.get("/matches/{int:match_id}", response=MatchSchema, by_alias=True)
def get_match(request, match_id: int):
    _owned_match(request, match_id)
    return _match_response(match_id)


@api.delete("/matches/{int:match_id}")
def delete_match(request, match_id: int):
    match = _owned_match(request, match_id)
    services.delete_match(match)
    return {"detail": "deleted"}


# --------------------------------------------------------------------------- #
# Scoring / game flow
# --------------------------------------------------------------------------- #
@api.put("/matches/{int:match_id}/scores", response={200: MatchSchema, 400: ErrorSchema}, by_alias=True)
def update_score(request, match_id: int, payload: UpdateScoreIn):
    _owned_match(request, match_id)
    services.update_score(match_id, payload.player_id, payload.game_index, payload.value)
    broadcast_match(match_id)
    return _match_response(match_id)


@api.post("/matches/{int:match_id}/next-game", response={200: MatchSchema, 400: ErrorSchema}, by_alias=True)
def next_game(request, match_id: int):
    _owned_match(request, match_id)
    services.next_game(match_id)
    broadcast_match(match_id)
    return _match_response(match_id)


@api.post("/matches/{int:match_id}/end-game", response={200: MatchSchema, 400: ErrorSchema}, by_alias=True)
def end_game(request, match_id: int):
    _owned_match(request, match_id)
    services.end_game(match_id)
    broadcast_match(match_id)
    return _match_response(match_id)


# --------------------------------------------------------------------------- #
# Players
# --------------------------------------------------------------------------- #
@api.post("/matches/{int:match_id}/players", response={200: MatchSchema, 400: ErrorSchema}, by_alias=True)
def add_player(request, match_id: int, payload: AddPlayerIn):
    _owned_match(request, match_id)
    services.add_player(match_id, payload.name, payload.avatar)
    broadcast_match(match_id, include_avatars=True)
    return _match_response(match_id)


@api.put(
    "/matches/{int:match_id}/players/{int:player_id}",
    response={200: MatchSchema, 400: ErrorSchema},
    by_alias=True,
)
def update_player(request, match_id: int, player_id: int, payload: UpdatePlayerIn):
    _owned_match(request, match_id)
    services.update_player(match_id, player_id, payload.dict(exclude_unset=True))
    broadcast_match(match_id, include_avatars=True)
    return _match_response(match_id)


@api.delete("/matches/{int:match_id}/players/{int:player_id}", response={200: MatchSchema, 400: ErrorSchema}, by_alias=True)
def delete_player(request, match_id: int, player_id: int):
    _owned_match(request, match_id)
    services.delete_player(match_id, player_id)
    broadcast_match(match_id)
    return _match_response(match_id)


@api.post(
    "/matches/{int:match_id}/players/{int:player_id}/toggle-autofill",
    response={200: MatchSchema, 400: ErrorSchema},
    by_alias=True,
)
def toggle_autofill(request, match_id: int, player_id: int):
    _owned_match(request, match_id)
    services.toggle_player_auto_fill(match_id, player_id)
    broadcast_match(match_id)
    return _match_response(match_id)


# --------------------------------------------------------------------------- #
# Share
# --------------------------------------------------------------------------- #
@api.post("/matches/{int:match_id}/share", response=TokenSchema, by_alias=True)
def create_share(request, match_id: int):
    match = _owned_match(request, match_id)
    link = services.get_or_create_share_link(match)
    return {"token": link.token}


@api.get("/shared/{token}", auth=None, response=SharedMatchSchema, by_alias=True)
def get_shared(request, token: str):
    match = services.get_match_by_token(token)
    if match is None:
        raise HttpError(404, errors.MATCH_NOT_FOUND)
    return build_shared(match)
