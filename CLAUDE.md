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
- `pipeline/` — the actual video generation (Ollama script writing + fact-check →
  Wikimedia/Pexels visuals → edge-tts narration → faster-whisper captions → ffmpeg
  render). Fully independent of Flask; only needs `DATABASE_URL`/`S3_*` env vars.
  `run_pipeline.py` is spawned as a subprocess by `app/generation/job_manager.py`.
- Data lives in **Postgres** (`app/models/`: `User`, `Story`, `GenerationJob`) and
  **MinIO** (S3-compatible; rendered videos). Nothing is stored as loose JSON files
  anymore — that was the pre-multi-user design and has been fully migrated away from.

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
- **One generation globally at a time.** Concurrent Ollama requests on this CPU-bound
  single-instance setup were the direct, confirmed cause of real failures earlier in
  this project (truncated/malformed output). `job_manager.start()` refuses a second job
  while one is running. If you ever add a real job queue for concurrency, keep this
  constraint until you've verified the underlying Ollama contention issue is actually
  solved (e.g. multiple model instances, more RAM/CPU).
- **Cookie session auth, not JWT**, because the SPA is served same-origin (Caddy proxies
  both `/api/*` and the built frontend) — an HttpOnly cookie can't be read by JS at all,
  which is strictly safer against XSS than a token sitting in `localStorage`.
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
- Rate limiting (`Flask-Limiter`) uses in-memory storage — fine for the current
  single-`app`-container deployment, but won't share state if you ever scale to
  multiple app instances. Would need a Redis backend at that point.
- Publish-to-YouTube: **working, verified against a real account and a real upload** —
  not just plumbing that looked right. `app/social/` (per-user OAuth connect/disconnect,
  Settings > Connections in the UI) + `app/publishing/` (`Publication` row per
  story+platform attempt, background thread, Publish button in Library) both exist and
  were exercised end-to-end for real: connected a live YouTube channel, clicked Publish
  on an approved story, confirmed the video actually live on youtube.com.
  Uploads are **public** — Antiquary's own human review step (app/studio/) is the real
  gate; there's no second, silent platform-level privacy gate behind it.
  Publish is NOT globally serialized like generation is — that constraint is
  Ollama-CPU-specific (see below) and doesn't apply to an HTTP upload; it's only guarded
  per (story, platform) so the same story can't be double-uploaded to the same platform
  from two clicks. That guard, and orphaned-job detection, is staleness-based off
  `Publication.updated_at` — NOT in-memory state — because gunicorn runs multiple worker
  *processes* (`--workers 2`); a first version tracked in-flight jobs in a Python-level
  set and it was wrong in production (a status-poll request landing on a different
  worker than the one running the upload saw no record of the job and wrongly marked a
  succeeding upload as "interrupted"). If you touch this concurrency logic again, keep
  the source of truth in the database, not in a worker-local variable.
  Instagram's connect flow and publish job are still unbuilt (needs Meta App Review —
  see CLAUDE.md's original plan discussion). Performance-metrics/insights dashboard is a
  separate, later phase — nothing here polls view/like counts yet.
- No automated test suite exists yet. Verification so far has been manual/live
  (curl'ing the API, driving the React app in a real browser) — thorough, but not
  regression-proof. Worth adding `tests/` mirroring `app/`'s structure if this keeps
  growing.

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

## Where to look next

- `docs/ARCHITECTURE.md` — layering rules, package-by-package breakdown, conventions.
- `docs/DEPLOYMENT.md` — exact steps to get this running on a real Ubuntu server
  (domain, port-forwarding, GitHub Actions self-hosted runner, first `.env`).
- `docs/SERVER_SETUP.md` — the detailed, self-contained walkthrough of the same
  process, meant to be handed to a Claude Code session running on the server itself
  (or followed by hand step-by-step), starting from a bare Ubuntu Server install.
