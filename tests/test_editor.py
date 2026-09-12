"""Tests for app/editor/service.py — the first slice of the timeline editor (Phase B,
see Claude outputs/OPEN_ISSUES.md #3).

test_update_caption_actually_persists_to_the_database is a deliberate regression test
for a real bug caught live this session: the original update_caption() mutated the
already-loaded timeline dict in place, then did `story.timeline = timeline` (the same
object, by reference) and committed — which returned the correctly-edited dict from the
function, but never actually wrote anything to Postgres. SQLAlchemy's flush decides
whether to include a column in the UPDATE by comparing its own before/after history for
that column; since "before" and "after" were the literal same object, they compared
equal and the column was silently dropped from the UPDATE despite the object showing up
in session.dirty. flag_modified() is the actual fix. A test that only checks the
function's *return value* would not have caught this — this one forces a real re-read
from the database (session.expire_all() then re-fetch) instead of trusting the
in-memory object.
"""
from sqlalchemy.orm.attributes import flag_modified

from app.db import get_session
from app.editor import service as editor_service
from app.models import Story


def _timeline_with_caption(cap_id="cap_00", text="Original caption"):
    return {
        "version": 1,
        "duration": 5.0,
        "tracks": {
            "visual": [{"id": "clip_00", "kind": "image", "start": 0, "duration": 5.0, "object_key": "x"}],
            "narration": [{"id": "beat_00", "start": 0, "duration": 5.0, "text": "x", "object_key": "y"}],
            "captions": [{
                "id": cap_id, "text": text, "start": 0, "end": 1, "emphasis": False,
                "words": [{"word": "Original", "start": 0, "end": 0.5}],
            }],
            "music": None,
        },
        "style": {"caption_font": "Anton", "caption_uppercase": True, "voice": "en-US-GuyNeural"},
    }


def _seed_timeline(story):
    story.timeline = _timeline_with_caption()
    flag_modified(story, "timeline")
    get_session().commit()


def test_update_caption_actually_persists_to_the_database(make_user, make_story):
    owner = make_user()
    story = make_story(owner)
    _seed_timeline(story)

    result = editor_service.update_caption(story.id, "cap_00", "Edited caption text", owner)
    assert result["tracks"]["captions"][0]["text"] == "Edited caption text"

    # Force a genuine re-read from Postgres, not the identity map's in-memory object —
    # this is the part a return-value-only test would miss.
    session = get_session()
    session.expire_all()
    reloaded = session.get(Story, story.id)
    assert reloaded.timeline["tracks"]["captions"][0]["text"] == "Edited caption text"
    assert "words" not in reloaded.timeline["tracks"]["captions"][0]


def test_update_caption_rejects_non_owner(make_user, make_story):
    owner = make_user()
    other = make_user()
    story = make_story(owner)
    _seed_timeline(story)

    assert editor_service.update_caption(story.id, "cap_00", "Hacked", other) is None


def test_update_caption_unknown_caption_id_returns_none(make_user, make_story):
    owner = make_user()
    story = make_story(owner)
    _seed_timeline(story)

    assert editor_service.update_caption(story.id, "not-a-real-id", "x", owner) is None


def test_get_timeline_scoped_to_owner(make_user, make_story):
    owner = make_user()
    other = make_user()
    story = make_story(owner)
    _seed_timeline(story)

    assert editor_service.get_timeline(story.id, owner) is not None
    assert editor_service.get_timeline(story.id, other) is None
