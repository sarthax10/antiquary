"""Business logic for the actual product: stories waiting for review, decided ones,
and the recent-activity feed on the Create screen. All querying lives here — routes.py
never touches the DB session directly.

Every read/write here is scoped to the requesting user's own stories, with admins
seeing (and able to decide/restore) everyone's — the review desk is per-user, not a
shared pool, except for the admin oversight bypass. See docs/ARCHITECTURE.md."""
from app.db import get_session
from app.models import Story, User, utcnow


def _scoped(query, user: User):
    return query if user.is_admin else query.filter_by(created_by_id=user.id)


def pending_stories(user: User) -> list[Story]:
    query = get_session().query(Story).filter_by(status="pending")
    return (
        _scoped(query, user)
        .order_by(Story.created_at.asc())  # oldest first — review in the order received
        .all()
    )


def decided_stories(status: str, user: User) -> list[Story]:
    query = get_session().query(Story).filter_by(status=status)
    return (
        _scoped(query, user)
        .order_by(Story.decided_at.desc().nullslast(), Story.created_at.desc())
        .all()
    )


def recent_stories(user: User, limit: int = 8) -> list[Story]:
    query = get_session().query(Story)
    return _scoped(query, user).order_by(Story.created_at.desc()).limit(limit).all()


def get_story(story_id: str, user: User) -> Story | None:
    """Returns None both when the story doesn't exist and when it exists but isn't
    this user's (and they're not admin) — a non-owner gets the same 404 an unknown id
    would, rather than a 403 that would confirm the id is real."""
    story = get_session().get(Story, story_id)
    if story is None:
        return None
    if not user.is_admin and story.created_by_id != user.id:
        return None
    return story


def decide_story(story_id: str, action: str, decided_by: User) -> Story | None:
    if action not in ("approve", "reject"):
        raise ValueError(f"invalid action: {action}")
    story = get_story(story_id, decided_by)
    if story is None:
        return None
    story.status = "approved" if action == "approve" else "rejected"
    story.decided_at = utcnow()
    story.decided_by_id = decided_by.id
    get_session().commit()
    return story


def restore_story(story_id: str, user: User) -> Story | None:
    story = get_story(story_id, user)
    if story is None:
        return None
    story.status = "pending"
    story.decided_at = None
    story.decided_by_id = None
    get_session().commit()
    return story


def video_url(story: Story) -> str | None:
    # Same-origin path the app itself serves (see studio.routes.story_video) — not a
    # direct MinIO link, since MinIO stays internal-only.
    if not story.video_object_key:
        return None
    return f"/api/stories/{story.id}/video"
