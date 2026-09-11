# Frontend smoke tests (optional)

Not part of the build or the deploy. These exist because the app has no automated
test suite yet (see CLAUDE.md) and the redesign changed every screen.

- `mock-server.mjs` — a dependency-free Node server that serves `frontend/dist` and
  mocks every `/api/*` route with the same response shapes as the Flask API, including
  a generation job that walks through the six real stage keys.
- `flows.mjs` — Playwright script that drives the main journeys (sign in with redirect
  back, review with keyboard + undo, modifier chords not triggering decisions, archive
  search + restore, command menu, story detail, create → stop → complete, members
  approve/suspend confirm, sign up, mobile decision bar, no horizontal overflow).

```bash
cd frontend
npm run build
node e2e/mock-server.mjs &                 # http://localhost:5199
npx -p playwright node e2e/flows.mjs       # prints PASS/FAIL per step
```

Sign in to the mock with `admin@antiquary.test` / `correct-horse-battery` (mock-only
credentials). Env vars: `PORT`, `LATENCY` (ms), `EMPTY=1` (no stories),
`JOB=running|error` (start with a generation in that state), `STAGE_MS`, and
`VIDEOS=/dir/with/v0.mp4..v3.mp4` for sample footage (without it, posters show the
"no video" fallback).
