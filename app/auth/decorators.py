"""Route guards for the JSON API. Unlike a server-rendered app these never redirect —
there's no HTML page to redirect to — they return a JSON error + the right status code,
and the React app decides what to show (redirect to /login, show a "pending" screen, etc.)."""
import functools

from flask import abort, jsonify
from flask_login import current_user


def approved_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify(error="not_authenticated"), 401
        if not current_user.is_approved:
            return jsonify(error="not_approved", status=current_user.status), 403
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify(error="not_authenticated"), 401
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped
