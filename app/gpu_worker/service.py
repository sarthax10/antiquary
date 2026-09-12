"""Claim/complete/fail logic for illustration_jobs — see app/gpu_worker/routes.py for
the HTTP surface a remote GPU-having machine polls, and Claude outputs/OPEN_ISSUES.md
#66 for why this exists: this app's own hosts have no GPU, so illustration generation
is fulfilled by a separate machine over HTTP instead of in-process."""
from datetime import timedelta

from sqlalchemy import update

from app import storage
from app.db import get_session
from app.models import IllustrationJob, utcnow

# How long a pending job stays claimable, and (see pipeline/illustration_jobs.py) how
# long the requesting pipeline process waits for one — the two sides deliberately share
# this exact number so a worker never spends real GPU time completing a job its
# requester has already given up on and fallen through to real sourcing for.
JOB_TTL_SECONDS = 30


def claim_next_job() -> IllustrationJob | None:
    """Atomically claims the oldest still-claimable pending job, or None if there isn't
    one. "Atomic" matters even though this app runs a single gunicorn worker process
    (see CLAUDE.md) — that process is still multi-threaded, so two near-simultaneous
    polls from two real workers (or a retried request from one) are a real possibility,
    not a hypothetical."""
    session = get_session()
    cutoff = utcnow() - timedelta(seconds=JOB_TTL_SECONDS)
    candidate = (
        session.query(IllustrationJob)
        .filter(IllustrationJob.status == "pending", IllustrationJob.created_at >= cutoff)
        .order_by(IllustrationJob.created_at.asc())
        .first()
    )
    if candidate is None:
        return None
    # Re-checking status="pending" in the WHERE clause is what makes this safe under a
    # race: if another thread claimed this exact row between the SELECT above and this
    # UPDATE, rowcount is 0 here and we correctly report "lost the race" instead of
    # handing the same job to two workers.
    result = session.execute(
        update(IllustrationJob)
        .where(IllustrationJob.id == candidate.id, IllustrationJob.status == "pending")
        .values(status="claimed", claimed_at=utcnow())
    )
    session.commit()
    if result.rowcount == 0:
        return None
    session.refresh(candidate)
    return candidate


def complete_job(job_id: str, local_image_path: str, content_type: str = "image/png") -> IllustrationJob | None:
    """Uploads the worker's result to MinIO and marks the job done. Returns None (no
    upload attempted) if the job doesn't exist or isn't in "claimed" state — e.g. it
    already expired out from under a slow worker; see pipeline/illustration_jobs.py's
    own timeout handling."""
    session = get_session()
    job = session.get(IllustrationJob, job_id)
    if job is None or job.status != "claimed":
        return None
    object_key = f"gpu-illustrations/{job_id}.png"
    storage.upload_asset(local_image_path, object_key, content_type=content_type)
    job.status = "done"
    job.image_object_key = object_key
    job.completed_at = utcnow()
    session.commit()
    return job


def fail_job(job_id: str, error: str) -> IllustrationJob | None:
    session = get_session()
    job = session.get(IllustrationJob, job_id)
    if job is None or job.status != "claimed":
        return None
    job.status = "failed"
    job.error = (error or "")[:2000]
    job.completed_at = utcnow()
    session.commit()
    return job
