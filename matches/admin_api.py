"""Admin API mounted at ``/api/admin``.

``POST /login`` (no auth) exchanges username/password for a signed token.
Every other route requires ``Authorization: Bearer <token>`` verified by
:class:`AdminBearer`. Admin routes span ALL devices; ``device_id`` is never
serialized (detail reuses ``build_shared``). Beyond reads, the admin can soft
delete and restore any match -- the only writes on this router.
"""
from django.contrib.auth import authenticate
from django.core import signing
from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.security import HttpBearer

from . import errors, services
from .models import Match
from .schemas import (
    AdminMatchSchema,
    ErrorSchema,
    PageSchema,
    SharedMatchSchema,
    TokenSchema,
    build_admin_match,
    build_page,
    build_shared,
)

ADMIN_SALT = "admin-api"
ADMIN_TOKEN_MAX_AGE = 86400  # 24h


class LoginIn(Schema):
    username: str
    password: str


class AdminBearer(HttpBearer):
    """Verify the signed admin token from the ``Authorization: Bearer`` header."""

    def authenticate(self, request, token):
        try:
            data = signing.loads(token, salt=ADMIN_SALT, max_age=ADMIN_TOKEN_MAX_AGE)
        except signing.BadSignature:
            return None
        return data.get("u")


admin_router = Router()


def _admin_match(match_id: int) -> Match:
    """Admin lookups span every device and include soft-deleted matches."""
    match = Match.objects.filter(id=match_id).first()
    if match is None:
        raise HttpError(404, errors.MATCH_NOT_FOUND)
    return match


@admin_router.post("/login", auth=None, response={200: TokenSchema, 401: ErrorSchema})
def login(request, payload: LoginIn):
    user = authenticate(username=payload.username, password=payload.password)
    if user is None:
        raise HttpError(401, errors.ADMIN_INVALID_CREDENTIALS)
    token = signing.dumps({"u": user.id}, salt=ADMIN_SALT)
    return {"token": token}


@admin_router.get(
    "/matches", auth=AdminBearer(), response=PageSchema[AdminMatchSchema], by_alias=True
)
def list_matches(request, page: int = 1, page_size: int = 10):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    # Newest activity first; Match.Meta.ordering (created_at) stays for the
    # end-user match list.
    queryset = Match.objects.prefetch_related("players").order_by("-updated_at", "-id")
    offset = (page - 1) * page_size
    items = [build_admin_match(m) for m in queryset[offset : offset + page_size]]
    return build_page(items, queryset.count(), page, page_size)


@admin_router.get(
    "/matches/{int:match_id}",
    auth=AdminBearer(),
    response=SharedMatchSchema,
    by_alias=True,
)
def get_match(request, match_id: int):
    return build_shared(_admin_match(match_id))


@admin_router.delete(
    "/matches/{int:match_id}",
    auth=AdminBearer(),
    response=AdminMatchSchema,
    by_alias=True,
)
def delete_match(request, match_id: int):
    """Soft delete any match, regardless of which device owns it."""
    match = _admin_match(match_id)
    if match.deleted_at is None:
        services.delete_match(match)
    return build_admin_match(match)


@admin_router.post(
    "/matches/{int:match_id}/restore",
    auth=AdminBearer(),
    response=AdminMatchSchema,
    by_alias=True,
)
def restore_match(request, match_id: int):
    """Undo a soft delete so the owner device sees the match again."""
    match = _admin_match(match_id)
    if match.deleted_at is not None:
        services.restore_match(match)
    return build_admin_match(match)
