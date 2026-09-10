"""Admin API: /api/admin/*. Every route here requires the admin role
(app.auth.decorators.admin_required) — this is the user-approval gate the whole
signup flow depends on."""
from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.auth.decorators import admin_required
from app.models import VALID_USER_STATUSES

from . import service

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _user_json(user):
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "created_at": user.created_at.isoformat(),
        "approved_at": user.approved_at.isoformat() if user.approved_at else None,
    }


@bp.route("/users")
@admin_required
def list_users():
    status = request.args.get("status")
    if status and status not in VALID_USER_STATUSES:
        return jsonify(error="invalid status filter"), 400
    users = service.list_users(status=status)
    return jsonify(users=[_user_json(u) for u in users])


@bp.route("/users/<int:user_id>/status", methods=["POST"])
@admin_required
def update_user_status(user_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in VALID_USER_STATUSES:
        return jsonify(error="invalid status"), 400
    # An admin can't demote/reject/suspend their own account — without this, the only
    # admin could lock themselves (and everyone waiting for approval) out entirely,
    # with no one left who can reverse it. A frontend-only guard here would be
    # trivially bypassed by calling this endpoint directly, so it belongs here.
    if user_id == current_user.id and status != "approved":
        return jsonify(error="you can't change your own account's status"), 400
    user = service.set_user_status(user_id, status, approved_by=current_user)
    if user is None:
        return jsonify(error="not found"), 404
    return jsonify(user=_user_json(user))
