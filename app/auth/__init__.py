from app.extensions import login_manager

from . import service
from .routes import bp


@login_manager.user_loader
def load_user(session_id: str):
    # Runs fresh on every request (no caching), so a status change (e.g. admin
    # suspends a user mid-session) takes effect on that user's very next request.
    # session_id is "<user id>:<session_version at login time>" (see User.get_id()) —
    # a mismatched version means the password changed since this cookie was issued, so
    # it's treated the same as an invalid/expired session (returning None logs it out)
    # rather than silently trusting a stale cookie forever.
    try:
        user_id_str, version_str = session_id.split(":", 1)
        user_id, version = int(user_id_str), int(version_str)
    except ValueError:
        return None
    user = service.get_user_by_id(user_id)
    if user is None or user.session_version != version:
        return None
    return user


@login_manager.unauthorized_handler
def unauthorized():
    from flask import jsonify
    return jsonify(error="not_authenticated"), 401


__all__ = ["bp"]
