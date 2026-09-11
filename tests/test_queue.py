"""Generation queue logic (app/generation/job_manager.py) — the Phase 3 rework: a second
`start()` while one is running enqueues instead of erroring, FIFO ordering is preserved
even when a job finishes between two start() calls, and cancel() prioritizes the caller's
own job over the admin-oversight bypass (a real bug caught via live testing: an admin's
own "leave queue" action was killing someone else's running job instead of their own
queued one).

Runs against the real DATABASE_URL (see conftest.py). _spawn is monkeypatched to a no-op
everywhere here — these tests must never launch a real pipeline subprocess. Because the
"one running job" invariant (a partial unique DB index) is global across the whole table,
these tests skip outright if something is genuinely running system-wide, rather than
risk colliding with it."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_session  # noqa: E402
from app.generation import job_manager  # noqa: E402


class _FakeProc:
    """Stands in for subprocess.Popen so cancel() takes its fast, non-polling path
    (proc.terminate()/wait()) instead of the slow PID-polling fallback, which would
    otherwise burn several real seconds per test waiting for a fake PID to "die"."""

    def terminate(self):
        pass

    def wait(self, timeout=None):
        pass

    def kill(self):
        pass


@pytest.fixture(autouse=True)
def _no_real_subprocess(monkeypatch):
    def _fake_spawn(job):
        job.pid = 424242  # never a real process — only meaningful because _pid_alive is patched below
        job_manager._current_proc = _FakeProc()
        get_session().commit()

    monkeypatch.setattr(job_manager, "_spawn", _fake_spawn)
    # Without this, get_status()'s self-heal sees a PID that (correctly) isn't a real
    # running process and marks the job "error" before the test ever gets to assert
    # anything about "running"/"queued" state.
    monkeypatch.setattr(job_manager, "_pid_alive", lambda pid: True)
    job_manager._current_proc = None
    yield
    job_manager._current_proc = None


@pytest.fixture(autouse=True)
def _skip_if_something_really_running():
    if job_manager._running_job() is not None:
        pytest.skip("a real generation is running system-wide — would collide with the one-running-job invariant")


def test_start_second_user_enqueues_instead_of_erroring(make_user):
    a = make_user()
    b = make_user()

    started_a, msg_a = job_manager.start("topic a", a)
    assert started_a and msg_a == "started"

    started_b, msg_b = job_manager.start("topic b", b)
    assert started_b and "queued" in msg_b

    status_b = job_manager.get_status(b)
    assert status_b["status"] == "queued"
    assert status_b["queue_position"] == 1


def test_start_refuses_second_job_for_same_user(make_user):
    a = make_user()
    job_manager.start("first", a)
    started_again, msg = job_manager.start("second", a)
    assert started_again is False
    assert "already have" in msg


def test_get_status_promotes_oldest_queued_job(make_user):
    a = make_user()
    b = make_user()
    job_manager.start("topic a", a)
    job_manager.start("topic b", b)

    # Nothing has cancelled a's job — b should still be queued, not promoted.
    assert job_manager.get_status(b)["status"] == "queued"

    job_manager.cancel(a)
    # The next status check is what performs promotion (piggybacking on polling).
    status_b = job_manager.get_status(b)
    assert status_b["status"] == "running"


def test_fifo_order_preserved_across_three_users(make_user):
    a, b, c = make_user(), make_user(), make_user()
    job_manager.start("a", a)
    job_manager.start("b", b)
    job_manager.start("c", c)

    assert job_manager.get_status(b)["queue_position"] == 1
    assert job_manager.get_status(c)["queue_position"] == 2

    job_manager.cancel(a)
    job_manager.get_status(b)  # triggers promotion of b
    assert job_manager.get_status(b)["status"] == "running"
    assert job_manager.get_status(c)["queue_position"] == 1


def test_cancel_own_queued_job_does_not_touch_someone_elses_running_job(make_user):
    """Regression test for the exact bug caught via live browser testing: an admin
    (or anyone) with their own job queued behind someone else's running job must have
    "cancel" cancel THEIR OWN queued job, not the other person's running one — even
    though the admin bypass would otherwise match any running job."""
    runner = make_user()
    admin = make_user(role="admin")

    job_manager.start("runner's topic", runner)
    job_manager.start("admin's topic", admin)
    assert job_manager.get_status(admin)["status"] == "queued"

    cancelled, message = job_manager.cancel(admin)
    assert cancelled is True

    assert job_manager.get_status(runner)["status"] == "running"
    assert job_manager.get_status(admin)["status"] == "cancelled"


def test_admin_can_cancel_others_running_job_when_admin_has_nothing_queued(make_user):
    runner = make_user()
    admin = make_user(role="admin")

    job_manager.start("runner's topic", runner)
    cancelled, message = job_manager.cancel(admin)
    assert cancelled is True
    assert job_manager.get_status(runner)["status"] == "cancelled"


def test_non_admin_cannot_cancel_someone_elses_running_job(make_user):
    runner = make_user()
    bystander = make_user()

    job_manager.start("runner's topic", runner)
    cancelled, message = job_manager.cancel(bystander)
    assert cancelled is False
    assert message == "forbidden"
    assert job_manager.get_status(runner)["status"] == "running"
