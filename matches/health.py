"""Public health check: app + Postgres + Redis.

Called from outside (GitHub Actions schedule) through the Cloudflare Tunnel,
so a 200 here means the full user path works. Checks are deliberately cheap
(SELECT 1 + PING with short timeouts) and never raise.
"""
import redis
from django.conf import settings
from django.db import connection


def check_db() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except Exception:
        return False


def check_redis() -> bool:
    try:
        with redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2
        ) as client:
            return bool(client.ping())
    except Exception:
        return False
