"""Tests for app/gpu_worker/ — the claim/complete/fail logic (service.py) a remote
GPU-having machine drives over HTTP (routes.py) to fulfill illustration_jobs (see
Claude outputs/OPEN_ISSUES.md #66). Runs against the real DATABASE_URL, same convention
as tests/conftest.py's other fixtures — a job here is disposable/cheap to create, so
each test makes its own and cleans up directly rather than needing a shared fixture.

The HTTP layer itself (Flask routes, token header checking) is exercised at the
service-layer/pure-function level rather than through a full Flask test client — this
project's existing test suite has no precedent for spinning up a live app instance (see
tests/test_ownership.py etc., which all call service functions directly), so
_authorized()'s token comparison is tested directly instead.
"""
import os
import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_session  # noqa: E402
from app.gpu_worker import service  # noqa: E402
from app.models import IllustrationJob, utcnow  # noqa: E402


@pytest.fixture
def make_illustration_job():
    created = []

    def _make(status="pending", created_at=None):
        session = get_session()
        job = IllustrationJob(prompt="a test prompt", width=512, height=512, status=status)
        if created_at is not None:
            job.created_at = created_at
        session.add(job)
        session.commit()
        created.append(job.id)
        return job

    yield _make

    session = get_session()
    session.query(IllustrationJob).filter(IllustrationJob.id.in_(created)).delete(synchronize_session=False)
    session.commit()


def test_claim_next_job_claims_the_oldest_pending_job(make_illustration_job):
    older = make_illustration_job(created_at=utcnow() - timedelta(seconds=5))
    make_illustration_job(created_at=utcnow())

    claimed = service.claim_next_job()
    assert claimed is not None
    assert claimed.id == older.id
    assert claimed.status == "claimed"
    assert claimed.claimed_at is not None


def test_claim_next_job_returns_none_when_nothing_pending():
    assert service.claim_next_job() is None


def test_claim_next_job_ignores_a_job_past_the_ttl(make_illustration_job):
    stale = make_illustration_job(created_at=utcnow() - timedelta(seconds=service.JOB_TTL_SECONDS + 5))
    claimed = service.claim_next_job()
    assert claimed is None or claimed.id != stale.id


def test_claim_next_job_does_not_reclaim_an_already_claimed_job(make_illustration_job):
    make_illustration_job(status="claimed")
    assert service.claim_next_job() is None


def test_complete_job_uploads_and_marks_done(make_illustration_job, tmp_path, monkeypatch):
    job = make_illustration_job(status="claimed")
    uploaded = {}
    monkeypatch.setattr(service.storage, "upload_asset",
                         lambda local_path, key, content_type: uploaded.update(path=local_path, key=key))

    local_image = tmp_path / "result.png"
    local_image.write_bytes(b"fake png")
    result = service.complete_job(job.id, str(local_image))

    assert result is not None
    assert result.status == "done"
    assert result.image_object_key == f"gpu-illustrations/{job.id}.png"
    assert uploaded["key"] == f"gpu-illustrations/{job.id}.png"


def test_complete_job_returns_none_for_a_job_that_was_never_claimed(make_illustration_job, tmp_path):
    job = make_illustration_job(status="pending")
    result = service.complete_job(job.id, str(tmp_path / "x.png"))
    assert result is None


def test_complete_job_returns_none_for_an_unknown_job_id():
    assert service.complete_job("does-not-exist", "/tmp/x.png") is None


def test_fail_job_marks_failed_with_error(make_illustration_job):
    job = make_illustration_job(status="claimed")
    result = service.fail_job(job.id, "simulated OOM")
    assert result is not None
    assert result.status == "failed"
    assert result.error == "simulated OOM"


def test_fail_job_returns_none_for_a_job_that_was_never_claimed(make_illustration_job):
    job = make_illustration_job(status="pending")
    assert service.fail_job(job.id, "x") is None


# --- Token auth (routes.py's _authorized()) -------------------------------------------
# Needs a real Flask request context to read request.headers — create_app() itself has
# no DB-connectivity/secret-key requirements beyond what's already set for every other
# test in this suite (see tests/conftest.py's own "real stack" convention).

@pytest.fixture
def app():
    from app import create_app
    return create_app()


def test_authorized_true_when_header_matches_env_token(app, monkeypatch):
    from app.gpu_worker import routes
    monkeypatch.setenv("GPU_WORKER_TOKEN", "real-token-123")
    with app.test_request_context(headers={"X-Worker-Token": "real-token-123"}):
        assert routes._authorized() is True


def test_authorized_false_when_header_missing(app, monkeypatch):
    from app.gpu_worker import routes
    monkeypatch.setenv("GPU_WORKER_TOKEN", "real-token-123")
    with app.test_request_context():
        assert routes._authorized() is False


def test_authorized_false_when_header_wrong(app, monkeypatch):
    from app.gpu_worker import routes
    monkeypatch.setenv("GPU_WORKER_TOKEN", "real-token-123")
    with app.test_request_context(headers={"X-Worker-Token": "wrong"}):
        assert routes._authorized() is False


def test_authorized_false_when_no_token_configured(app, monkeypatch):
    from app.gpu_worker import routes
    monkeypatch.delenv("GPU_WORKER_TOKEN", raising=False)
    with app.test_request_context(headers={"X-Worker-Token": "anything"}):
        assert routes._authorized() is False


def test_next_job_endpoint_disabled_without_token_configured(app, monkeypatch):
    monkeypatch.delenv("GPU_WORKER_TOKEN", raising=False)
    client = app.test_client()
    resp = client.get("/api/gpu-worker/jobs/next")
    assert resp.status_code == 503


def test_next_job_endpoint_rejects_missing_auth(app, monkeypatch):
    monkeypatch.setenv("GPU_WORKER_TOKEN", "real-token-123")
    client = app.test_client()
    resp = client.get("/api/gpu-worker/jobs/next")
    assert resp.status_code == 401


def test_next_job_endpoint_returns_null_job_when_nothing_pending(app, monkeypatch):
    monkeypatch.setenv("GPU_WORKER_TOKEN", "real-token-123")
    client = app.test_client()
    resp = client.get("/api/gpu-worker/jobs/next", headers={"X-Worker-Token": "real-token-123"})
    assert resp.status_code == 200
    assert resp.get_json()["job"] is None


def test_next_job_endpoint_returns_and_claims_a_real_pending_job(app, monkeypatch, make_illustration_job):
    monkeypatch.setenv("GPU_WORKER_TOKEN", "real-token-123")
    job = make_illustration_job()
    client = app.test_client()
    resp = client.get("/api/gpu-worker/jobs/next", headers={"X-Worker-Token": "real-token-123"})
    assert resp.status_code == 200
    body = resp.get_json()["job"]
    assert body["id"] == job.id
    assert body["prompt"] == "a test prompt"

    session = get_session()
    session.expire_all()
    refreshed = session.get(IllustrationJob, job.id)
    assert refreshed.status == "claimed"
