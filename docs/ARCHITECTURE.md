# Architecture

## Frontend/backend split: Flask is a JSON API, React is a separate SPA

Flask renders **no HTML**. Every `app/<feature>/routes.py` returns JSON. The UI is a
standalone React app (`frontend/`, Vite) that calls that API and owns all
presentation — this is the actual "segregation of frontend and backend," not just
moving Python-built HTML into template files.

- **Auth stays cookie-based, not JWT.** The React app is served same-origin (Caddy
  reverse-proxies both `/api/*` to Flask and everything else to the built React static
  files), so an HttpOnly session cookie (Flask-Login) is both simpler and more secure
  here than a JWT sitting in `localStorage` — HttpOnly cookies aren't readable by JS at
  all, so an XSS bug can't exfiltrate the session the way it could a `localStorage`
  token. `fetch(..., { credentials: 'include' })` on every API call.
- **CSRF for an API, not a form.** `Flask-WTF`'s CSRF check accepts a token via the
  `X-CSRFToken` header, not just a hidden form field. `GET /api/auth/csrf` hands the
  React app a token (itself set as a readable, non-HttpOnly cookie is the common
  double-submit pattern, but here it's returned in a JSON body from that endpoint on
  app load); every mutating request attaches it as a header.
- **Validation** happens in the route/service layer against the parsed JSON body —
  no `Flask-WTF` `FlaskForm` classes (those render server-side HTML forms, which this
  app no longer has). Plain validation functions in each feature's `service.py`.

## Layering (strict, one-way dependencies)

```
React components  →  API client  →  Flask routes (JSON in/out)  →  services  →  models  →  db / storage
```

- **Routes** (`app/<feature>/routes.py`): thin controllers. Parse the JSON request,
  call exactly one service function, return `jsonify(...)`. A route file should never
  import a model or issue a query directly — if a route needs data, that's a service's
  job.
- **Services** (`app/<feature>/service.py`): the actual business logic — pure functions
  operating on models and the DB session. This is what's independently testable and
  reusable (the CLI seed-admin command and the web routes both call `auth.service`
  functions rather than duplicating logic).
- **Models** (`app/models/`): ORM schema only. A computed property is fine (e.g.
  `Story.claim_counts`); business rules and queries are not — those belong in a service.
- **`pipeline/`** is deliberately outside `app/` and never imports from
  `app.auth`/`app.admin`/`app.studio`/any routes module. It's a standalone worker (run
  as a subprocess, not part of the request/response cycle) that writes to the same
  Postgres/MinIO via `app.models`/`app.db`/`app.storage`, and reports real progress via
  `app.generation.job_manager.set_stage()` — that module is the one sanctioned bridge,
  since it needs no Flask app/request context (see its docstring), only a DB session.

## Ownership model (explicit, not just implied by the UI)

Every `Story` belongs to exactly one user (`created_by_id`, `NOT NULL`, indexed). A
non-admin can only read/stream/decide/restore/cancel-generation-of their own stories;
`app/studio/service.py`'s `_scoped()` helper (and `get_story()`'s inline check) enforce
this on every query, not just the list views. An admin bypasses the check entirely —
this is deliberate oversight, the same trust boundary that already lets admins approve
signups — not an oversight-shaped bug. MinIO object keys are namespaced the same way:
`stories/<user_id>/<story_id>/video.mp4`.

Generation is a small FIFO queue (`app/generation/job_manager.py`), not "one job
globally or an instant rejection": a second `start()` while one is running enqueues
(`status="queued"`), and `get_status()` — already polled by the frontend every 2.5s —
opportunistically promotes the oldest queued job once nothing is running. A DB-level
partial unique index (`generation_jobs` where `status='running'`) backs the "one running
job" invariant regardless of process/thread races; gunicorn itself runs a single worker
(with threads) so that invariant and Flask-Limiter's rate-limit store are both correct
without needing Redis.

## Timeline (editor data model)

`Story.timeline` (JSONB, added in migration `570ffe36b382`, built by `pipeline/
timeline.py`) is the foundation for the upcoming timeline editor — a structured,
addressable representation of a story's edit, not just a final rendered MP4:

```json
{
  "version": 1,
  "duration": 42.3,
  "tracks": {
    "visual":    [{"id","kind":"video"|"image","start","duration","entity_type","visual_query","face","source","object_key"}],
    "narration": [{"id","start","duration","text","object_key"}],
    "captions":  [{"id","text","start","end","emphasis","words":[{"word","start","end"}]}],
    "music":     {"volume"} | null
  },
  "style": {"caption_font","caption_uppercase","voice"}
}
```

One clip/cue per beat, in the same order `pipeline/generate_script.py`'s beats and
`pipeline/tts.py`'s per-beat audio already produce — this generalizes what the
auto-pipeline does today rather than replacing it. The primary auto-generation path
(`pipeline/render.py` via `run_pipeline.py`) still consumes beats/audio/captions
directly, so that path's output is byte-for-byte unaffected by any of this.

Each visual/narration entry's `object_key` points at that beat's own clip, durably
uploaded to MinIO under `stories/<user_id>/<story_id>/clips/{visual,audio}_<NN>.<ext>` by
`pipeline/enqueue_story.py._upload_clip_assets()` right after the Story row (and thus its
id) exists — a temp-file-only clip can't survive `run_pipeline.py`'s own cleanup, so this
is the only chance to keep it. `pipeline/render_timeline.py` downloads exactly these
objects, rebuilds the narration track and a karaoke `.ass` from the caption track's own
stored per-word timestamps (`captions.build_ass_from_track()` — not re-transcribed), and
calls the same `render.render()` the auto-pipeline uses — so re-rendering an edited
timeline shares one ffmpeg filter-graph implementation with the original generation.
Nothing calls `render_timeline.py` yet outside manual/test use (`python
render_timeline.py <story_id>`) — no editor route exists to trigger it. Stories rendered
before this landed have entries with no `object_key`; `render_from_timeline()` raises
rather than silently producing a broken video for those.

The plan (not yet built): a timeline editor UI reading/writing this JSON, wired to an
actual "save + re-render" route that calls `render_timeline.render_story()`, and
AI-assisted edits (single operations, then natural-language chat) that patch this
structure instead of regenerating the whole video.

## Package layout

```
app/                        Flask JSON API — no templates/, no static/
  __init__.py                create_app() factory — the only place extensions/blueprints
                              get wired to a concrete app instance
  config.py                  Config classes, env-var driven, no secrets hardcoded
  extensions.py               login_manager / csrf / limiter (uninitialized until init_app)
  db.py                      plain SQLAlchemy engine + scoped_session (not Flask-SQLAlchemy
                              — see its docstring: routes, a background thread, and a
                              separate OS subprocess all need DB access, and only one of
                              those three has a Flask app context)
  cli.py                     `flask seed-admin` (schema itself comes from `alembic upgrade head`)

  models/                    ORM layer, zero Flask imports except UserMixin
  auth/                      signup / login / logout / csrf, decorators, validation
  admin/                     user-approval endpoints (admin-only blueprint)
  studio/                    the actual product — create / review / library / archive
  generation/                job_manager.py: spawns + monitors the pipeline subprocess,
                              persists progress to GenerationJob rows
  storage.py                 MinIO/S3 client wrapper

frontend/                    React SPA (Vite), the entire UI — talks to app/ only via fetch
  src/
    api/                     one module per backend feature, thin fetch wrappers
    pages/                   Login, Signup, Pending, AdminUsers, Create, Review, Library,
                              Archive, StoryDetail
    components/              AppShell (sidebar / top bar / tab bar), CommandMenu, StoryPoster,
                              VideoFrame, FactCheck, StoryDossier, StoryCollection, ui.jsx
                              (Button, fields, Dialog, Stamp, EmptyState, ...), icons.jsx
    *Context.jsx             Auth, Counts (story lists + nav counts), Generation (global job
                              status + polling), Toast (undoable confirmations)
    lib/                     format helpers, hooks (hotkeys, in-view, title), view transitions
    styles/                  tokens.css → base → components → shell → pages; the design system
                              is documented in UI_UX_REDESIGN_REVIEW.md
  e2e/                       optional mock API + Playwright smoke flows (not part of the build)

pipeline/                    video generation, independent of the web app
  generate_script.py          Ollama writer + fact-check passes; splits narration into
                               ordered "beats" ({text, visual_query, entity_type}) that
                               fetch_visuals.py, tts.py and render.py all key off
  fetch_visuals.py             one asset per beat — a named person's actual portrait
                               (Wikidata P18) before any generic stock fallback
  tts.py                       one narration clip per beat (exact per-beat duration,
                               no approximation), concatenated for the full track
  captions.py                  word-level karaoke captions (kinetic pop-in per word,
                               one of a few real installed fonts per video — see
                               pipeline/assets/fonts/), burned in via .ass/libass
  render.py                    per-beat cut timing, face-aware Ken Burns, grade/grain,
                               optional ducked music bed (pipeline/assets/music/)
  timeline.py                  builds Story.timeline — the editable project
                               representation (visual/narration/caption/music tracks)
                               the upcoming timeline editor reads/writes
  enqueue_story.py             creates the Story row, uploads the final video, and
                               (_upload_clip_assets) durably uploads each beat's own
                               visual/audio clip to MinIO, recording object_key on the
                               matching timeline entries
  render_timeline.py           renders *from* a Story.timeline's durable per-clip
                               assets + caption track — what a future editor's
                               "save + re-render" action will call; not wired to any
                               route yet. run_pipeline.py's own render still goes
                               straight through render.py, unaffected.
migrations/                  Alembic
docs/                        this file, DEPLOYMENT.md, SERVER_SETUP.md
tests/                        pytest — ownership scoping, the generation queue, and the
                               beat-grouping math; runs against the real DATABASE_URL
                               (see tests/conftest.py), no separate test-DB infra
wsgi.py                      gunicorn entrypoint: `from app import create_app; app = create_app()`
```

## Conventions

- **No secrets in code.** Every credential/URL comes from an environment variable, read
  once in `app/config.py`. `.env.example` documents every var; `.env` itself is
  git-ignored.
- **Flask returns JSON, never HTML.** If a route is building a string of markup, that's
  a bug — it belongs in a React component instead.
- **Routes don't query the DB.** If you're tempted to write `session.query(...)` inside
  a `routes.py`, that logic belongs in `service.py` instead.
- **One migration per schema change**, via Alembic (`alembic revision --autogenerate`),
  never hand-edited table changes against a running database.
- **The API client is the only thing in `frontend/` that calls `fetch`.** Page/component
  code calls a function from `frontend/src/api/`, never a raw `fetch()` — keeps the
  CSRF-header/credentials boilerplate in one place.

## What's deliberately simple (not over-engineered)

- No custom exception hierarchy — services call `flask.abort()` for expected failure
  cases (not found, forbidden) rather than raising domain exceptions the route layer
  would just translate right back to the same HTTP codes. Revisit only if this app
  grows a non-HTTP consumer of these services.
- No repository/DAO abstraction over SQLAlchemy — the ORM session already is that
  abstraction; adding another layer on top of it for an app this size would be
  indirection without payoff.
