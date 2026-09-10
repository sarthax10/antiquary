"""All configuration comes from environment variables — nothing here is a secret,
nothing here is hardcoded for a specific environment. See .env.example for every var
this app reads."""
import os


class Config:
    SECRET_KEY = os.environ["SECRET_KEY"]
    DATABASE_URL = os.environ["DATABASE_URL"]

    # Cookie security — FORCE_HTTPS=0 for local dev over plain http, 1 once Caddy is
    # terminating real TLS in front of this app. Login over plain HTTP is not
    # acceptable once this is public, so production must set this.
    FORCE_HTTPS = os.environ.get("FORCE_HTTPS", "0") == "1"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    WTF_CSRF_ENABLED = True

    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

    @property
    def SESSION_COOKIE_SECURE(self) -> bool:  # noqa: N802 (Flask's own casing convention)
        return self.FORCE_HTTPS


def load_config() -> Config:
    return Config()
