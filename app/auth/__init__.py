from app.extensions import login_manager

from . import service
from .routes import bp


@login_manager.user_loader
def load_user(user_id: str):
    # Runs fresh on every request (no caching), so a status change (e.g. admin
    # suspends a user mid-session) takes effect on that user's very next request.
    return service.get_user_by_id(int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    from flask import jsonify
    return jsonify(error="not_authenticated"), 401


__all__ = ["bp"]
