# Antiquary — project context

This file exists so a Claude Code session on a different machine, with no memory of
this project's history, can pick up development immediately. Read this, then
`docs/ARCHITECTURE.md` for the technical layering, then `docs/DEPLOYMENT.md` if the
task is about shipping to the server.

## What this is

Antiquary generates short (~30-45s), vertical (9:16), fact-checked AI videos about
narrow, surprising true historical events, and gives a human a review desk to
approve/reject each one before it's eligible for publishing (publishing itself —
actually posting to YouTube/Instagram — is not built yet; "approved" just means
eligible for a future publish workflow to pick up).

It's now a multi-user web app: people sign up, an admin approves each request, and only
approved users can generate/review stories.

## Why Ollama, not the Claude API or a Claude subscription

Early in this project the user asked about using "headless Claude" (the Claude
subscription, scripted) to avoid paying for API usage. That's not just a cost
question — using a Claude.ai/Claude Code **consumer subscription** to power an
unattended backend service is outside Anthropic's Consumer Terms/Usage Policy (that
license is for individual interactive/personal use, not for building another automated
product on top of it). The Claude **API** would be a legitimate paid alternative but
the user wanted zero ongoing cost, so the whole pipeline runs on **local Ollama**
(`llama3.2:3b` by default) instead — free, but noticeably more prone to hallucination
than a frontier model, which is precisely why the fact-check pass exists (see below).
This project has no dependency on Anthropic/Claude at runtime at all.

## Architecture (see docs/ARCHITECTURE.md for the full layering rules)

- `app/` — Flask, **JSON API only**, no HTML rendering. Blueprints: `auth`, `admin`,
  `studio`. Plain SQLAlchemy (not Flask-SQLAlchemy) via `app/db.py` — deliberately, so
  the same DB access code works from a Flask request, a background thread, and a
  separate OS subprocess without juggling Flask app-context rules.
- `frontend/` — React (Vite), the entire UI. Talks to `app/` only via
  `frontend/src/api/*` fetch wrappers. Cookie-based session auth (Flask-Login), CSRF via
  an `X-CSRFToken` header fetched from `/api/auth/csrf`.
- `pipeline/` — the actual video generation (Ollama script writing + fact-check, split
  into ordered "beats" → Wikidata/Wikimedia/Pexels visuals per beat → edge-tts narration
  per beat → faster-whisper captions → ffmpeg render). Fully independent of Flask; only
  needs `DATABASE_URL`/`S3_*` env vars. `run_pipeline.py` is spawned as a subprocess by
  `app/generation/job_manager.py`. See docs/ARCHITECTURE.md for how beats tie sourcing,
  narration timing and render cuts together.
- Data lives in **Postgres** (`app/models/`: `User`, `Story`, `GenerationJob`) and
  **MinIO** (S3-compatible; rendered videos, namespaced per user —
  `stories/<user_id>/<story_id>/video.mp4`). Nothing is stored as loose JSON files
  anymore — that was the pre-multi-user design and has been fully migrated away from.
  Every `Story` belongs to exactly one user (`created_by_id`); non-admins only see and
  can act on their own, admins see/act on everyone's — see docs/ARCHITECTURE.md's
  "Ownership model" for the enforcement details.

## Key decisions and their reasoning (don't relitigate these without a real reason)

- **Real staged generation progress, never simulated.** `job_manager.set_stage()` is
  called by the pipeline subprocess itself at each genuine step. A fake timer-based
  progress bar was explicitly rejected as dishonest UI.
- **No fake "advanced settings"** on the Create screen (voice/pacing/style/etc.) — the
  pipeline doesn't actually support any of these yet. Shipping non-functional controls
  that look real was explicitly rejected; there's an honest "coming soon" note instead.
  If you wire up a real setting, move it out of that note and into an actual control.
- **No click-to-highlight linking between fact-check claims and narration text.** Claims
  are LLM-paraphrased, not verbatim substrings of the narration — a highlight-matching
  feature here would be unreliable/misleading, not just unfinished.
- **One generation subprocess at a time, but a real FIFO queue now, not a rejection.**
  Concurrent Ollama requests on this CPU-bound single-instance setup were the direct,
  confirmed cause of real failures earlier in this project (truncated/malformed output),
  so that constraint stays — but `job_manager.start()` now enqueues a second request
  (`status="queued"`) instead of erroring, and `get_status()` promotes the oldest queued
  job once nothing is running. Don't relax the one-subprocess-at-a-time part until
  you've verified the underlying Ollama contention issue is actually solved (e.g.
  multiple model instances, more RAM/CPU).
- **Cookie session auth, not JWT**, because the SPA is served same-origin (Caddy proxies
  both `/api/*` and the built frontend) — an HttpOnly cookie can't be read by JS at all,
  which is strictly safer against XSS than a token sitting in `localStorage`.
- **`ADMIN_EMAIL`/`ADMIN_PASSWORD` are bootstrap-only.** `seed-admin` uses them once to
  create the first admin row; after that the DB is the only source of truth, same as any
  other user — `POST /api/auth/change-password` (self-service) and
  `POST /api/admin/users/<id>/reset-password` (admin-initiated, for a member who's lost
  access) are the real way to change a password from then on. Don't reintroduce
  "edit `.env` to change a password" anywhere — that was the actual bug this fixed, not
  a deliberate design choice worth preserving.
- **Fact-checking is a second, independent LLM pass, not a web search.** It catches
  internal inconsistencies and claims the model itself is unsure about, but a small
  local model can and does confidently confirm its own hallucinations sometimes. Treat
  `needs_human_review: false` / a "verified" verdict as "nothing flagged itself," never
  as ground truth — the human review step is load-bearing, not a formality.
- **MinIO/Postgres/Caddy/DuckDNS** were chosen specifically to keep the whole stack free
  for self-hosting (the user's hard constraint throughout this project), while still
  being genuinely production-shaped (real object storage, real RDBMS, real automatic
  TLS) rather than toy substitutes.

## Known gaps / honest limitations (don't claim these are done)

- No email verification on signup — admin approval is the only gate. Fine for the
  current trust model; revisit if that changes.
- Rate limiting (`Flask-Limiter`) uses in-memory storage, which only stays correct
  because gunicorn runs a single worker process (`docker-compose.yml`, `--workers 1
  --worker-class gthread --threads 4`) — the same fix that makes `job_manager`'s
  in-process lock actually span every request. If you ever need multiple worker
  *processes* (not threads) for real request-handling concurrency, both of these need a
  shared backend (Redis for the limiter; the DB-level partial unique index already
  backs the job invariant independently of the in-process lock) — don't just bump
  `--workers` without addressing that.
- No publish-to-YouTube/Instagram step yet — "Approved" stops at making a story
  eligible; nothing in this repo actually posts anywhere.
- `tests/` covers the security-critical/new logic (ownership scoping, the generation
  queue, the beat-grouping math) — not a full retrofit of everything else. It runs
  against the real `DATABASE_URL` (see `tests/conftest.py`), not a separate test DB.

## Local dev setup

```bash
# Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in SECRET_KEY, DATABASE_URL, S3_*, ADMIN_EMAIL/PASSWORD
alembic upgrade head
flask --app wsgi seed-admin
flask --app wsgi ensure-bucket
python wsgi.py          # serves the API on :8787

# Frontend (separate terminal)
cd frontend
npm install
npm run dev              # serves on :5173, proxies /api to :8787
```

Needs Postgres and MinIO reachable locally (see `docker-compose.yml` for the real
service definitions, or run them natively — whatever's convenient for your machine).

## Frontend design system

The UI follows the "screening room" design system documented in
`UI_UX_REDESIGN_REVIEW.md` (tokens in `frontend/src/styles/tokens.css`). Key rules: one
signal colour (tungsten) that always means "needs a human eye"; reversible actions confirm
with an Undo toast rather than a blocking dialog, and only actions that affect another
person (suspending/revoking a member) or discard in-progress work (stopping a generation)
use `ConfirmDialog`; single-key shortcuts go through `useHotkeys` (which ignores modifier
chords, typing and open dialogs); fact-check "verified" is shown as "nothing flagged".
No new npm dependencies were added — keep it that way unless one clearly pays for itself.

## Where to look next

- `docs/ARCHITECTURE.md` — layering rules, package-by-package breakdown, conventions.
- `docs/DEPLOYMENT.md` — exact steps to get this running on a real Ubuntu server
  (domain, port-forwarding, GitHub Actions self-hosted runner, first `.env`).
- `docs/SERVER_SETUP.md` — the detailed, self-contained walkthrough of the same
  process, meant to be handed to a Claude Code session running on the server itself
  (or followed by hand step-by-step), starting from a bare Ubuntu Server install.
