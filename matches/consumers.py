"""WebSocket consumer for the public share view."""
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .broadcast import group_name
from .models import Match, ShareLink
from .schemas import build_snapshot


class ShareConsumer(AsyncJsonWebsocketConsumer):
    """``ws/share/{token}``.

    Resolves the token to a match, joins group ``match_{id}``, and pushes the
    current snapshot. Permission comes from ``share_link.permission`` (not
    hardcoded): ``view`` ignores all client messages -- an open seam for a future
    ``edit`` permission without a protocol change. Server->client messages use a
    typed envelope ``{"type": "match.snapshot", "data": {...}}``.
    """

    async def connect(self):
        token = self.scope["url_route"]["kwargs"]["token"]
        link = await self._get_link(token)
        if link is None:
            await self.close(code=4404)
            return

        self.match_id = link.match_id
        self.permission = link.permission
        self.group = group_name(self.match_id)

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

        snapshot = await self._build_snapshot(self.match_id)
        if snapshot is not None:
            await self.send_json({"type": "match.snapshot", "data": snapshot})

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # Permission-driven, not hardcoded. Viewers cannot write anything.
        if self.permission == ShareLink.Permission.VIEW:
            return
        # Future: handle client edits for `edit` permission here.

    async def match_snapshot(self, event):
        """Channel-layer handler for ``match.snapshot`` group messages."""
        await self.send_json({"type": "match.snapshot", "data": event["data"]})

    @database_sync_to_async
    def _get_link(self, token):
        return (
            ShareLink.objects.select_related("match")
            .filter(token=token)
            .first()
        )

    @database_sync_to_async
    def _build_snapshot(self, match_id):
        match = Match.objects.filter(id=match_id).first()
        # Initial snapshot carries avatars (once per connection) so the viewer
        # does not depend on racing the initial REST fetch.
        return build_snapshot(match, include_avatars=True) if match else None
