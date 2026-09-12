"""Backend for the first real, visible slice of the timeline editor (Phase B — see
Claude outputs/OPEN_ISSUES.md #3). Deliberately narrow: the only edit operation is a
caption's text, and the only render action is "re-render the whole thing" — proving the
render-from-timeline path (pipeline/render_timeline.py, built this session) actually
works end to end from a real UI, before building trim/reorder/swap-clip editing on top
of it. Reuses app/studio/service.py's ownership scoping rather than re-deriving it.

Render status is tracked in a plain in-process dict, not a DB-backed job row like
app/generation/job_manager.py uses for full generations — correct only because gunicorn
runs a single worker process (docker-compose.yml, `--workers 1`), the same fact
job_manager's own in-process lock already depends on. If this ever needs a second worker
process, this needs a real job row (or Redis) the same way job_manager would.
"""
import sys
import threading
from pathlib import Path

from sqlalchemy.orm.attributes import flag_modified

from app.db import get_session
from app.generation import job_manager
from app.models import User
from app.studio import service as studio_service

PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

_render_status: dict[str, dict] = {}
_render_lock = threading.Lock()


def get_timeline(story_id: str, user: User) -> dict | None:
    story = studio_service.get_story(story_id, user)
    if story is None:
        return None
    return story.timeline or {}


def update_caption(story_id: str, cap_id: str, text: str, user: User) -> dict | None:
    """Edits one caption's text in place. Clears that caption's per-word timestamps
    ("words") since they no longer match the edited text — captions.build_ass_from_track
    falls back to treating the whole caption as a single karaoke unit when "words" is
    absent, which is the correct (if less flashy) rendering for hand-edited text rather
    than replaying stale timing against different words."""
    story = studio_service.get_story(story_id, user)
    if story is None:
        return None
    timeline = story.timeline or {}
    captions = ((timeline.get("tracks") or {}).get("captions")) or []
    found = None
    for cap in captions:
        if cap.get("id") == cap_id:
            cap["text"] = text
            cap.pop("words", None)
            found = cap
            break
    if found is None:
        return None
    # Reassigning story.timeline to the SAME (in-place-mutated) dict object does NOT
    # reliably persist: SQLAlchemy's flush uses the column's own before/after history to
    # decide whether to include it in the UPDATE, and a plain JSONB Column's history
    # check is a Python `==` — since the "before" and "after" here are literally the same
    # object (mutated in place), it compares equal to itself and gets silently dropped
    # from the UPDATE even though the object shows up in session.dirty. flag_modified()
    # is the actual fix — confirmed live: without it, a caption edit returned success but
    # silently never reached the database. See Claude outputs/OPEN_ISSUES.md.
    story.timeline = timeline
    flag_modified(story, "timeline")
    get_session().commit()
    return timeline


def render_status(story_id: str) -> dict:
    with _render_lock:
        return dict(_render_status.get(story_id, {"status": "idle"}))


def start_render(story_id: str, user: User) -> tuple[bool, str]:
    story = studio_service.get_story(story_id, user)
    if story is None:
        return False, "not found"
    if not story.timeline or not (story.timeline.get("tracks") or {}).get("visual"):
        return False, "this story has no timeline to render from"

    with _render_lock:
        current = _render_status.get(story_id)
        if current and current.get("status") == "rendering":
            return False, "already rendering"
        # A re-render is as CPU-heavy (ffmpeg) as an original generation — avoid piling
        # onto an active one on this single-instance deployment (see job_manager.py's own
        # "one generation at a time" reasoning; the same constraint applies here).
        if job_manager.get_status().get("status") == "running":
            return False, "a generation is currently running — try again once it finishes"
        _render_status[story_id] = {"status": "rendering", "error": None}

    def _run() -> None:
        import render_timeline  # pipeline/ is on sys.path (see module load above)

        from app import db

        try:
            render_timeline.render_story(story_id)
            with _render_lock:
                _render_status[story_id] = {"status": "done", "error": None}
        except Exception as exc:  # noqa: BLE001 - surfaced to the user via render_status(), not swallowed
            with _render_lock:
                _render_status[story_id] = {"status": "error", "error": str(exc)}
        finally:
            # Long-lived daemon thread, not a Flask request — nothing else calls
            # remove_session() for it. Same leak/reuse risk as job_manager._watch();
            # see that function's comment for the full reasoning.
            db.remove_session()

    threading.Thread(target=_run, daemon=True).start()
    return True, "rendering started"
