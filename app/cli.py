"""`flask seed-admin` — idempotently creates the admin account from ADMIN_EMAIL/
ADMIN_PASSWORD env vars, so the initial admin credential lives in the server's .env,
never in source code. Schema itself is created via `alembic upgrade head`, not here —
one path to create tables, not two.

`flask ensure-bucket` — idempotently creates the MinIO/S3 bucket videos get uploaded to
(see app/storage.py). Run once before gunicorn starts, same as seed-admin, rather than
from create_app() itself — that runs once per gunicorn worker on boot, which would race
multiple workers against the same bucket-create call for no benefit."""
import click
from flask import Flask

from app.auth import service as auth_service


def register_cli(app: Flask) -> None:
    @app.cli.command("seed-admin")
    def seed_admin():
        email = app.config.get("ADMIN_EMAIL")
        password = app.config.get("ADMIN_PASSWORD")
        if not email or not password:
            click.echo("ADMIN_EMAIL and ADMIN_PASSWORD must be set in the environment.")
            raise SystemExit(1)

        existing = auth_service.get_user_by_email(email)
        if existing:
            click.echo(f"Admin {email} already exists (status={existing.status}, role={existing.role}).")
            return

        auth_service.create_signup_request(email, password, role="admin", status="approved")
        click.echo(f"Created admin account: {email}")

    @app.cli.command("ensure-bucket")
    def ensure_bucket():
        from app import storage

        storage.ensure_bucket()
        click.echo(f"Bucket {storage.S3_BUCKET!r} ready at {storage.S3_ENDPOINT_URL}.")
