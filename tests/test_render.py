"""Pure-function tests for pipeline/render.py's subject-continuity logic — see
OPEN_ISSUES.md audit #34: entity_type matching alone was never a real claim about two
consecutive beats being about the *same* subject (a "person" beat about Caesar followed
by a "person" beat about Brutus is a real subject change, not a continuation). No ffmpeg
invocation here; the actual filter graph is verified separately with real encodes (see
Claude outputs/OPEN_ISSUES.md for the frame-by-frame verification notes on the fixes this
session)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import render  # noqa: E402


def test_same_subject_true_for_matching_named_person():
    a = {"entity_type": "person", "visual_query": "Julius Caesar portrait bust"}
    b = {"entity_type": "person", "visual_query": "Julius Caesar statue Rome"}
    assert render._same_subject(a, b) is True


def test_same_subject_false_for_different_named_person():
    a = {"entity_type": "person", "visual_query": "Julius Caesar portrait bust"}
    b = {"entity_type": "person", "visual_query": "Marcus Brutus portrait"}
    assert render._same_subject(a, b) is False


def test_same_subject_false_when_either_query_empty():
    assert render._same_subject({"visual_query": ""}, {"visual_query": "Napoleon"}) is False
    assert render._same_subject({"visual_query": "Napoleon"}, {"visual_query": ""}) is False


def test_transition_style_same_type_different_subject_is_a_hard_cut():
    # Both "person", but genuinely different people — must NOT get the continuity
    # crossfade just because entity_type happens to match (the exact bug audit #34
    # found: matching entity_type was being treated as "same subject").
    a = {"entity_type": "person", "visual_query": "Julius Caesar"}
    b = {"entity_type": "person", "visual_query": "Marcus Brutus"}
    duration, name = render._transition_style(a, b, 0)
    assert duration == render.XFADE_CUT
    assert name == "fade"


def test_transition_style_same_type_same_subject_is_a_smooth_crossfade():
    a = {"entity_type": "person", "visual_query": "Julius Caesar portrait"}
    b = {"entity_type": "person", "visual_query": "Julius Caesar bust marble"}
    duration, name = render._transition_style(a, b, 0)
    assert duration == render.XFADE_SMOOTH
    assert name == "smoothleft"


def test_transition_style_person_to_place_is_an_accent_transition():
    a = {"entity_type": "person", "visual_query": "Napoleon Bonaparte"}
    b = {"entity_type": "place", "visual_query": "Battle of Waterloo field"}
    duration, name = render._transition_style(a, b, 0)
    assert duration == render.XFADE_SMOOTH
    assert name == "radial"


# --- Mood classification (Professional Quality Roadmap Tier 3 #11) ------------------
# Whole-word matching, not substring: see render._classify_mood's own docstring for why
# ("war" must not fire on "warm"/"warrior"). Real word lists are exercised here, not
# mocked out, since a wrong word list is exactly the kind of bug these tests should
# actually catch.

def test_classify_mood_tense_from_real_narration_words():
    beats = [{"text": "The general was captured and executed after the brutal siege."}]
    assert render._classify_mood(beats) == "tense"


def test_classify_mood_somber_from_real_narration_words():
    beats = [{"text": "He died alone, mourned by no one, his name soon forgotten."}]
    assert render._classify_mood(beats) == "somber"


def test_classify_mood_uplifting_from_real_narration_words():
    beats = [{"text": "Against all odds, the team celebrated their hard-won victory."}]
    assert render._classify_mood(beats) == "uplifting"


def test_classify_mood_defaults_to_documentary_when_no_signal():
    beats = [{"text": "The ancient trade route connected three distant cities."}]
    assert render._classify_mood(beats) == "documentary"


def test_classify_mood_handles_empty_or_missing_beats():
    assert render._classify_mood([]) == "documentary"
    assert render._classify_mood(None) == "documentary"
    assert render._classify_mood([{"entity_type": "place"}]) == "documentary"


def test_classify_mood_does_not_substring_match_unrelated_words():
    # "war" must not fire on "warm"/"warrior"/"reward" — whole-word matching only.
    beats = [{"text": "The warm afternoon reward for the warrior was a quiet reunion."}]
    assert render._classify_mood(beats) == "documentary"


def test_music_tracks_falls_back_to_flat_pool_for_unknown_mood():
    # documentary/ always exists in this repo; a mood with no directory (or an empty
    # one) must still return *something* rather than silently dropping the music bed.
    tracks = render._music_tracks("not-a-real-mood")
    assert tracks  # real files on disk, not mocked
    assert all(p.suffix == ".mp3" for p in tracks)


def test_music_tracks_prefers_the_matched_mood_directory():
    tense_tracks = render._music_tracks("tense")
    assert tense_tracks
    assert all(p.parent.name == "tense" for p in tense_tracks)
