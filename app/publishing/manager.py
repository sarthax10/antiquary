"""Publishes a Story to a user's connected SocialAccount as a background thread inside
the Flask process — not a separate OS subprocess like app/generation/job_manager.py,
because this is network I/O (an HTTP upload), not CPU-bound work that needs process
isolation from the rest of the app.

Unlike generation, publish jobs are NOT serialized globally. "One generation at a time"
exists specifically because of local Ollama CPU contention (see CLAUDE.md) — that
doesn't apply to an HTTP upload. Concurrency is only guarded per (story_id, platform):
two clicks on the same story's same platform while one is already running refuse;
everything else runs freely.

Staleness (not in-memory job tracking) is what detects an orphaned pending/uploading
row — e.g. the app restarted mid-upload. gunicorn runs multiple worker PROCESSES
(--workers 2 in docker-compose.yml); a Python-level set/thread tracked in one worker is
simply invisible to a request handled by another. An earlier version of this file used
an in-memory `_active` set for exactly this and it was wrong in production: the request
that starts a publish and the request that polls its status can land on different
workers, so the poller would see no record of the job and incorrectly mark a
genuinely-in-progress (and in one observed case, already-succeeded) upload as
interrupted. Publication.updated_at (auto-touched by the model's onupdate=) is
process-agnostic — every worker reads the same database row — so staleness is judged by
elapsed time since the last real progress update instead."""
import os
import tempfile
import threading
from datetime import timedelta

from app import storage
from app.db import get_session
from app.models import Publication, Story, utcnow
from app.social import service as social_service
from app.social import youtube

# Generous: a slow connection uploading a several-MB video shouldn't be mistaken for a
# dead job. Only matters for detecting a job whose owning process actually died.
_STALE_AFTER = timedelta(minutes=10)


def _is_stale(pub: Publication) -> bool:
    return pub.status in ("pending", "uploading") and (utcnow() - pub.updated_at) > _STALE_AFTER


def get_publications_for_story(story_id: str) -> list[Publication]:
    session = get_session()
    pubs = (
        session.query(Publication)
        .filter_by(story_id=story_id)
        .order_by(Publication.created_at.desc())
        .all()
    )
    dirty = False
    for pub in pubs:
        if _is_stale(pub):
            pub.status = "failed"
            pub.error = "Publish appears to have stalled or the app restarted mid-run."
            dirty = True
    if dirty:
        session.commit()
    return pubs


def _upload_worker(publication_id: int, story_id: str, platform: str) -> None:
    session = get_session()
    tmp_path = None
    try:
        pub = session.get(Publication, publication_id)
        pub.status = "uploading"
        pub.stage = "downloading"
        session.commit()

        story = session.get(Story, story_id)
        account = pub.social_account
        if account is None:
            raise RuntimeError("The connected account was disconnected before this could run.")

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name
        storage.download_video(story.video_object_key, tmp_path)

        pub.stage = "uploading"
        session.commit()

        access_token = social_service.get_valid_access_token(account)
        description = f"{story.hook}\n\n{story.narration}".strip()
        if platform == "youtube":
            video_id, video_url = youtube.upload_video(access_token, tmp_path, story.title, description)
        else:
            raise NotImplementedError(f"Publishing to {platform!r} isn't built yet.")

        pub.status = "published"
        pub.error = None
        pub.external_id = video_id
        pub.external_url = video_url
        pub.stage = None
        pub.published_at = utcnow()
        session.commit()
    except Exception as exc:
        session.rollback()
        pub = session.get(Publication, publication_id)
        pub.status = "failed"
        pub.error = str(exc)[:2000]
        pub.stage = None
        session.commit()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def start_publish(story_id: str, platform: str, social_account, requested_by) -> tuple[bool, str, Publication | None]:
    """Returns (started, message, publication)."""
    session = get_session()
    story = session.get(Story, story_id)
    if story is None:
        return False, "Story not found.", None
    if story.status != "approved":
        return False, "Only approved stories can be published.", None
    if not story.video_object_key:
        return False, "This story has no rendered video to publish.", None

    in_flight = (
        session.query(Publication)
        .filter_by(story_id=story_id, platform=platform)
        .filter(Publication.status.in_(("pending", "uploading")))
        .order_by(Publication.created_at.desc())
        .first()
    )
    if in_flight is not None and not _is_stale(in_flight):
        return False, "A publish attempt for this story is already running.", None

    pub = Publication(
        story_id=story_id,
        platform=platform,
        social_account_id=social_account.id,
        status="pending",
        requested_by_id=requested_by.id if requested_by else None,
    )
    session.add(pub)
    session.commit()  # need pub.id before spawning, so the thread can report to it

    threading.Thread(target=_upload_worker, args=(pub.id, story_id, platform), daemon=True).start()
    return True, "started", pub
