"""Publishing API: /api/publish/<story_id> — start a publish attempt (using the
current user's own connected account for that platform) and list attempts for a story.
Every route requires an approved, logged-in user, same as app/studio/routes.py — any
approved user can publish any approved story, but only through their own account."""
from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.auth.decorators import approved_required
from app.models import Publication, VALID_SOCIAL_PLATFORMS
from app.social import service as social_service

from . import manager

bp = Blueprint("publishing", __name__, url_prefix="/api/publish")


def _publication_json(pub: Publication) -> dict:
    return {
        "id": pub.id,
        "story_id": pub.story_id,
        "platform": pub.platform,
        "status": pub.status,
        "stage": pub.stage,
        "external_id": pub.external_id,
        "external_url": pub.external_url,
        "error": pub.error,
        "created_at": pub.created_at.isoformat() if pub.created_at else None,
        "published_at": pub.published_at.isoformat() if pub.published_at else None,
    }


@bp.route("/<story_id>")
@approved_required
def list_publications(story_id):
    pubs = manager.get_publications_for_story(story_id)
    return jsonify(publications=[_publication_json(p) for p in pubs])


@bp.route("/<story_id>", methods=["POST"])
@approved_required
def publish(story_id):
    data = request.get_json(silent=True) or {}
    platform = data.get("platform")
    if platform not in VALID_SOCIAL_PLATFORMS:
        return jsonify(error=f"platform must be one of {VALID_SOCIAL_PLATFORMS}"), 400

    account = social_service.get_account(current_user.id, platform)
    if account is None:
        return jsonify(error=f"Connect your {platform} account first."), 400

    started, message, pub = manager.start_publish(story_id, platform, account, requested_by=current_user)
    return jsonify(started=started, message=message, publication=_publication_json(pub) if pub else None)
