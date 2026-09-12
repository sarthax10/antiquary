"""Auth API: /api/auth/*. Session-cookie based (Flask-Login) — see docs/ARCHITECTURE.md
for why that's the right choice for a same-origin SPA over a JWT-in-localStorage
approach."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import generate_csrf

from app.extensions import limiter

from . import service
from .decorators import admin_required

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _user_json(user):
    return {"id": user.id, "email": user.email, "role": user.role, "status": user.status}


@bp.route("/csrf")
def csrf():
    """The React app fetches this once on load and attaches the token as an
    X-CSRFToken header on every subsequent mutating request."""
    return jsonify(csrf_token=generate_csrf())


@bp.route("/me")
def me():
    if not current_user.is_authenticated:
        return jsonify(user=None)
    return jsonify(user=_user_json(current_user))


@bp.route("/signup", methods=["POST"])
@limiter.limit("5 per hour")
def signup():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if not service.is_valid_email(email):
        return jsonify(error="Enter a valid email address."), 400
    pw_error = service.password_error(password)
    if pw_error:
        return jsonify(error=pw_error), 400
    if service.get_user_by_email(email):
        return jsonify(error="An account with this email already exists."), 409

    service.create_signup_request(email, password)
    return jsonify(message="Request received — an admin will review it shortly."), 201


@bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    data = request.get_json(silent=True) or {}
    user, error = service.authenticate(data.get("email", ""), data.get("password", ""))
    if error:
        return jsonify(error=error), 401
    login_user(user)
    return jsonify(user=_user_json(user))


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return jsonify(message="Logged out.")


@bp.route("/change-password", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def change_password():
    data = request.get_json(silent=True) or {}
    error = service.change_password(
        current_user, data.get("current_password") or "", data.get("new_password") or ""
    )
    if error:
        return jsonify(error=error), 400
    # change_password() just bumped session_version, which would otherwise invalidate
    # this very session on its next request too — re-issue the session cookie with the
    # new version so the browser that just proved its identity stays logged in; every
    # other session (stolen cookie, another device) has no such refresh and stays dead.
    login_user(current_user)
    return jsonify(message="Password updated.")


@bp.route("/admin-check")
@admin_required
def admin_check():
    """Used by Caddy's forward_auth in front of /stats (Netdata) — being logged into
    Antiquary as an admin, via the same session cookie, is the only credential needed
    to see server metrics. No separate password to manage. Empty 204: forward_auth only
    looks at the status code, and the cookie's already same-origin/same-request."""
    return "", 204
