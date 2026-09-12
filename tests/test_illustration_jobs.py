"""Tests for pipeline/illustration_jobs.py — the server-side client fetch_visuals.py
uses to request a GPU illustration from a remote worker (Claude outputs/OPEN_ISSUES.md
#66). Runs against the real DATABASE_URL, same convention as tests/conftest.py.

The happy path is tested with a REAL background thread committing to the SAME real
Postgres from a separate session — genuinely exercising the "another process updates
this row, this process's poll loop picks it up" contract the real remote worker relies
on, not a mocked stand-in for it. storage.download_asset (MinIO) is mocked — that's a
separate, already-tested boundary (app/storage.py has no dedicated test file today, but
this isn't the place to add MinIO integration coverage).
"""
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import illustration_jobs as ij  # noqa: E402

from app.db import get_session  # noqa: E402
from app.models import IllustrationJob  # noqa: E402


@pytest.fixture(autouse=True)
def _fast_polling(monkeypatch):
    monkeypatch.setattr(ij, "POLL_INTERVAL", 0.1)


def _cleanup_by_prompt(prompt: str) -> None:
    session = get_session()
    session.query(IllustrationJob).filter(IllustrationJob.prompt == prompt).delete(synchronize_session=False)
    session.commit()


def test_request_illustration_returns_none_when_nothing_claims_it_in_time():
    prompt = "a test prompt that nobody will claim"
    try:
        result = ij.request_illustration(prompt, timeout=0.5)
        assert result is None

        session = get_session()
        session.expire_all()
        job = session.query(IllustrationJob).filter(IllustrationJob.prompt == prompt).first()
        assert job is not None
        assert job.status == "expired"
    finally:
        _cleanup_by_prompt(prompt)


def test_request_illustration_returns_none_when_job_is_marked_failed(monkeypatch):
    prompt = "a test prompt a worker will fail"

    def _fail_it_soon():
        deadline = time.monotonic() + 5
        job = None
        while time.monotonic() < deadline and job is None:
            time.sleep(0.05)
            session = get_session()
            job = session.query(IllustrationJob).filter(IllustrationJob.prompt == prompt).first()
        assert job is not None
        job.status = "failed"
        job.error = "simulated failure"
        get_session().commit()

    thread = threading.Thread(target=_fail_it_soon)
    thread.start()
    try:
        result = ij.request_illustration(prompt, timeout=10)
        assert result is None
    finally:
        thread.join(timeout=10)
        _cleanup_by_prompt(prompt)


def test_request_illustration_returns_bytes_when_a_worker_completes_it(monkeypatch):
    prompt = "a test prompt a worker will complete"
    image_bytes = b"fake png bytes from a real remote worker"

    def _fake_download(object_key, local_path):
        Path(local_path).write_bytes(image_bytes)

    monkeypatch.setattr(ij.storage, "download_asset", _fake_download)

    def _complete_it_soon():
        deadline = time.monotonic() + 5
        job = None
        while time.monotonic() < deadline and job is None:
            time.sleep(0.05)
            session = get_session()
            job = session.query(IllustrationJob).filter(IllustrationJob.prompt == prompt).first()
        assert job is not None
        job.status = "done"
        job.image_object_key = "gpu-illustrations/fake-test-job.png"
        get_session().commit()

    thread = threading.Thread(target=_complete_it_soon)
    thread.start()
    try:
        result = ij.request_illustration(prompt, timeout=10)
        assert result == image_bytes
    finally:
        thread.join(timeout=10)
        _cleanup_by_prompt(prompt)


def test_request_illustration_returns_none_on_download_failure(monkeypatch):
    prompt = "a test prompt whose download will fail"

    def _boom(object_key, local_path):
        raise RuntimeError("simulated MinIO error")

    monkeypatch.setattr(ij.storage, "download_asset", _boom)

    def _complete_it_soon():
        deadline = time.monotonic() + 5
        job = None
        while time.monotonic() < deadline and job is None:
            time.sleep(0.05)
            session = get_session()
            job = session.query(IllustrationJob).filter(IllustrationJob.prompt == prompt).first()
        assert job is not None
        job.status = "done"
        job.image_object_key = "gpu-illustrations/fake-test-job.png"
        get_session().commit()

    thread = threading.Thread(target=_complete_it_soon)
    thread.start()
    try:
        result = ij.request_illustration(prompt, timeout=10)
        assert result is None
    finally:
        thread.join(timeout=10)
        _cleanup_by_prompt(prompt)
