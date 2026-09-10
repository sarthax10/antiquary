"""Application factory. This is the only place extensions and blueprints get wired to a
concrete Flask app instance — see docs/ARCHITECTURE.md for the layering this enforces.

Deliberately does NOT import blueprints/config at module level: `app.models` (and
`app.db`, `app.storage`) must be importable on their own — by Alembic, by pipeline/
scripts, by tests — without pulling in Flask, Flask-Login, or requiring SECRET_KEY to be
set. Only create_app() itself needs the full stack, so everything Flask-specific is
imported inside its body.
"""
from flask import Flask, jsonify


def create_app() -> Flask:
    from . import admin, auth, db, studio
    from .cli import register_cli
    from .config import load_config
    from .extensions import csrf, limiter, login_manager

    app = Flask(__name__, static_folder=None)  # pure JSON API — Caddy serves the built React app
    app.config.from_object(load_config())

    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(studio.bp)
    register_cli(app)

    @app.teardown_appcontext
    def _remove_db_session(_exception=None):
        db.remove_session()

    @app.after_request
    def _security_headers(response):
        # Defense in depth on top of whatever Caddy adds in front of this in production
        # — these cost nothing and matter regardless of what the reverse proxy does.
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if app.config.get("FORCE_HTTPS"):
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify(error="not found"), 404

    @app.errorhandler(403)
    def forbidden(_e):
        return jsonify(error="forbidden"), 403

    @app.errorhandler(400)
    def bad_request(_e):
        return jsonify(error="bad request"), 400

    @app.errorhandler(429)
    def rate_limited(_e):
        return jsonify(error="too many requests, slow down"), 429

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    return app
