"""YouTube OAuth (Google) — hand-rolled against Google's plain REST endpoints rather
than pulling in google-api-python-client, matching this project's existing preference
for direct HTTP calls (see pipeline/generate_script.py's Ollama client) over heavy SDKs.

YOUTUBE_CLIENT_ID/SECRET identify Antiquary itself to Google (one OAuth client,
registered once in Google Cloud Console — see docs/DEPLOYMENT.md) — not any individual
user's credential. Each user's own access/refresh token is what gets stored per-row in
SocialAccount, via app/social/service.py.
"""
import os
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests

from app.models.base import utcnow

CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

# Requested once at connect time (not just "upload") so later phases (publishing,
# performance-metrics polling) never need to re-prompt the user for consent.
# youtube.readonly is required even just to identify which channel we're talking to
# (fetch_channel()'s channels.list?mine=true call) — youtube.upload alone grants write
# access but not read, and 403s on that call with ACCESS_TOKEN_SCOPE_INSUFFICIENT.
SCOPES = " ".join([
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
])


def is_configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET)


def build_auth_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",  # required to get a refresh_token back
        "prompt": "consent",       # forces a fresh refresh_token even on a re-connect
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str) -> dict:
    resp = requests.post(TOKEN_URL, data={
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_channel(access_token: str) -> tuple[str, str]:
    """Returns (channel_id, channel_title) for the Google account that just authorized
    us. Raises ValueError if the account has no YouTube channel at all."""
    resp = requests.get(
        CHANNELS_URL,
        params={"part": "snippet", "mine": "true"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        raise ValueError("This Google account has no YouTube channel.")
    channel = items[0]
    return channel["id"], channel["snippet"]["title"]


def expires_at_from(token_response: dict) -> datetime | None:
    expires_in = token_response.get("expires_in")
    return utcnow() + timedelta(seconds=expires_in) if expires_in else None


def refresh_access_token(refresh_token: str) -> dict:
    """A refresh_token grant never returns a new refresh_token itself — the original
    keeps working indefinitely (until the user revokes access), only the short-lived
    access_token needs periodic renewal."""
    resp = requests.post(TOKEN_URL, data={
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def upload_video(access_token: str, file_path: str, title: str, description: str) -> tuple[str, str]:
    """Resumable upload, done in a single PUT — correct and sufficient for this app's
    ~30-45s vertical videos (a few MB, nowhere near where chunking would matter).
    Uploads as public: publishing IS the point of clicking "Publish to YouTube" on an
    already-approved story — Antiquary's own human review step (app/studio/) is the
    real gate, not a second, silent platform-level one behind it.

    Returns (video_id, video_url)."""
    file_size = os.path.getsize(file_path)
    init_resp = requests.post(
        UPLOAD_URL,
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(file_size),
        },
        json={
            "snippet": {"title": title[:100], "description": description[:5000]},
            "status": {"privacyStatus": "public"},
        },
        timeout=15,
    )
    init_resp.raise_for_status()
    upload_url = init_resp.headers["Location"]

    with open(file_path, "rb") as f:
        put_resp = requests.put(
            upload_url,
            headers={"Content-Type": "video/mp4", "Content-Length": str(file_size)},
            data=f,
            timeout=300,
        )
    put_resp.raise_for_status()
    video_id = put_resp.json()["id"]
    return video_id, f"https://www.youtube.com/watch?v={video_id}"
