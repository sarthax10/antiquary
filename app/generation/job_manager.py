#!/usr/bin/env python3
"""Runs pipeline/run_pipeline.py as a fully separate OS process (not a thread inside the
Flask process) so a crash or hang in generation can never take the API down with it, and
persists its state to a GenerationJob row so status survives a restart and is visible to
every request — not just the one that started the job.

Only one generation subprocess is ever running at a time — the CPU-bound local Ollama
model can't usefully serve two requests at once (concurrent requests truncating each
other's output was a real, confirmed failure mode earlier in this project). A second
`start()` while one is already running no longer errors outright, though: it enqueues
(status="queued") instead, and get_status() opportunistically promotes the oldest queued
job to running once nothing is — piggybacking on the polling the frontend already does
every 2.5s rather than needing a separate scheduler process.

Status and cancellation are per-user, matching per-user story ownership (see
app/studio/service.py) — a user sees and can cancel their own running/queued job (or an
admin can cancel anyone's), not a shared global status, even though only one pipeline
subprocess ever runs system-wide.

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

from sqlalchemy.exc import IntegrityError

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


def _running_job() -> GenerationJob | None:
    return get_session().query(GenerationJob).filter_by(status="running").first()


def _queued_jobs() -> list[GenerationJob]:
    return (
        get_session().query(GenerationJob)
        .filter_by(status="queued")
        .order_by(GenerationJob.started_at.asc())
        .all()
    )


def _latest_job(user_id: int | None = None) -> GenerationJob | None:
    query = get_session().query(GenerationJob)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    return query.order_by(GenerationJob.started_at.desc()).first()


def _job_json(job: GenerationJob | None, queue_length: int = 0, queue_position: int | None = None) -> dict:
    if job is None:
        return {"status": "idle", "queue_length": queue_length}
    return {
        "status": job.status,
        "topic": job.topic,
        "pid": job.pid,
        "stage": job.stage,
        "started_at": job.started_at.timestamp() if job.started_at else None,
        "finished_at": job.finished_at.timestamp() if job.finished_at else None,
        "error": job.error,
        "story_id": job.resulting_story_id,
        "queue_length": queue_length,
        "queue_position": queue_position,
    }


def _spawn(job: GenerationJob) -> None:
    """Launches the pipeline subprocess for an already-`running` job row. Shared by
    start() (spawning immediately) and get_status() (promoting a queued job)."""
    global _current_proc
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(LOG_PATH, "w")
    env = os.environ.copy()
    env["GENERATION_JOB_ID"] = str(job.id)
    if job.user_id is not None:
        env["GENERATION_USER_ID"] = str(job.user_id)
    proc = subprocess.Popen(
        [sys.executable, "run_pipeline.py", job.topic],
        cwd=str(PIPELINE_DIR),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        env=env,
    )
    _current_proc = proc
    job.pid = proc.pid
    get_session().commit()
    threading.Thread(target=_watch, args=(proc, job.id), daemon=True).start()


def _queue_position(job: GenerationJob) -> int:
    """1-based position among currently queued jobs, oldest first."""
    return 1 + (
        get_session().query(GenerationJob)
        .filter(GenerationJob.status == "queued", GenerationJob.started_at < job.started_at)
        .count()
    )


def get_status(user=None) -> dict:
    """Self-heals a crashed running job and promotes the oldest queued job once nothing
    is running. With `user`, reports that user's own running/queued job (or their most
    recent finished one) plus the global queue depth; without one (internal callers),
    reports whichever job is running.

    The self-heal + promotion below runs under `_lock`, same as start()/cancel() — without
    it, two near-simultaneous polls could both see "nothing running" and both promote+spawn
    the same queued job: the DB-level unique index only blocks a second *row* from being
    running, not two threads both completing the UPDATE on the *same* row and each calling
    _spawn() on it, which would launch two real pipeline subprocesses against one Ollama
    instance — exactly what the one-subprocess-at-a-time design exists to prevent."""
    session = get_session()
    with _lock:
        running = _running_job()
        if running is not None and (not running.pid or not _pid_alive(running.pid)):
            running.status = "error"
            running.error = "Generation process ended unexpectedly (was the app restarted mid-run?)."
            running.finished_at = utcnow()
            session.commit()
            running = None

        if running is None:
            queued = _queued_jobs()
            if queued:
                job = queued[0]
                job.status = "running"
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()  # lost a race — someone else's job is running now
                else:
                    _spawn(job)
                    running = job

    queue_length = get_session().query(GenerationJob).filter_by(status="queued").count()

    if user is None:
        return _job_json(running, queue_length=queue_length)

    mine = (
        get_session().query(GenerationJob)
        .filter(GenerationJob.user_id == user.id, GenerationJob.status.in_(("queued", "running")))
        .order_by(GenerationJob.started_at.asc())
        .first()
    )
    if mine is not None:
        position = _queue_position(mine) if mine.status == "queued" else None
        return _job_json(mine, queue_length=queue_length, queue_position=position)

    return _job_json(_latest_job(user.id), queue_length=queue_length)


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
    from app import db  # local import: keep this module Flask-optional (see app/db.py's own docstring)

    try:
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
    finally:
        # This is a long-lived daemon thread, not a Flask request — nothing else ever
        # calls remove_session() for it. Without this, the scoped_session registry keeps
        # this thread's session forever (a real leak over the server's lifetime), and if
        # CPython later reuses this thread's id for a new thread, that thread could
        # inherit this one's abandoned session state.
        db.remove_session()


def start(topic: str, user) -> tuple[bool, str]:
    """Returns (started, message). Enqueues (status="queued") instead of refusing when a
    generation is already running — get_status() promotes the oldest queued job once
    nothing is. Refuses only if this same user already has a running or queued job of
    their own (one at a time per user, not one at a time globally-with-no-queue)."""
    global _current_proc
    with _lock:
        session = get_session()
        if user is not None:
            existing = (
                session.query(GenerationJob)
                .filter(GenerationJob.user_id == user.id, GenerationJob.status.in_(("queued", "running")))
                .first()
            )
            if existing is not None:
                return False, "You already have a generation running or queued."

        # Join the back of the queue whenever anything is running OR already queued —
        # not just when something is running. Otherwise a new job could jump ahead of an
        # earlier queued one that just hasn't been promoted by get_status() yet (e.g.
        # nobody has polled status since the previous job finished).
        blocked = _running_job() is not None or bool(_queued_jobs())
        job = GenerationJob(user_id=user.id if user else None, topic=topic, status="queued" if blocked else "running")
        session.add(job)
        try:
            session.commit()  # need job.id before spawning, so the subprocess can report to it
        except IntegrityError:
            # Lost a race with another request that started running first (defense in
            # depth — with gunicorn's single worker this shouldn't actually happen).
            session.rollback()
            job = GenerationJob(user_id=user.id if user else None, topic=topic, status="queued")
            session.add(job)
            session.commit()

        if job.status != "running":
            return True, f"queued (position {_queue_position(job)})"

        _spawn(job)
        return True, "started"


def cancel(user) -> tuple[bool, str]:
    """Cancels the caller's own job first — their running one (SIGTERM, escalating to
    SIGKILL after a short grace period) if they have one, else their oldest queued one,
    which is just a status flip since it was never spawned. Only once the caller has
    nothing of their own to cancel does an admin's bypass kick in, letting them stop
    someone else's running job. Returns (cancelled, message); message is "forbidden"
    when a non-admin tries to touch a running job that isn't theirs.

    The caller's own job is checked before the admin bypass deliberately: an admin who
    queued behind someone else's job and clicks "leave queue" must cancel their own
    queued entry, not reach for admin privileges and kill the other person's running
    job instead — an earlier version got this backwards.

    Normally operates on the in-memory Popen handle (_current_proc), which lets it reap
    the child cleanly via proc.wait(). That handle only exists in the process that
    called start() — if the app was restarted while a generation was running,
    _current_proc is None even though the job (tracked in the DB, self-healed by
    get_status()'s pid check) is still genuinely alive. In that case, fall back to
    signalling by PID directly and polling for it to disappear."""
    global _current_proc
    with _lock:
        session = get_session()
        running = _running_job()
        owns_running = running is not None and (running.user_id is None or running.user_id == user.id)

        queued_mine = (
            session.query(GenerationJob)
            .filter(GenerationJob.user_id == user.id, GenerationJob.status == "queued")
            .order_by(GenerationJob.started_at.asc())
            .first()
        )
        if not owns_running and queued_mine is not None:
            queued_mine.status = "cancelled"
            queued_mine.finished_at = utcnow()
            session.commit()
            return True, "cancelled"

        if owns_running or (running is not None and user.is_admin):
            proc = _current_proc
            pid = running.pid
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
            elif pid:
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
            running.status = "cancelled"
            running.finished_at = utcnow()
            running.error = None
            session.commit()
            _current_proc = None
            return True, "cancelled"

        if running is not None:
            return False, "forbidden"
        return False, "Nothing is running."
