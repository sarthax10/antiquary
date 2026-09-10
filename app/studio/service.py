"""Business logic for the actual product: stories waiting for review, decided ones,
and the recent-activity feed on the Create screen. All querying lives here — routes.py
never touches the DB session directly."""
from app.db import get_session
from app.models import Story, User, utcnow
from app.storage import presigned_video_url


def pending_stories() -> list[Story]:
    return (
        get_session().query(Story)
        .filter_by(status="pending")
        .order_by(Story.created_at.asc())  # oldest first — review in the order received
        .all()
    )


def decided_stories(status: str) -> list[Story]:
    return (
        get_session().query(Story)
        .filter_by(status=status)
        .order_by(Story.decided_at.desc().nullslast(), Story.created_at.desc())
        .all()
    )


def recent_stories(limit: int = 8) -> list[Story]:
    return get_session().query(Story).order_by(Story.created_at.desc()).limit(limit).all()


def get_story(story_id: str) -> Story | None:
    return get_session().get(Story, story_id)


def decide_story(story_id: str, action: str, decided_by: User) -> Story | None:
    if action not in ("approve", "reject"):
        raise ValueError(f"invalid action: {action}")
    session = get_session()
    story = session.get(Story, story_id)
    if story is None:
        return None
    story.status = "approved" if action == "approve" else "rejected"
    story.decided_at = utcnow()
    story.decided_by_id = decided_by.id
    session.commit()
    return story


def restore_story(story_id: str) -> Story | None:
    session = get_session()
    story = session.get(Story, story_id)
    if story is None:
        return None
    story.status = "pending"
    story.decided_at = None
    story.decided_by_id = None
    session.commit()
    return story


def video_url(story: Story) -> str | None:
    if not story.video_object_key:
        return None
    return presigned_video_url(story.video_object_key)
