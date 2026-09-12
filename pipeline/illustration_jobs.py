#!/usr/bin/env python3
"""Server-side client for requesting a GPU-generated illustration from a remote worker
(see app/gpu_worker/routes.py, pipeline/gpu_worker.py, Claude outputs/OPEN_ISSUES.md
#66). Runs inside the pipeline process, which already has direct DB access (see
CLAUDE.md on why this project uses plain SQLAlchemy) — creating and polling the job row
directly is simpler and more reliable than the pipeline calling its own HTTP API. Only
the remote worker (a genuinely separate machine with no DB access) talks to this server
over HTTP.

The one function here, request_illustration(), NEVER raises: any failure (no worker
listening, DB error, MinIO error, timeout) returns None, and pipeline/fetch_visuals.py
falls straight through to real sourcing only — "if this system is not available, use
the normal flow" is the default, not a special case.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import get_session  # noqa: E402
from app.models import IllustrationJob  # noqa: E402
from app import storage  # noqa: E402

# Matches app/gpu_worker/service.py's JOB_TTL_SECONDS exactly — see that module's
# docstring for why both sides need to agree: a worker must never spend real GPU time
# completing a job this side has already given up on.
JOB_TTL_SECONDS = 30
POLL_INTERVAL = 1.0


def request_illustration(prompt: str, width: int = 512, height: int = 512,
                          seed: int | None = None, timeout: float = JOB_TTL_SECONDS) -> bytes | None:
    """Creates a pending IllustrationJob, polls for a remote worker to fulfill it up to
    `timeout` seconds, and returns the generated image's bytes on success. Returns None
    on any failure, including "no worker claimed this in time" — that specific case
    marks the job "expired" (best-effort) so a straggling worker doesn't waste a
    generation completing it after this caller has already moved on."""
    try:
        session = get_session()
        job = IllustrationJob(prompt=prompt, width=width, height=height, seed=seed, status="pending")
        session.add(job)
        session.commit()
        job_id = job.id
    except Exception as e:
        print(f"[illustration_jobs] could not create job: {type(e).__name__}: {e}", file=sys.stderr)
        return None

    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            time.sleep(POLL_INTERVAL)
            session.expire_all()
            job = session.get(IllustrationJob, job_id)
            if job is None:
                return None
            if job.status == "done":
                if not job.image_object_key:
                    return None
                return _download(job.image_object_key)
            if job.status == "failed":
                return None
        _expire(job_id)
        return None
    except Exception as e:
        print(f"[illustration_jobs] error polling job {job_id}: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def _download(object_key: str) -> bytes | None:
    import tempfile
    from pathlib import Path
    try:
        with tempfile.TemporaryDirectory() as tmp:
            local_path = Path(tmp) / "illustration.png"
            storage.download_asset(object_key, str(local_path))
            return local_path.read_bytes()
    except Exception as e:
        print(f"[illustration_jobs] could not download {object_key}: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def _expire(job_id: str) -> None:
    try:
        session = get_session()
        job = session.get(IllustrationJob, job_id)
        if job is not None and job.status == "pending":
            job.status = "expired"
            session.commit()
    except Exception:
        pass  # best-effort — a straggling worker completing it anyway is a wasted
        # generation, not a correctness problem
