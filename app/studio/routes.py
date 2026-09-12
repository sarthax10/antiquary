"""Studio API: /api/stories/* and /api/generate/* — the actual product. Every route
requires an approved, logged-in user (app.auth.decorators.approved_required)."""
from flask import Blueprint, Response, jsonify, request
from flask_login import current_user

from app import storage
from app.auth.decorators import approved_required
from app.generation import job_manager
from app.models import VALID_STORY_STATUSES, Story

from . import service

bp = Blueprint("studio", __name__, url_prefix="/api")


def _story_json(story: Story, include_video_url: bool = False) -> dict:
    data = {
        "id": story.id,
        "title": story.title,
        "hook": story.hook,
        "narration": story.narration,
        "fact_check": story.fact_check,
        "claim_counts": story.claim_counts,
        "needs_human_review": story.needs_human_review,
        "status": story.status,
        "topic": story.topic,
        "duration_seconds": story.duration_seconds,
        "created_at": story.created_at.isoformat() if story.created_at else None,
        "decided_at": story.decided_at.isoformat() if story.decided_at else None,
    }
    if include_video_url:
        data["video_url"] = service.video_url(story)
        # Chapter markers for the player's scrubber — just clip start times, not the
        # whole editor timeline (visual_query/entity_type/etc aren't needed here and
        # story.timeline is empty {} for anything rendered before it existed).
        visual_track = (story.timeline or {}).get("tracks", {}).get("visual") or []
        data["chapters"] = [clip["start"] for clip in visual_track]
    return data


@bp.route("/stories")
@approved_required
def list_stories():
    status = request.args.get("status")
    recent = request.args.get("recent", type=int)
    if recent:
        stories = service.recent_stories(current_user, limit=recent)
    elif status == "pending":
        stories = service.pending_stories(current_user)
    elif status in VALID_STORY_STATUSES:
        stories = service.decided_stories(status, current_user)
    else:
        return jsonify(error="pass ?status=pending|approved|rejected or ?recent=N"), 400
    return jsonify(stories=[_story_json(s) for s in stories])


@bp.route("/stories/<story_id>")
@approved_required
def get_story(story_id):
    story = service.get_story(story_id, current_user)
    if story is None:
        return jsonify(error="not found"), 404
    return jsonify(story=_story_json(story, include_video_url=True))


@bp.route("/stories/<story_id>/video")
@approved_required
def story_video(story_id):
    story = service.get_story(story_id, current_user)
    if story is None:
        return jsonify(error="not found"), 404
    if not story.video_object_key:
        return jsonify(error="video not available"), 404

    obj = storage.get_video_object(story.video_object_key, request.headers.get("Range"))
    headers = {
        "Content-Type": obj.get("ContentType", "video/mp4"),
        "Content-Length": str(obj["ContentLength"]),
        "Accept-Ranges": "bytes",
    }
    status = 200
    if "ContentRange" in obj:
        headers["Content-Range"] = obj["ContentRange"]
        status = 206
    return Response(obj["Body"].iter_chunks(), status=status, headers=headers)


@bp.route("/stories/<story_id>/decide", methods=["POST"])
@approved_required
def decide_story(story_id):
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if action not in ("approve", "reject"):
        return jsonify(error="action must be 'approve' or 'reject'"), 400
    story = service.decide_story(story_id, action, decided_by=current_user)
    if story is None:
        return jsonify(error="not found"), 404
    return jsonify(story=_story_json(story))


@bp.route("/stories/<story_id>/restore", methods=["POST"])
@approved_required
def restore_story(story_id):
    story = service.restore_story(story_id, current_user)
    if story is None:
        return jsonify(error="not found"), 404
    return jsonify(story=_story_json(story))


@bp.route("/generate", methods=["POST"])
@approved_required
def generate():
    data = request.get_json(silent=True) or {}
    topic = (data.get("topic") or "").strip()
    started, message = job_manager.start(topic, user=current_user)
    return jsonify(started=started, message=message)


@bp.route("/generate/cancel", methods=["POST"])
@approved_required
def generate_cancel():
    cancelled, message = job_manager.cancel(current_user)
    if message == "forbidden":
        return jsonify(error="You can only cancel your own generation."), 403
    return jsonify(cancelled=cancelled, message=message)


@bp.route("/generate/status")
@approved_required
def generate_status():
    return jsonify(job_manager.get_status(current_user))
