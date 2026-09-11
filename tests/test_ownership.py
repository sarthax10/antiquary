"""Story ownership scoping (app/studio/service.py) — the security-critical part of the
Phase 2 rework: a non-admin user must never see or touch another user's story, and an
admin must be able to see/touch everyone's for oversight. Runs against the real
DATABASE_URL (see conftest.py) with rows created/torn down per test."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.studio import service  # noqa: E402


def test_get_story_returns_own_story(make_user, make_story):
    owner = make_user()
    story = make_story(owner)
    assert service.get_story(story.id, owner) is not None


def test_get_story_hides_other_users_story(make_user, make_story):
    owner = make_user()
    other = make_user()
    story = make_story(owner)
    assert service.get_story(story.id, other) is None


def test_get_story_admin_sees_everyones(make_user, make_story):
    owner = make_user()
    admin = make_user(role="admin")
    story = make_story(owner)
    assert service.get_story(story.id, admin) is not None


def test_get_story_unknown_id_returns_none(make_user):
    user = make_user()
    assert service.get_story("nonexistent000", user) is None


def test_pending_stories_scoped_to_owner(make_user, make_story):
    a = make_user()
    b = make_user()
    story_a = make_story(a, status="pending")
    make_story(b, status="pending")

    a_pending = [s.id for s in service.pending_stories(a)]
    assert story_a.id in a_pending
    assert len(a_pending) == 1


def test_pending_stories_admin_sees_all(make_user, make_story):
    a = make_user()
    b = make_user()
    admin = make_user(role="admin")
    story_a = make_story(a, status="pending")
    story_b = make_story(b, status="pending")

    all_ids = {s.id for s in service.pending_stories(admin)}
    assert {story_a.id, story_b.id} <= all_ids


def test_decide_story_rejects_non_owner(make_user, make_story):
    owner = make_user()
    other = make_user()
    story = make_story(owner)

    result = service.decide_story(story.id, "approve", other)
    assert result is None


def test_decide_story_allows_owner(make_user, make_story):
    owner = make_user()
    story = make_story(owner)

    result = service.decide_story(story.id, "approve", owner)
    assert result is not None
    assert result.status == "approved"


def test_decide_story_allows_admin_on_others_story(make_user, make_story):
    owner = make_user()
    admin = make_user(role="admin")
    story = make_story(owner)

    result = service.decide_story(story.id, "reject", admin)
    assert result is not None
    assert result.status == "rejected"
    assert result.decided_by_id == admin.id


def test_restore_story_rejects_non_owner(make_user, make_story):
    owner = make_user()
    other = make_user()
    story = make_story(owner, status="approved")

    assert service.restore_story(story.id, other) is None


def test_restore_story_allows_owner(make_user, make_story):
    owner = make_user()
    story = make_story(owner, status="approved")

    result = service.restore_story(story.id, owner)
    assert result is not None
    assert result.status == "pending"
