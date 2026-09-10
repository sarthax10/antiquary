# history-shorts

Automated pipeline for short-form (9:16) history-story videos, posted to Instagram Reels and
YouTube Shorts. Free stack: n8n (orchestration) + Ollama (script writing) + edge-tts (narration)
+ Pexels (visuals) + faster-whisper (captions) + ffmpeg (render).

Starts with a human approval step before anything publishes; that step is designed to be
removable later once you trust the output quality.

## 1. Start the infra

With Docker:

```
docker compose up -d
docker exec -it history-shorts-ollama ollama pull llama3.1
```

Without Docker (e.g. no docker access — this is how it was set up during development):

```
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull llama3.2:3b   # or llama3.1 if your hardware handles it — bigger models hallucinate less

npm install n8n --prefix ~/n8n-install
~/n8n-install/node_modules/.bin/n8n start
```

n8n UI: http://localhost:5678

## 2. Install script dependencies (used by n8n's Execute Command nodes)

The `n8n` container doesn't have Python/ffmpeg preinstalled. Simplest free option: run the
`scripts/` locally (or in a sidecar container) rather than inside the n8n image itself.

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

ffmpeg must be on PATH (`sudo pacman -S ffmpeg` / `apt install ffmpeg` / `brew install ffmpeg`).

## 3. Fill in `.env`

Copy `.env.example` to `.env` and fill in what you have so far — Pexels key is the only one
you need to start generating videos locally. Telegram + YouTube + Instagram credentials are
only needed once you wire up the approval and publish steps.

## 4. Pipeline stages (each is a standalone CLI script for now)

One command runs the whole chain and drops the result in the review queue — this is also
what an n8n Execute Command node calls:

```
cd scripts && python run_pipeline.py "a specific historical topic"
```

Visuals are a crossfading Ken-Burns slideshow of images matched per-beat to the narration
(Wikimedia Commons — free, no key, and a much better fit for history content than generic
stock photos; falls back to Pexels if `PEXELS_API_KEY` is set, then to a plain gradient as a
last resort). Captions are word-level with the currently-spoken word highlighted, burned in
via a styled `.ass` file — not a plain sentence-at-a-time subtitle track.

Each stage is still a standalone script if you want to debug or re-run just one step:
`generate_script.py`, `fetch_visuals.py`, `tts.py`, `captions.py`, `render.py`,
`enqueue_for_review.py` — see each file's docstring for its CLI signature.

## 5. Review dashboard

```
python scripts/review_app.py
```

Open http://localhost:8787 — lists everything in `media/queue/`, plays the video, shows the
script/hook/narration and the fact-check claims (flagged claims are colored), with
Approve / Reject / Reset-to-pending buttons. This page only flips a `status` field in each
item's `meta.json` — it doesn't talk to n8n, YouTube, or Instagram itself.

## 6. Architecture: two decoupled n8n workflows (design, not yet built)

Rather than one long workflow with a mid-flight "wait for approval" pause, keep generation and
publishing as two independent, polling workflows against the shared `media/queue/` directory —
simpler to build and debug than n8n's wait-for-webhook-resume pattern:

- **Generate** (Cron, e.g. hourly): runs the CLI chain above end-to-end, ending in
  `enqueue_for_review.py`. New items land as `status: pending`.
- **Publish** (Cron, e.g. every 15 min): scans `media/queue/` for `status: approved` items not
  yet posted, uploads to YouTube (Data API v3) and Instagram (Graph API), then marks them
  `published`.

You (via the dashboard) are the only thing that moves an item from `pending` to `approved`. To
go fully unattended later, just skip the Approve step's meaning-of-truth and have Generate write
`status: approved` directly instead of `pending` — no workflow rewiring needed.

## 7. Not built yet

- The actual n8n workflow JSON for Generate and Publish above
- YouTube upload node (YouTube Data API v3, OAuth)
- Instagram publish node (Graph API — needs the video at a public URL first)

See the main conversation for architecture context and the reasoning behind each choice.
