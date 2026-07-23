"""Seed the single admin user (idempotent, one-way hashed).

Creates ``User(username="admin")`` with the password from the
``ADMIN_SEED_PASSWORD`` env var (default ``"1"`` for local dev) hashed via
Django's password hasher. Uses ``get_or_create`` so running ``migrate`` twice
never fails or duplicates. Plaintext is never stored.
"""
import os

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations


def seed_admin(apps, schema_editor):
    User = apps.get_model("auth", "User")
    User.objects.get_or_create(
        username="admin",
        defaults={
            "password": make_password(os.environ.get("ADMIN_SEED_PASSWORD", "1")),
            "is_staff": True,
        },
    )


def unseed_admin(apps, schema_editor):
    """Reverse: no-op (leave data intact)."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("matches", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(seed_admin, unseed_admin),
    ]
