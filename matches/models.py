import secrets

from django.db import models


def generate_token() -> str:
    """Unguessable share token (>= 24 bytes of entropy)."""
    return secrets.token_urlsafe(24)


class Match(models.Model):
    """A scoring match owned by a device.

    No ``current_game`` / ``total_games`` columns: the number of games is
    derived from ``len(player.scores)`` (single source of truth, mirroring the
    frontend ``getCurrentGameNumber``).
    """

    class Status(models.TextChoices):
        PLAYING = "playing"
        ENDED = "ended"

    name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PLAYING
    )
    device_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Soft delete: user-facing querysets exclude deleted matches; the admin
    # dashboard still sees them.
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"Match {self.id}: {self.name}"


class Player(models.Model):
    match = models.ForeignKey(
        Match, related_name="players", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=255)
    scores = models.JSONField(default=list)
    gap = models.IntegerField(null=True, blank=True)
    auto_fill = models.BooleanField(default=False)
    avatar = models.TextField(null=True, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"Player {self.id}: {self.name}"


class ShareLink(models.Model):
    """A share link for a match.

    FK (not OneToOne) + ``permission`` so a match can later have multiple links
    with different permissions (future share-edit direction). Current scope only
    creates/returns ``view`` links.
    """

    class Permission(models.TextChoices):
        VIEW = "view"

    match = models.ForeignKey(
        Match, related_name="share_links", on_delete=models.CASCADE
    )
    token = models.CharField(
        max_length=64, unique=True, db_index=True, default=generate_token
    )
    permission = models.CharField(
        max_length=16, choices=Permission.choices, default=Permission.VIEW
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"ShareLink {self.token} ({self.permission})"
