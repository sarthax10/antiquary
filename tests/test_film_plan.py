"""Tests for pipeline/film_plan.py — the FilmPlan schema and its v0 projections (see
Claude outputs/FILM_PLAN_ARCHITECTURE.md Milestone 1). The load-bearing tests here are
the real-data round-trips: from_beats_v0()/to_beats_v0() must reproduce ACTUAL real
Story.beats content pulled from the real database, not just a synthesized example —
this is the same "verify against the real stack" discipline used everywhere else in
this project, applied to a schema instead of a render.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import pytest

import film_plan as fp  # noqa: E402


# --- Synthesized round-trips (fast, no DB needed) ------------------------------------

def test_from_beats_v0_minimal_shape_round_trips_through_to_beats_v0():
    # Story.beats' REAL persisted shape (confirmed this session, per enqueue_story.py):
    # just text/visual_query/entity_type, nothing else.
    beats = [
        {"text": "First sentence.", "visual_query": "a river", "entity_type": "scene"},
        {"text": "Second sentence.", "visual_query": "Napoleon portrait", "entity_type": "person"},
    ]
    plan = fp.from_beats_v0(beats)
    assert len(plan.scenes) == 2
    assert plan.scenes[0].narration == "First sentence."
    assert plan.scenes[1].shots[0].entity_type == "person"

    round_tripped = fp.to_beats_v0(plan)
    assert round_tripped == beats


def test_from_beats_v0_full_render_ready_shape_round_trips_through_to_beats_final():
    # run_pipeline.py's REAL beats_final shape — every field render.render() actually
    # reads today.
    beats = [{
        "path": "/tmp/img_00.jpg", "entity_type": "person", "face": [0.5, 0.3],
        "duration": 3.2, "text": "Caesar crossed the Rubicon.",
        "visual_query": "Julius Caesar portrait", "framing": "push_in",
    }]
    plan = fp.from_beats_v0(beats)
    round_tripped = fp.to_beats_final(plan)
    assert round_tripped == beats


def test_from_beats_v0_single_shot_per_scene_always():
    beats = [{"text": "x", "visual_query": "y", "entity_type": "scene"}]
    plan = fp.from_beats_v0(beats)
    assert len(plan.scenes[0].shots) == 1
    assert plan.scenes[0].primary_shot is plan.scenes[0].shots[0]


def test_from_beats_v0_missing_framing_defaults_to_hold_static():
    beats = [{"text": "x", "visual_query": "y", "entity_type": "scene"}]  # no framing key at all
    plan = fp.from_beats_v0(beats)
    assert plan.scenes[0].shots[0].framing == fp.DEFAULT_FRAMING == "hold_static"


def test_to_beats_v0_collapses_a_multi_shot_scene_to_its_primary_shot():
    scene = fp.Scene(
        scene_id="scene_00",
        narration="Two shots, one v0 beat.",
        shots=[
            fp.Shot(shot_id="s0", scene_id="scene_00", visual_query="first", entity_type="place"),
            fp.Shot(shot_id="s1", scene_id="scene_00", visual_query="second", entity_type="artifact"),
        ],
    )
    plan = fp.FilmPlan(scenes=[scene])
    beats = fp.to_beats_v0(plan)
    assert len(beats) == 1
    assert beats[0]["visual_query"] == "first"  # the primary (first) shot, not the second


def test_to_beats_v0_empty_shots_list_does_not_crash():
    # A malformed/edge-case scene with no shots at all — primary_shot handles this
    # (returns None) rather than the projection raising.
    plan = fp.FilmPlan(scenes=[fp.Scene(scene_id="scene_00", narration="no shots here")])
    beats = fp.to_beats_v0(plan)
    assert beats == [{"text": "no shots here", "visual_query": "", "entity_type": "scene"}]


# --- Dict round-trip (FilmPlan.to_dict / from_dict, the real JSONB storage shape) ----

def test_film_plan_to_dict_from_dict_round_trip():
    beats = [
        {"text": "a", "visual_query": "b", "entity_type": "place", "framing": "pan"},
        {"text": "c", "visual_query": "d", "entity_type": "event"},
    ]
    plan = fp.from_beats_v0(beats, title="A Real Title")
    d = plan.to_dict()
    restored = fp.FilmPlan.from_dict(d)
    assert restored.title == "A Real Title"
    assert [s.narration for s in restored.scenes] == [s.narration for s in plan.scenes]
    assert restored.scenes[0].shots[0].framing == "pan"


def test_film_plan_to_dict_is_json_serializable():
    import json
    plan = fp.from_beats_v0([{"text": "x", "visual_query": "y", "entity_type": "scene"}])
    json.dumps(plan.to_dict())  # must not raise


# --- Defensive validation — same pattern as entity_type/framing elsewhere -----------

def test_scene_from_dict_rejects_invalid_purpose():
    scene = fp.Scene.from_dict({"scene_id": "s", "purpose": "not_a_real_purpose"})
    assert scene.purpose == fp.DEFAULT_PURPOSE


def test_scene_from_dict_rejects_invalid_transition():
    scene = fp.Scene.from_dict({"scene_id": "s", "transition_in": "explode"})
    assert scene.transition_in == fp.DEFAULT_TRANSITION


def test_scene_from_dict_rejects_invalid_music_cue():
    scene = fp.Scene.from_dict({"scene_id": "s", "music_cue": "maximum_intensity_always"})
    assert scene.music_cue == fp.DEFAULT_MUSIC_CUE


def test_shot_from_dict_rejects_invalid_shot_type():
    shot = fp.Shot.from_dict({"scene_id": "s", "shot_type": "dutch_angle_drone_flip"})
    assert shot.shot_type == fp.DEFAULT_SHOT_TYPE


def test_typography_cue_from_dict_rejects_invalid_role():
    cue = fp.TypographyCue.from_dict({"role": "giant_karaoke_caption", "content": "x"})
    assert cue.role == "narration_caption"


def test_typography_cue_from_dict_none_when_absent():
    assert fp.TypographyCue.from_dict(None) is None
    assert fp.TypographyCue.from_dict({}) is None


# --- Real database round-trip — the load-bearing test -------------------------------

def test_from_beats_v0_round_trips_real_stories_from_the_real_database():
    # Pulls REAL Story.beats content from the real DATABASE_URL (same DB the app
    # itself uses — this project's own testing convention, see tests/conftest.py) and
    # confirms the projection is byte-identical, not just "doesn't crash." Skips
    # (doesn't fail the suite) if there are no real stories with beats yet, rather than
    # asserting against nothing.
    from app.db import get_session
    from app.models import Story

    session = get_session()
    stories = (
        session.query(Story)
        .filter(Story.beats != [])
        .order_by(Story.created_at.desc())
        .limit(5)
        .all()
    )
    if not stories:
        pytest.skip("no real stories with beats in the database to round-trip against")

    for story in stories:
        plan = fp.from_beats_v0(story.beats, title=story.title)
        round_tripped = fp.to_beats_v0(plan)
        assert round_tripped == story.beats, f"round-trip mismatch for real story {story.id}"
