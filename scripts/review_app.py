#!/usr/bin/env python3
"""Local review dashboard for the history-shorts pipeline.

Run: python scripts/review_app.py
Open: http://localhost:8787

Lists everything in media/queue/, lets you watch each rendered video and see
its script + fact-check flags, and Approve / Reject / reset it. Approved items
are what a separate n8n "publish" workflow should pick up and post; nothing
here talks to YouTube/Instagram directly.

Design: dark canvas throughout (card and page share one dark surface, video
never sits in a jarring black-box-on-white-card seam) — matches the
convention real video-review tools (Frame.io, Premiere, DaVinci Resolve,
YouTube Studio's player) use, rather than a generic light admin-panel look.
Palette is custom-tuned (not stock Tailwind swatches) with one accent hue
(warm bronze) reserved for brand identity and the "needs review" flag only,
so color keeps a 1:1 mapping to meaning.
"""
import html
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, redirect, request, send_from_directory, url_for

import generation_job

BASE_DIR = Path(__file__).resolve().parent.parent
QUEUE_DIR = BASE_DIR / "media" / "queue"

load_dotenv(BASE_DIR / ".env")  # so the subprocess generation_job spawns inherits PEXELS_API_KEY etc.

app = Flask(__name__)


def load_items():
    items = []
    if not QUEUE_DIR.exists():
        return items
    for item_dir in QUEUE_DIR.iterdir():
        meta_path = item_dir / "meta.json"
        script_path = item_dir / "script.json"
        if not meta_path.exists() or not script_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        script = json.loads(script_path.read_text())
        items.append({"meta": meta, "script": script})
    items.sort(key=lambda it: it["meta"]["created_at"], reverse=True)
    return items


def esc(text) -> str:
    return html.escape(str(text), quote=True)


# Minimal inline icon set (Heroicons-outline style, 1.5-2px stroke) — no icon font/CDN needed.
ICON_CHECK = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10.5l4 4 8-9"/></svg>'
ICON_X = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 5l10 10M15 5L5 15"/></svg>'
ICON_UNDO = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8a6 6 0 1 1 1.05 6.4M4 8V4M4 8h4"/></svg>'
ICON_FLAG = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 3v14M5 4h9l-2 3 2 3H5"/></svg>'
ICON_PLAY = '<svg viewBox="0 0 20 20" fill="currentColor"><path d="M6.5 4.8c0-.9 1-1.5 1.8-1l8 5.2c.8.5.8 1.5 0 2l-8 5.2c-.8.5-1.8-.1-1.8-1V4.8z"/></svg>'
# Brand mark: a viewfinder frame (the act of reviewing footage) around a play triangle —
# a play-icon-in-a-square is a generic video-app pattern on its own; the corner brackets
# tie it specifically to "reviewing/framing footage" rather than just "video."
ICON_MARK = (
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">'
    '<path d="M2 6.5V2h4.5M18 6.5V2h-4.5M2 13.5V18h4.5M18 13.5V18h-4.5"/>'
    '<path d="M8 7.1v5.8a.75.75 0 0 0 1.14.64l4.8-2.9a.75.75 0 0 0 0-1.28l-4.8-2.9A.75.75 0 0 0 8 7.1Z" fill="currentColor" stroke="none"/>'
    "</svg>"
)

VERDICT_STYLE = {
    "verified": ("var(--success-text)", "Verified"),
    "uncertain": ("var(--warning-text)", "Uncertain"),
    "false": ("var(--destructive-text)", "False"),
}

CONFIDENCE_STYLE = {
    "high": "var(--success-text)",
    "medium": "var(--warning-text)",
    "low": "var(--destructive-text)",
}


def render_claim(c: dict) -> str:
    verdict = c.get("verdict", "?")
    color, label = VERDICT_STYLE.get(verdict, ("var(--ink-muted)", str(verdict).title()))
    return f"""
    <li class="claim">
      <span class="claim-dot" style="background:{color}"></span>
      <div class="claim-body">
        <p class="claim-text"><span class="claim-verdict" style="color:{color}">{label}.</span> {esc(c.get('claim', ''))}</p>
        <p class="claim-note">{esc(c.get('note', ''))}</p>
      </div>
    </li>"""


STATUS_STYLE = {
    "pending": ("var(--pending-text)", "Pending"),
    "approved": ("var(--success-text)", "Approved"),
    "rejected": ("var(--destructive-text)", "Rejected"),
}

ACTION_TARGET_STATUS = {"approve": "approved", "reject": "rejected", "pending": "pending"}


def render_item(item) -> str:
    meta = item["meta"]
    script = item["script"]
    item_id = meta["id"]
    status = meta.get("status", "pending")
    status_color, status_label = STATUS_STYLE.get(status, ("var(--ink-muted)", status.title()))

    fact_check = script.get("fact_check", {})
    claims = fact_check.get("claims", [])
    claims_html = "".join(render_claim(c) for c in claims) or "<li class='claim-empty'>No claims extracted.</li>"

    needs_review = script.get("needs_human_review")
    flag_html = (
        f'<span class="flag-badge">{ICON_FLAG}Needs review</span>' if needs_review else ""
    )

    actions = "".join(
        f'<form method="post" action="/decide/{item_id}">'
        f'<input type="hidden" name="action" value="{action}">'
        f'<button type="submit" class="btn btn-{cls}{" btn-current" if is_current else ""}"'
        f'{" disabled" if is_current else ""}>{icon}{"Current" if is_current else label}</button></form>'
        for action, cls, label, icon, is_current in (
            (a, c, l, i, ACTION_TARGET_STATUS[a] == status)
            for a, c, l, i in [
                ("approve", "primary", "Approve", ICON_CHECK),
                ("reject", "danger", "Reject", ICON_X),
                ("pending", "ghost", "Reset", ICON_UNDO),
            ]
        )
    )

    created = time.strftime("%b %d, %H:%M", time.localtime(meta["created_at"]))
    n_claims = len(claims)
    confidence = fact_check.get("overall_confidence", "?")
    confidence_color = CONFIDENCE_STYLE.get(confidence, "var(--ink)")

    return f"""
    <article class="card">
      <div class="card-toolbar">
        <span class="status-tag"><span class="status-dot" style="background:{status_color}"></span><span style="color:{status_color}">{status_label}</span></span>
        {flag_html}
        <span class="mono card-id">#{esc(item_id)} &middot; {created}</span>
      </div>
      <div class="card-media">
        <video controls preload="metadata" src="/media/{item_id}/video.mp4"></video>
      </div>
      <div class="card-body">
        <h2 class="card-title">{esc(script.get('title', '(untitled)'))}</h2>
        <p class="card-hook">&ldquo;{esc(script.get('hook', ''))}&rdquo;</p>
        <p class="card-narration">{esc(script.get('narration', ''))}</p>
        <details class="factcheck">
          <summary>Fact-check &mdash; {n_claims} claim{'s' if n_claims != 1 else ''} &middot; confidence: <strong style="color:{confidence_color}">{esc(confidence)}</strong></summary>
          <ul class="claim-list">{claims_html}</ul>
        </details>
        <div class="actions">{actions}</div>
      </div>
    </article>"""


FAVICON = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20'%3E"
    "%3Crect width='20' height='20' rx='5' fill='%23C9A15A'/%3E"
    "%3Cpath d='M7.5 5.3c0-.9 1-1.5 1.8-1l6 3.7c.8.5.8 1.5 0 2l-6 3.7c-.8.5-1.8-.1-1.8-1V5.3z' fill='%230B1120'/%3E"
    "%3C/svg%3E"
)

PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>History Shorts — Review Desk</title>
<link rel="icon" href="__FAVICON__">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0B1120;
  --card: #151C2C;
  --card-raised: #1B2438;
  --border: rgba(255,255,255,0.08);
  --ink: #F8FAFC;
  --ink-muted: #9CA6B4;
  --ink-body: #CFD5DC;
  --accent: #C9A15A;
  --accent-text: #E0B368;
  --on-accent: #0B1120;
  --success-fill: #14804A;
  --success-text: #3ED98C;
  --on-success: #FFFFFF;
  --warning-text: #E8A33D;
  --pending-text: #6E9CF2;
  --destructive-fill: #C13B30;
  --destructive-text: #F0716A;
  --on-destructive: #FFFFFF;
  --radius: 16px;
  --radius-sm: 10px;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: 'Inter', system-ui, sans-serif;
  padding: 28px clamp(16px, 4vw, 48px) 80px;
  -webkit-font-smoothing: antialiased;
}
.mono { font-family: 'JetBrains Mono', monospace; letter-spacing: 0.01em; }

header.site {
  max-width: 1320px;
  margin: 0 auto 26px;
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  align-items: center;
  justify-content: space-between;
}
.brand { display: flex; align-items: center; gap: 13px; }
.brand-mark {
  width: 38px; height: 38px;
  background: var(--accent);
  color: var(--on-accent);
  display: flex; align-items: center; justify-content: center;
  border-radius: 9px;
  flex-shrink: 0;
}
.brand-mark svg { width: 22px; height: 22px; }
.brand h1 { font-size: 16px; font-weight: 700; letter-spacing: -0.01em; margin: 0; }
.brand .tagline { margin: 1px 0 0; font-size: 12.5px; color: var(--ink-muted); }

.stat-row { display: flex; gap: 9px; flex-wrap: wrap; }
.stat-pill {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 6px 15px 6px 12px;
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: background 150ms ease, border-color 150ms ease;
}
.stat-pill:hover { background: var(--card-raised); }
.stat-pill.active { background: var(--card-raised); border-color: var(--ink-muted); }
.stat-pill .dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.stat-pill .num { font-variant-numeric: tabular-nums; color: var(--ink); }
.stat-pill .label { color: var(--ink-muted); font-weight: 500; }
.stat-pill.active .label { color: var(--ink); }

.note { max-width: 1320px; margin: 0 auto 24px; font-size: 12.5px; color: var(--ink-muted); }

.grid {
  max-width: 1320px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(430px, 100%), 1fr));
  gap: 20px;
}

.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.card-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
  padding: 11px 14px;
  border-bottom: 1px solid var(--border);
}
.status-tag { display: flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.flag-badge {
  display: flex; align-items: center; gap: 5px;
  color: var(--accent-text); font-size: 12px; font-weight: 600;
}
.flag-badge svg { width: 12px; height: 12px; }
.card-id { margin-left: auto; font-size: 11px; color: var(--ink-muted); white-space: nowrap; }

.card-media { background: var(--card); display: flex; justify-content: center; }
.card-media video {
  width: auto;
  height: min(520px, 70vh);
  aspect-ratio: 9 / 16;
  max-width: 100%;
  display: block;
  background: #000;
  object-fit: contain;
}

.card-body { padding: 18px 20px 20px; display: flex; flex-direction: column; gap: 9px; flex: 1; }
.card-title { font-size: 16.5px; font-weight: 700; letter-spacing: -0.01em; margin: 0; }
.card-hook { font-style: italic; color: var(--ink-muted); margin: 0; font-size: 13.5px; }
.card-narration { font-size: 13.5px; line-height: 1.6; margin: 0; color: var(--ink-body); }

details.factcheck { border-top: 1px solid var(--border); padding-top: 10px; margin-top: 2px; }
details.factcheck summary {
  cursor: pointer;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-muted);
  list-style: none;
}
details.factcheck summary::-webkit-details-marker { display: none; }
details.factcheck summary strong { font-weight: 700; }
.claim-list { list-style: none; margin: 12px 0 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.claim { display: flex; gap: 9px; align-items: flex-start; }
.claim-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; margin-top: 6px; }
.claim-text { margin: 0; font-size: 12.5px; line-height: 1.5; color: var(--ink-body); }
.claim-verdict { font-weight: 700; }
.claim-note { margin: 2px 0 0; font-size: 12px; color: var(--ink-muted); }
.claim-empty { font-size: 12.5px; color: var(--ink-muted); }

.actions { display: flex; gap: 8px; margin-top: auto; padding-top: 8px; }
.card-body form { margin: 0; flex: 1; display: flex; }
.btn {
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-family: 'Inter', sans-serif;
  font-weight: 600;
  font-size: 13px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  padding: 9px 12px;
  cursor: pointer;
  transition: background 150ms ease, border-color 150ms ease, opacity 150ms ease;
}
.btn svg { width: 15px; height: 15px; flex-shrink: 0; }
.btn-primary { background: var(--success-fill); color: var(--on-success); }
.btn-primary:not(:disabled):hover { opacity: 0.9; }
.btn-danger { background: transparent; color: var(--destructive-text); border-color: var(--border); }
.btn-danger:not(:disabled):hover { background: rgba(193,59,48,0.14); border-color: rgba(240,113,106,0.35); }
.btn-ghost { background: transparent; color: var(--ink-muted); border-color: var(--border); }
.btn-ghost:not(:disabled):hover { background: var(--card-raised); color: var(--ink); }
.btn:disabled, .btn.btn-current {
  opacity: 0.5;
  cursor: not-allowed;
  background: transparent !important;
  color: var(--ink-muted) !important;
  border-color: var(--border) !important;
}

.btn:focus-visible, summary:focus-visible {
  outline: 2px solid var(--accent-text);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .btn { transition: none; }
}

.empty {
  max-width: 1320px;
  margin: 0 auto;
  background: var(--card);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  padding: 60px 20px;
  text-align: center;
  color: var(--ink-muted);
  font-size: 14px;
}
.empty strong { display: block; color: var(--ink); font-size: 15px; margin-bottom: 6px; }

.error-page {
  max-width: 480px;
  margin: 15vh auto 0;
  text-align: center;
  color: var(--ink-muted);
}
.error-page h1 { color: var(--ink); font-size: 20px; margin-bottom: 8px; }
.error-page a { color: var(--accent-text); }

.generate-bar {
  max-width: 1320px;
  margin: 0 auto 20px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.generate-input {
  flex: 1;
  min-width: 0;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--ink);
  font-family: 'Inter', sans-serif;
  font-size: 13.5px;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
}
.generate-input:focus-visible { outline: 2px solid var(--accent-text); outline-offset: 1px; }
.generate-input::placeholder { color: var(--ink-muted); }
.generate-btn { width: auto; flex-shrink: 0; padding: 9px 18px; }

.spinner {
  width: 22px; height: 22px; flex-shrink: 0;
  border-radius: 50%;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  animation: gen-spin 0.8s linear infinite;
}
@keyframes gen-spin { to { transform: rotate(360deg); } }
.generate-text strong { display: block; font-size: 13.5px; font-weight: 700; }
.generate-text .generate-sub { font-size: 12px; color: var(--ink-muted); }

@media (prefers-reduced-motion: reduce) {
  .spinner { animation: none; opacity: 0.6; }
}

.gen-toast {
  position: fixed;
  bottom: 22px;
  right: 22px;
  z-index: 50;
  max-width: 320px;
  background: var(--card);
  border: 1px solid var(--border);
  border-left: 3px solid var(--success-text);
  border-radius: var(--radius-sm);
  padding: 13px 16px;
  font-size: 13px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}
.gen-toast.error { border-left-color: var(--destructive-text); }
[hidden] { display: none !important; }
</style>
</head>
<body>
<header class="site">
  <div class="brand">
    <div class="brand-mark">__PLAY_ICON__</div>
    <div>
      <h1>History Shorts — Review Desk</h1>
      <p class="tagline">Nothing here posts anywhere by itself</p>
    </div>
  </div>
  <div class="stat-row">__FILTERS__</div>
</header>
__GENERATE_BAR__
<p class="note">Approve = eligible for the publish workflow to pick up next time it runs. Reject archives it here only. This page never talks to YouTube or Instagram.</p>
<main>
__CONTENT__
</main>
<div id="gen-toast" class="gen-toast" hidden></div>
<script>
(function () {
  var bar = document.querySelector('[data-gen-status="running"]');
  if (!bar) return;

  var startedAtMs = parseFloat(bar.getAttribute('data-started-at')) * 1000;
  var elapsedEl = document.getElementById('gen-elapsed');
  function fmt(ms) {
    var s = Math.max(0, Math.floor(ms / 1000));
    var m = Math.floor(s / 60);
    s = s % 60;
    return m + ':' + (s < 10 ? '0' : '') + s;
  }
  var tickTimer = setInterval(function () {
    if (elapsedEl) elapsedEl.textContent = fmt(Date.now() - startedAtMs);
  }, 1000);

  function showToast(msg, isError) {
    var t = document.getElementById('gen-toast');
    if (!t) return;
    t.textContent = msg;
    t.className = 'gen-toast' + (isError ? ' error' : '');
    t.hidden = false;
  }

  var pollTimer = setInterval(function () {
    fetch('/status').then(function (r) { return r.json(); }).then(function (data) {
      if (data.status === 'done') {
        clearInterval(pollTimer);
        clearInterval(tickTimer);
        showToast('New video ready for review.', false);
        setTimeout(function () { location.reload(); }, 1600);
      } else if (data.status === 'error') {
        clearInterval(pollTimer);
        clearInterval(tickTimer);
        showToast('Generation failed: ' + (data.error || 'unknown error'), true);
        setTimeout(function () { location.reload(); }, 2400);
      }
    }).catch(function () {});
  }, 3000);
})();
</script>
</body>
</html>
"""

ERROR_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ — History Shorts</title>
<link rel="icon" href="__FAVICON__">
<style>
  body { margin:0; background:#0B1120; color:#94A3B8; font-family:system-ui,sans-serif; padding:28px; }
  .error-page { max-width:480px; margin:15vh auto 0; text-align:center; }
  .error-page h1 { color:#F8FAFC; font-size:20px; margin-bottom:8px; }
  .error-page a { color:#E0B368; }
</style>
</head>
<body>
<div class="error-page">
  <h1>__TITLE__</h1>
  <p>__MESSAGE__</p>
  <p><a href="/">Back to the review queue</a></p>
</div>
</body>
</html>
"""


def error_page(title: str, message: str, code: int):
    body = ERROR_PAGE.replace("__FAVICON__", FAVICON).replace("__TITLE__", title).replace("__MESSAGE__", message)
    return body, code


@app.errorhandler(404)
def not_found(_e):
    return error_page("Not found", "That item isn't in the queue — it may have already been cleared out by the pipeline.", 404)


@app.errorhandler(400)
def bad_request(_e):
    return error_page("Bad request", "That action couldn't be processed. Go back and try again.", 400)


FILTER_CHIPS = [
    # (key, label, color_var or None)
    ("all", "All", None),
    ("pending", "Pending", "var(--pending-text)"),
    ("needs_review", "Needs review", "var(--accent-text)"),
    ("approved", "Approved", "var(--success-text)"),
    ("rejected", "Rejected", "var(--destructive-text)"),
]


def render_filter_chip(key: str, label: str, color: str | None, count: int, current: str) -> str:
    href = "/" if key == "all" else f"/?filter={key}"
    active = " active" if key == current else ""
    dot = f'<span class="dot" style="background:{color}"></span>' if color else ""
    return f'<a href="{href}" class="stat-pill{active}">{dot}<span class="num">{count}</span><span class="label">{label}</span></a>'


def render_generate_bar(gen_status: dict) -> str:
    state = gen_status.get("status", "idle")
    if state == "running":
        topic_label = esc(gen_status.get("topic") or "(free pick)")
        started_at = gen_status.get("started_at") or time.time()
        return (
            f'<div class="generate-bar" data-gen-status="running" data-started-at="{started_at}">'
            f'<div class="spinner" aria-hidden="true"></div>'
            f'<div class="generate-text"><strong>Generating a new video&hellip;</strong>'
            f'<span class="generate-sub">Topic: {topic_label} &middot; '
            f'<span id="gen-elapsed">0:00</span> elapsed &middot; usually takes a few minutes</span></div>'
            f"</div>"
        )
    return (
        '<form method="post" action="/generate" class="generate-bar" data-gen-status="idle">'
        '<input type="text" name="topic" class="generate-input" autocomplete="off" '
        'placeholder="Topic seed (optional) — leave blank for a free pick">'
        f'<button type="submit" class="btn btn-primary generate-btn">{ICON_PLAY}Generate video</button>'
        "</form>"
    )


@app.route("/generate", methods=["POST"])
def generate():
    topic = request.form.get("topic", "").strip()
    generation_job.start(topic)  # no-ops (silently) if one is already running
    return redirect(url_for("index"))


@app.route("/status")
def status():
    return jsonify(generation_job.get_status())


@app.route("/")
def index():
    items = load_items()
    counts = {"pending": 0, "approved": 0, "rejected": 0}
    needs_review_count = 0
    for it in items:
        s = it["meta"].get("status", "pending")
        counts[s] = counts.get(s, 0) + 1
        if it["script"].get("needs_human_review"):
            needs_review_count += 1
    chip_counts = {
        "all": len(items),
        "pending": counts["pending"],
        "needs_review": needs_review_count,
        "approved": counts["approved"],
        "rejected": counts["rejected"],
    }

    filter_key = request.args.get("filter", "all")
    if filter_key == "needs_review":
        filtered = [it for it in items if it["script"].get("needs_human_review")]
    elif filter_key in ("pending", "approved", "rejected"):
        filtered = [it for it in items if it["meta"].get("status", "pending") == filter_key]
    else:
        filter_key = "all"
        filtered = items

    if filtered:
        content = '<div class="grid">' + "".join(render_item(it) for it in filtered) + "</div>"
    elif items:
        content = (
            '<div class="empty"><strong>Nothing matches this filter</strong>'
            'Try a different filter, or <a href="/">view all</a>.</div>'
        )
    else:
        content = (
            '<div class="empty"><strong>No videos waiting for review</strong>'
            "Use “Generate video” above and new videos will show up here.</div>"
        )

    filters_html = "".join(
        render_filter_chip(key, label, color, chip_counts[key], filter_key)
        for key, label, color in FILTER_CHIPS
    )

    page = (
        PAGE_HTML
        .replace("__FAVICON__", FAVICON)
        .replace("__PLAY_ICON__", ICON_MARK)
        .replace("__FILTERS__", filters_html)
        .replace("__GENERATE_BAR__", render_generate_bar(generation_job.get_status()))
        .replace("__CONTENT__", content)
    )
    return page


@app.route("/media/<item_id>/video.mp4")
def media(item_id):
    item_dir = QUEUE_DIR / item_id
    if not item_dir.exists():
        abort(404)
    return send_from_directory(item_dir, "video.mp4")


@app.route("/decide/<item_id>", methods=["POST"])
def decide(item_id):
    action = request.form.get("action")
    if action not in ("approve", "reject", "pending"):
        abort(400)
    meta_path = QUEUE_DIR / item_id / "meta.json"
    if not meta_path.exists():
        abort(404)
    meta = json.loads(meta_path.read_text())
    meta["status"] = "approved" if action == "approve" else ("rejected" if action == "reject" else "pending")
    meta["decided_at"] = time.time()
    meta_path.write_text(json.dumps(meta, indent=2))
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8787, debug=False)
