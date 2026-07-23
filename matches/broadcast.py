"""Broadcast a full match snapshot to the match's WebSocket group.

Called after every successful REST mutation. Score-path snapshots exclude
``avatar`` (heavy Base64); player add/update broadcasts pass
``include_avatars=True`` so avatar changes reach live viewers.
"""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Match
from .schemas import build_snapshot


def group_name(match_id: int) -> str:
    return f"match_{match_id}"


def broadcast_match(match_id: int, include_avatars: bool = False) -> None:
    match = Match.objects.filter(id=match_id).first()
    if match is None:
        return
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        group_name(match_id),
        {"type": "match.snapshot", "data": build_snapshot(match, include_avatars)},
    )
