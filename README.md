# Antiquary

A multi-user web app that generates short (~30-45s), vertical, fact-checked AI videos
about narrow, surprising true historical events, with an admin-gated signup flow and a
review desk for approving/rejecting each generated story before it's eligible for
publishing elsewhere.

Free stack throughout: Ollama (script writing + fact-check) + edge-tts (narration) +
Wikimedia Commons/Pexels (visuals) + faster-whisper (captions) + ffmpeg (render) +
Postgres (data) + MinIO (video storage) + Caddy (automatic HTTPS).

See **[CLAUDE.md](CLAUDE.md)** for full project context and the reasoning behind the
major decisions, **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the technical
layering, and **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** for shipping this to a real
self-hosted server.

## Local development

```bash
# Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in SECRET_KEY, DATABASE_URL, S3_*, ADMIN_EMAIL/PASSWORD
alembic upgrade head
flask --app wsgi seed-admin
python wsgi.py          # JSON API on :8787

# Frontend (separate terminal)
cd frontend
npm install
npm run dev              # :5173, proxies /api to :8787
```

Needs Postgres, MinIO, and Ollama reachable locally. `docker-compose.yml` defines all
three (plus the app itself and Caddy) for a one-command full-stack run:

```bash
docker compose up -d
```

The `app` container's startup applies migrations and seeds the admin account
automatically (`alembic upgrade head && flask seed-admin`) — both are idempotent, safe
to run on every start.

## Repository layout

```
app/          Flask JSON API (auth, admin, studio, generation)
frontend/     React SPA (Vite) — the entire UI
pipeline/     video generation, independent of the web app
migrations/   Alembic
docs/         architecture + deployment guides
```

## Status

Auth, admin approval, generation, review, and storage are built and working end-to-end
(verified live, not just written). Publishing generated videos to YouTube/Instagram is
**not** built yet — "Approved" currently just means eligible for that future step.
