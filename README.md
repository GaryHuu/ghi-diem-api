# ghi-diem-api

Django 5 + django-ninja + Channels backend for **Ghi Điểm Online**, a Vietnamese
card-game score tracker. REST for match/player/score CRUD (zero-sum enforced
server-side), plus a public read-only realtime share view over WebSocket.

## Stack

- Django 5, django-ninja (REST), Django Channels (WebSocket)
- Postgres + Redis channel layer (`channels-redis`)
- Ownership via `X-Device-Id` header (UUID, no accounts)

## Local development

### With Docker Compose (api + postgres + redis)

```bash
cp .env.example .env
docker compose up -d          # migrates then serves uvicorn on :8000
curl http://localhost:8000/api/docs   # ninja swagger UI
```

### Without Docker (sqlite, no Redis)

Leave `POSTGRES_HOST` unset so Django falls back to sqlite.

```bash
uv venv --python 3.12
uv pip install "django>=5.0,<5.2" "django-ninja>=1.3" "channels>=4.1" \
  "channels-redis>=4.2" "psycopg[binary]>=3.2" "django-cors-headers>=4.4" \
  "uvicorn[standard]>=0.30" pytest pytest-django pytest-asyncio
uv run python manage.py migrate
uv run uvicorn config.asgi:application --reload
```

## Tests

```bash
uv run pytest        # sqlite test DB + in-memory channel layer
```

## Key endpoints

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/matches` | list matches for the device |
| POST | `/api/matches` | create match (+players) |
| GET/DELETE | `/api/matches/{id}` | owner only |
| PUT | `/api/matches/{id}/scores` | `{playerId, gameIndex, value}`; returns full snapshot |
| POST | `/api/matches/{id}/next-game` \| `/end-game` | zero-sum enforced |
| POST | `/api/matches/{id}/players` | add player |
| PUT/DELETE | `/api/matches/{id}/players/{pid}` | update name/gap/avatar/order |
| POST | `/api/matches/{id}/players/{pid}/toggle-autofill` | autoFill side effects |
| POST | `/api/matches/{id}/share` | idempotent, returns `{token}` |
| GET | `/api/shared/{token}` | public read-model (no device auth) |
| WS | `/ws/share/{token}` | envelope `{"type":"match.snapshot","data":{...}}` |
## Production deploy (self-host)

Architecture: infra-level ingress (e.g. Cloudflare Tunnel, managed outside this repo) -> api on 127.0.0.1:8000 (uvicorn, N workers) -> postgres + redis. The FE lives on Vercel with `VITE_API_URL=https://api.ghidiem.online`.

1. On the server:

   ```bash
   git clone <repo> && cd ghi-diem-api
   cp .env.production.example .env
   # Fill in: DJANGO_SECRET_KEY, POSTGRES_PASSWORD, ADMIN_SEED_PASSWORD...
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```

2. Point your ingress at `http://localhost:8000` (the api is bound to loopback only).
3. Check: `curl https://<API_DOMAIN>/api/docs` returns 200.
4. On Vercel: set `VITE_API_URL=https://<API_DOMAIN>` and redeploy the FE (websocket becomes `wss://` automatically).

Notes:
- `DJANGO_ALLOWED_HOSTS` must also include the FE domain (the websocket layer validates the Origin header).
- `ADMIN_SEED_PASSWORD` must be set before the first `migrate` (the migration seeds the admin only once).
- Local dev is unchanged: plain `docker compose up` auto-loads `docker-compose.override.yml` (hot reload + source mount).
- Data backup: the `pgdata` volume (`docker compose exec db pg_dump -U ghidiem ghidiem > backup.sql`).
