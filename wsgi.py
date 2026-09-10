"""Gunicorn entrypoint: `gunicorn wsgi:app`. Also runnable directly for local dev
(`python wsgi.py`) — same app either way, since create_app() is the single source of
truth for wiring."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8787, debug=False)
