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


# --- Sound-design accent cue wiring (#18/GENERATION.md) ------------------------------
# render() itself shells out to real ffmpeg (verified separately, end-to-end, against
# real waveform output — see the session notes in OPEN_ISSUES.md). These tests isolate
# the *cmd/filter_complex construction* logic by faking subprocess.run: the ffprobe call
# (get_audio_duration) returns a fixed duration, and the final ffmpeg call is captured
# instead of executed, so we can assert on exactly what render() decided to build
# without paying for a real encode or needing real media files on disk.

class _FakeCompleted:
    def __init__(self, stdout=""):
        self.stdout = stdout


def _capture_ffmpeg_cmd(monkeypatch, duration=6.0):
    captured = {}

    def fake_run(cmd, *args, **kwargs):
        if cmd[0] == "ffprobe":
            return _FakeCompleted(stdout=str(duration))
        captured["cmd"] = cmd
        return _FakeCompleted()

    monkeypatch.setattr(render.subprocess, "run", fake_run)
    monkeypatch.setattr(render, "_pick_music", lambda beats=None: None)  # isolate sfx from music
    return captured


def test_render_adds_no_sfx_when_no_cue_is_triggered(monkeypatch):
    captured = _capture_ffmpeg_cmd(monkeypatch)
    beats = [
        {"path": "a.jpg", "entity_type": "person", "face": None, "duration": 2.0,
         "text": "Julius Caesar crossed the river."},
        {"path": "b.jpg", "entity_type": "person", "face": None, "duration": 2.0,
         "text": "Marcus Brutus made his choice."},  # different subject -> hard cut, no accent
    ]
    render.render("narration.mp3", "captions.ass", "out.mp4", beats)
    cmd_str = " ".join(captured["cmd"])
    assert "whoosh" not in cmd_str
    assert "adelay" not in cmd_str


def test_render_adds_sfx_on_a_year_label_reveal(monkeypatch):
    captured = _capture_ffmpeg_cmd(monkeypatch)
    beats = [
        {"path": "a.jpg", "entity_type": "event", "face": None, "duration": 3.0,
         "text": "In 1943, everything changed."},
    ]
    render.render("narration.mp3", "captions.ass", "out.mp4", beats)
    cmd_str = " ".join(captured["cmd"])
    assert "whoosh.mp3" in cmd_str
    assert "adelay=delays=100:all=1" in cmd_str  # beat_start[0]=0.0 + the 0.1s reveal delay


def test_render_adds_sfx_on_an_accent_transition(monkeypatch):
    captured = _capture_ffmpeg_cmd(monkeypatch)
    beats = [
        {"path": "a.jpg", "entity_type": "person", "face": None, "duration": 3.0,
         "text": "Napoleon Bonaparte planned his next move."},
        {"path": "b.jpg", "entity_type": "place", "face": None, "duration": 3.0,
         "text": "The battlefield stretched for miles."},
    ]
    render.render("narration.mp3", "captions.ass", "out.mp4", beats)
    cmd_str = " ".join(captured["cmd"])
    assert "whoosh.mp3" in cmd_str
    assert "adelay" in cmd_str
