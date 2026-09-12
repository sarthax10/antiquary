"""Editor API: /api/stories/<id>/editor/* — the first real, visible slice of the
timeline editor (Phase B). See app/editor/service.py for what this deliberately does and
doesn't do yet."""
from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.auth.decorators import approved_required

from . import service

bp = Blueprint("editor", __name__, url_prefix="/api")


@bp.route("/stories/<story_id>/editor")
@approved_required
def get_editor_timeline(story_id):
    timeline = service.get_timeline(story_id, current_user)
    if timeline is None:
        return jsonify(error="not found"), 404
    return jsonify(timeline=timeline, render=service.render_status(story_id))


@bp.route("/stories/<story_id>/editor/captions/<cap_id>", methods=["PATCH"])
@approved_required
def update_caption(story_id, cap_id):
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify(error="text is required"), 400
    timeline = service.update_caption(story_id, cap_id, text, current_user)
    if timeline is None:
        return jsonify(error="not found"), 404
    return jsonify(timeline=timeline)


@bp.route("/stories/<story_id>/editor/render", methods=["POST"])
@approved_required
def start_render(story_id):
    started, message = service.start_render(story_id, current_user)
    if not started and message == "not found":
        return jsonify(error="not found"), 404
    return jsonify(started=started, message=message), (202 if started else 409)


@bp.route("/stories/<story_id>/editor/render/status")
@approved_required
def get_render_status(story_id):
    # Confirms the story exists and is this user's before revealing status — same
    # 404-not-403 pattern used everywhere else in this app.
    if service.get_timeline(story_id, current_user) is None:
        return jsonify(error="not found"), 404
    return jsonify(service.render_status(story_id))
