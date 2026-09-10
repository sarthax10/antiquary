#!/usr/bin/env python3
"""Runs pipeline/run_pipeline.py as a fully separate OS process (not a thread inside the
Flask process) so a crash or hang in generation can never take the API down with it, and
persists its state to a GenerationJob row so status survives a restart and is visible to
every request — not just the one that started the job.

Only one generation is ever allowed to run at a time — starting a second one while the
first is still going wastes the CPU-bound local Ollama model's time twice over and was
the direct cause of real failures earlier in this project (concurrent requests
truncating each other's output). start() refuses if a live job is already running.

Needs no Flask app/request context — only app.db's plain session — which is what lets
set_stage() be called from inside the pipeline subprocess itself (a separate OS process
entirely) via the GENERATION_JOB_ID env var this module sets before spawning it.
"""
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from app.db import get_session
from app.models import GenerationJob, utcnow

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE_DIR = REPO_ROOT / "pipeline"
LOG_PATH = REPO_ROOT / "media" / "generation_log.txt"

# Real pipeline stages, in order — kept in sync with pipeline/run_pipeline.py's actual steps.
STAGES = [
    ("writing", "Writing the story"),
    ("fact_checking", "Fact-checking claims"),
    ("sourcing_visuals", "Sourcing visuals"),
    ("recording_narration", "Recording narration"),
    ("generating_captions", "Generating captions"),
    ("rendering", "Rendering the film"),
]
STAGE_KEYS = [k for k, _ in STAGES]

_lock = threading.Lock()
_current_proc: subprocess.Popen | None = None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _log_tail(n_chars: int = 800) -> str:
    if not LOG_PATH.exists():
        return ""
    return LOG_PATH.read_text(errors="replace")[-n_chars:]


def _latest_job() -> GenerationJob | None:
    return (
        get_session().query(GenerationJob)
        .order_by(GenerationJob.started_at.desc())
        .first()
    )


def _job_json(job: GenerationJob | None) -> dict:
    if job is None:
        return {"status": "idle"}
    return {
        "status": job.status,
        "topic": job.topic,
        "pid": job.pid,
        "stage": job.stage,
        "started_at": job.started_at.timestamp() if job.started_at else None,
        "finished_at": job.finished_at.timestamp() if job.finished_at else None,
        "error": job.error,
        "story_id": job.resulting_story_id,
    }


def get_status() -> dict:
    """Self-heals if a tracked process died without the watcher thread updating it
    (e.g. the app itself was restarted mid-generation)."""
    session = get_session()
    job = _latest_job()
    if job is not None and job.status == "running":
        if not job.pid or not _pid_alive(job.pid):
            job.status = "error"
            job.error = "Generation process ended unexpectedly (was the app restarted mid-run?)."
            job.finished_at = utcnow()
            session.commit()
    return _job_json(job)


def set_stage(stage_key: str) -> None:
    """Called by pipeline/run_pipeline.py itself (a separate process) at each real step
    it reaches, identified by the GENERATION_JOB_ID env var set in start() before the
    subprocess was spawned."""
    job_id = os.environ.get("GENERATION_JOB_ID")
    if not job_id:
        return
    session = get_session()
    job = session.get(GenerationJob, int(job_id))
    if job is None or job.status != "running":
        return  # e.g. already cancelled — don't resurrect a running-looking status
    job.stage = stage_key
    session.commit()


def _watch(proc: subprocess.Popen, job_id: int) -> None:
    global _current_proc
    returncode = proc.wait()
    session = get_session()
    with _lock:
        if _current_proc is proc:
            _current_proc = None
    job = session.get(GenerationJob, job_id)
    if job is None or job.status == "cancelled":
        return  # cancel() already finalized this run — don't overwrite with "error"

    if returncode == 0:
        tail = _log_tail(200).strip()
        story_id = tail.splitlines()[-1].strip() if tail else None
        job.status = "done"
        job.resulting_story_id = story_id
    else:
        job.status = "error"
        job.error = _log_tail(800).strip() or f"exited with code {returncode}"
    job.finished_at = utcnow()
    session.commit()


def start(topic: str, user) -> tuple[bool, str]:
    """Returns (started, message). Refuses if a generation is already running."""
    global _current_proc
    with _lock:
        if get_status().get("status") == "running":
            return False, "A generation is already running."

        session = get_session()
        job = GenerationJob(user_id=user.id if user else None, topic=topic, status="running")
        session.add(job)
        session.commit()  # need job.id before spawning, so the subprocess can report to it

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(LOG_PATH, "w")
        env = os.environ.copy()
        env["GENERATION_JOB_ID"] = str(job.id)
        if user is not None:
            env["GENERATION_USER_ID"] = str(user.id)
        proc = subprocess.Popen(
            [sys.executable, "run_pipeline.py", topic],
            cwd=str(PIPELINE_DIR),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            env=env,
        )
        _current_proc = proc
        job.pid = proc.pid
        session.commit()

        threading.Thread(target=_watch, args=(proc, job.id), daemon=True).start()
        return True, "started"


def cancel() -> tuple[bool, str]:
    """Terminates the running generation (SIGTERM, escalating to SIGKILL after a short
    grace period) and marks it "cancelled" — distinct from "error" so the UI can tell a
    crash apart from a deliberate stop.

    Normally operates on the in-memory Popen handle (_current_proc), which lets it reap
    the child cleanly via proc.wait(). That handle only exists in the process that
    called start() — if the app was restarted while a generation was running,
    _current_proc is None even though the job (tracked in the DB, self-healed by
    get_status()'s pid check) is still genuinely alive. In that case, fall back to
    signalling by PID directly and polling for it to disappear."""
    global _current_proc
    with _lock:
        session = get_session()
        job = _latest_job()
        proc = _current_proc
        if job is None or job.status != "running":
            return False, "Nothing is running."
        pid = job.pid
        if proc is None and not (pid and _pid_alive(pid)):
            return False, "Nothing is running."

        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except Exception:
                    pass
            except ProcessLookupError:
                pass
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
            for _ in range(20):  # ~4s grace period
                if not _pid_alive(pid):
                    break
                time.sleep(0.2)
            if _pid_alive(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass

        job.status = "cancelled"
        job.finished_at = utcnow()
        job.error = None
        session.commit()
        _current_proc = None
        return True, "cancelled"
