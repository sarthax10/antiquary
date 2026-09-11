"""Social account connections: /api/social/* — OAuth connect/callback per platform,
list/disconnect for the current user's own connected accounts. This is only the
connect/disconnect round-trip; actually publishing with these accounts is a later phase.

APP_BASE_URL is the origin the browser sees the SPA at (http://localhost:5173 in local
dev, the real domain in production) — used to build the redirect_uri sent to Google and
the final redirect back to the frontend. Derived deliberately from this env var rather
than the incoming request's Host header: Vite's dev proxy runs with changeOrigin=true,
so Flask would otherwise see Host: localhost:8787 even though the browser is on :5173,
producing a redirect_uri that doesn't match what's registered with Google."""
import os
import secrets

from flask import Blueprint, current_app, jsonify, redirect, request, session
from flask_login import current_user
from requests.exceptions import RequestException

from app.auth.decorators import approved_required

from . import service, youtube

bp = Blueprint("social", __name__, url_prefix="/api/social")

APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5173")
_FRONTEND_RETURN_PATH = "/connections"


def _account_json(account) -> dict:
    return {
        "id": account.id,
        "platform": account.platform,
        "external_account_name": account.external_account_name,
        "connected_at": account.connected_at.isoformat() if account.connected_at else None,
    }


@bp.route("/accounts")
@approved_required
def list_accounts():
    accounts = service.get_accounts_for_user(current_user.id)
    return jsonify(accounts=[_account_json(a) for a in accounts])


@bp.route("/accounts/<int:account_id>", methods=["DELETE"])
@approved_required
def disconnect_account(account_id):
    deleted = service.delete_account(current_user.id, account_id)
    if not deleted:
        return jsonify(error="not found"), 404
    return jsonify(disconnected=True)


@bp.route("/youtube/connect")
@approved_required
def youtube_connect():
    if not youtube.is_configured():
        # Redirect rather than a JSON error: this is a full-page navigation (the user
        # clicked a plain link, not something the SPA fetched), so a JSON body would
        # just strand them on a bare API response instead of back in the app.
        return redirect(f"{APP_BASE_URL}{_FRONTEND_RETURN_PATH}?error=youtube_not_configured")

    state = secrets.token_urlsafe(24)
    session["youtube_oauth_state"] = state
    redirect_uri = f"{APP_BASE_URL}/api/social/youtube/callback"
    return redirect(youtube.build_auth_url(redirect_uri, state))


@bp.route("/youtube/callback")
@approved_required
def youtube_callback():
    error = request.args.get("error")
    if error:
        return redirect(f"{APP_BASE_URL}{_FRONTEND_RETURN_PATH}?error={error}")

    state = request.args.get("state")
    if not state or state != session.pop("youtube_oauth_state", None):
        return redirect(f"{APP_BASE_URL}{_FRONTEND_RETURN_PATH}?error=invalid_state")

    code = request.args.get("code")
    redirect_uri = f"{APP_BASE_URL}/api/social/youtube/callback"
    try:
        token_data = youtube.exchange_code(code, redirect_uri)
        channel_id, channel_title = youtube.fetch_channel(token_data["access_token"])
    except RequestException as exc:
        # Google's error body (e.g. "redirect_uri_mismatch", "invalid_grant") is the
        # actual useful signal here — logged server-side, never shown to the user, who
        # can't act on it anyway. Without this, a misconfigured client/redirect just
        # looks like an opaque failure with no way to diagnose it from the app's UI.
        body = exc.response.text if exc.response is not None else str(exc)
        current_app.logger.error("YouTube OAuth callback failed: %s", body)
        return redirect(f"{APP_BASE_URL}{_FRONTEND_RETURN_PATH}?error=youtube_connect_failed")
    except (ValueError, KeyError) as exc:
        current_app.logger.error("YouTube OAuth callback failed: %s", exc)
        return redirect(f"{APP_BASE_URL}{_FRONTEND_RETURN_PATH}?error=youtube_connect_failed")

    service.save_account(
        user_id=current_user.id,
        platform="youtube",
        external_account_id=channel_id,
        external_account_name=channel_title,
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_expires_at=youtube.expires_at_from(token_data),
        scopes=token_data.get("scope", youtube.SCOPES),
    )
    return redirect(f"{APP_BASE_URL}{_FRONTEND_RETURN_PATH}?connected=youtube")
