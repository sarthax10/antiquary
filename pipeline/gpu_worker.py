#!/usr/bin/env python3
"""Runs on a GPU-having machine (this laptop — see Claude outputs/OPEN_ISSUES.md #66)
and polls a DIFFERENT machine's web app (GPU_SERVER_URL — production's `reliquary`, or
http://localhost:8787 to test against your own local stack) for pending illustration
jobs, generates each with pipeline/illustrate.py, and posts the result back.

Deliberately POLLS OUTWARD rather than the server pushing in: this laptop sits behind a
home router with no inbound port-forwarding, the exact same constraint documented in
.github/workflows/deploy.yml for the self-hosted GitHub Actions runner — "that's what
lets this reach a machine behind a home router... the runner polls GitHub, GitHub never
has to reach in." Same shape here: this worker polls the server, the server never has
to reach in.

Usage: set GPU_SERVER_URL and GPU_WORKER_TOKEN (see .env.example) and run
`python pipeline/gpu_worker.py` from inside this laptop's GPU-enabled antiquary-app
container (torch/diffusers/CUDA already installed there — see docker-compose.yml's
WITH_GPU_ILLUSTRATION build arg). Exits immediately if no GPU is actually available —
this script has nothing useful to do without one. Runs until killed (Ctrl+C / container
stop); every failure mode (network error, generation error, upload error) is caught and
logged, never crashes the loop.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import illustrate  # noqa: E402
from image_quality import technical_quality_score  # noqa: E402

POLL_INTERVAL_IDLE = 2.0
POLL_INTERVAL_ERROR = 5.0
REQUEST_TIMEOUT = 15.0

# A generation this poor is worth one retry with a different seed before giving up —
# see image_quality.py's own docstring for exactly what this does and doesn't catch
# (blur/flatness, not anatomical distortion — that's illustrate.is_multi_subject_prompt's
# job, applied upstream by the server before a job is even created).
MIN_QUALITY_TO_ACCEPT = 0.5


def _generate_with_retry(prompt: str, seed: int | None, out_path: Path) -> bool:
    best_score = -1.0
    for attempt_seed in (seed, (seed or 0) + 1):
        if not illustrate.generate_illustration(prompt, out_path, seed=attempt_seed):
            continue
        score = technical_quality_score(out_path)
        print(f"[gpu_worker] attempt seed={attempt_seed} quality={score:.2f}", file=sys.stderr)
        if score >= MIN_QUALITY_TO_ACCEPT:
            return True
        if score > best_score:
            best_score = score
        else:
            out_path.unlink(missing_ok=True)
    return best_score >= 0  # kept whichever attempt's file is still on disk, even if
    # neither cleared the bar — the server-side ranking (asset_ranking.py) still
    # compares it against the real candidate and can reject it there, which is a better
    # place for that call than a worker guessing in isolation.


def _handle_job(server: str, headers: dict, job: dict) -> None:
    job_id = job["id"]
    prompt = job["prompt"]
    seed = job.get("seed")
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "illustration.png"
        try:
            ok = _generate_with_retry(prompt, seed, out_path)
        except Exception as e:
            ok = False
            print(f"[gpu_worker] generation crashed for job {job_id}: {type(e).__name__}: {e}", file=sys.stderr)
        if not ok:
            try:
                requests.post(f"{server}/api/gpu-worker/jobs/{job_id}/fail", headers=headers,
                               json={"error": "generation failed or produced no usable image"},
                               timeout=REQUEST_TIMEOUT)
            except requests.exceptions.RequestException:
                pass
            return
        try:
            with open(out_path, "rb") as f:
                resp = requests.post(f"{server}/api/gpu-worker/jobs/{job_id}/result", headers=headers,
                                      files={"image": ("illustration.png", f, "image/png")},
                                      timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            print(f"[gpu_worker] completed job {job_id}", file=sys.stderr)
        except requests.exceptions.RequestException as e:
            print(f"[gpu_worker] could not submit result for job {job_id}: {type(e).__name__}: {e}", file=sys.stderr)


def run(server: str, token: str) -> None:
    headers = {"X-Worker-Token": token}
    print(f"[gpu_worker] polling {server} for illustration jobs...", file=sys.stderr)
    while True:
        try:
            resp = requests.get(f"{server}/api/gpu-worker/jobs/next", headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            job = resp.json().get("job")
        except requests.exceptions.RequestException as e:
            print(f"[gpu_worker] poll failed: {type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(POLL_INTERVAL_ERROR)
            continue
        if job is None:
            time.sleep(POLL_INTERVAL_IDLE)
            continue
        print(f"[gpu_worker] claimed job {job['id']!r}: {job['prompt']!r}", file=sys.stderr)
        _handle_job(server, headers, job)


if __name__ == "__main__":
    server = os.environ.get("GPU_SERVER_URL", "").rstrip("/")
    token = os.environ.get("GPU_WORKER_TOKEN", "")
    if not server or not token:
        print("[gpu_worker] GPU_SERVER_URL and GPU_WORKER_TOKEN must both be set", file=sys.stderr)
        sys.exit(1)
    if not illustrate.gpu_illustration_available():
        print("[gpu_worker] no CUDA GPU available on this machine — nothing to do", file=sys.stderr)
        sys.exit(1)
    run(server, token)
