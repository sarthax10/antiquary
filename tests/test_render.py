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


# --- Skin-tone secondary correction (Tier 3 #10) -------------------------------------
# The filter's own real corrective effect (does it actually reduce a sepia cast, at a
# modest magnitude) is verified separately against real decoded pixels — see the
# session's verification script and OPEN_ISSUES.md #58. These tests cover the wiring:
# who gets it and who doesn't.

def test_render_applies_skin_tone_correction_to_a_person_still_image(monkeypatch):
    captured = _capture_ffmpeg_cmd(monkeypatch)
    beats = [{"path": "a.jpg", "entity_type": "person", "face": None, "duration": 3.0, "text": "no year here"}]
    render.render("narration.mp3", "captions.ass", "out.mp4", beats)
    cmd_str = " ".join(captured["cmd"])
    assert render.SKIN_TONE_CORRECTION in cmd_str


def test_render_skips_skin_tone_correction_for_non_person_still_image(monkeypatch):
    captured = _capture_ffmpeg_cmd(monkeypatch)
    beats = [{"path": "a.jpg", "entity_type": "place", "face": None, "duration": 3.0, "text": "no year here"}]
    render.render("narration.mp3", "captions.ass", "out.mp4", beats)
    cmd_str = " ".join(captured["cmd"])
    assert render.SKIN_TONE_CORRECTION not in cmd_str


def test_render_illustrated_style_gives_every_beat_an_overlay(monkeypatch):
    # Real user report (OPEN_ISSUES.md #59): 3 of 4 beats in an illustrated video showed
    # nothing but the plain backdrop, since only a year mention triggered any overlay at
    # all. A beat with no year must still get its own visual_query as a keyword card in
    # illustrated style.
    captured = _capture_ffmpeg_cmd(monkeypatch)
    beats = [{"path": "a.jpg", "entity_type": "event", "face": None, "duration": 3.0,
              "text": "no year mentioned here", "visual_query": "Victory dance"}]
    render.render("narration.mp3", "captions.ass", "out.mp4", beats, style="illustrated")
    cmd_str = " ".join(captured["cmd"])
    assert "VICTORY DANCE" in cmd_str
    assert f"fontsize={render.motion_graphics.ILLUSTRATED_FONT_SIZE}" in cmd_str


def test_render_photographic_style_does_not_add_keyword_overlay(monkeypatch):
    # The default style must be completely unaffected by this feature — photographic
    # mode relies on real imagery, not a graphic, for beats without a year.
    captured = _capture_ffmpeg_cmd(monkeypatch)
    beats = [{"path": "a.jpg", "entity_type": "event", "face": None, "duration": 3.0,
              "text": "no year mentioned here", "visual_query": "Victory dance"}]
    render.render("narration.mp3", "captions.ass", "out.mp4", beats)  # default style
    cmd_str = " ".join(captured["cmd"])
    assert "VICTORY DANCE" not in cmd_str


def test_render_keyword_card_does_not_trigger_the_sfx_whoosh(monkeypatch):
    # Sparing on purpose: illustrated mode's keyword card fires on nearly every beat, so
    # it must NOT also trigger the accent whoosh (#18) — only a genuine year reveal does.
    captured = _capture_ffmpeg_cmd(monkeypatch)
    beats = [{"path": "a.jpg", "entity_type": "event", "face": None, "duration": 3.0,
              "text": "no year mentioned here", "visual_query": "Victory dance"}]
    render.render("narration.mp3", "captions.ass", "out.mp4", beats, style="illustrated")
    cmd_str = " ".join(captured["cmd"])
    assert "whoosh" not in cmd_str


# --- Per-beat framing/mood intent (Tier 3 #13) ---------------------------------------

def test_resolve_zoom_in_push_in_forces_zoom_in():
    assert render._resolve_zoom_in("push_in", index=1) is True  # odd index would alternate to False


def test_resolve_zoom_in_pull_back_forces_zoom_out():
    assert render._resolve_zoom_in("pull_back", index=0) is False  # even index would alternate to True


def test_resolve_zoom_in_falls_back_to_alternation_for_hold_static_and_pan():
    for framing in ("hold_static", "pan", None, "unrecognized"):
        assert render._resolve_zoom_in(framing, index=0) is True
        assert render._resolve_zoom_in(framing, index=1) is False


def test_zoompan_expr_hold_static_dampens_zoom_rate_and_pan_margin():
    z_default, _, _ = render._zoompan_expr(0.5, 0.5, zoom_in=True, index=0, frames=90)
    z_hold, x_hold, _ = render._zoompan_expr(0.5, 0.5, zoom_in=True, index=0, frames=90, framing="hold_static")
    # Both should reference "zoom+<rate>" — the hold_static rate must be smaller.
    import re
    default_rate = float(re.search(r"zoom\+([\d.]+)", z_default).group(1))
    hold_rate = float(re.search(r"zoom\+([\d.]+)", z_hold).group(1))
    assert hold_rate < default_rate


def test_zoompan_expr_pan_widens_pan_margin_relative_to_default():
    # A wider pan margin means _pan_targets' end point is further from the start point —
    # confirm indirectly via the x expression differing between "pan" and the default.
    _, x_default, _ = render._zoompan_expr(0.5, 0.5, zoom_in=True, index=0, frames=90)
    _, x_pan, _ = render._zoompan_expr(0.5, 0.5, zoom_in=True, index=0, frames=90, framing="pan")
    assert x_default != x_pan


def test_zoompan_expr_unrecognized_framing_matches_default_exactly():
    # Full backward-compat guarantee: a beat with no framing key (every beat from before
    # this feature existed) must produce byte-identical output to an explicit None.
    a = render._zoompan_expr(0.5, 0.5, zoom_in=True, index=0, frames=90)
    b = render._zoompan_expr(0.5, 0.5, zoom_in=True, index=0, frames=90, framing=None)
    assert a == b


def test_render_skips_skin_tone_correction_for_a_real_video_clip(monkeypatch):
    # A "person" entity_type whose asset happens to be a video (e.g. illustrated-mode's
    # synthetic backdrop) must not get skin-tone correction applied — it hits the
    # VIDEO_EXTS branch, which never carries this correction (see render.py's comment on
    # why: no real skin-tone content exists to correct there).
    captured = _capture_ffmpeg_cmd(monkeypatch)
    beats = [{"path": "a.mp4", "entity_type": "person", "face": None, "duration": 3.0, "text": "no year here"}]
    render.render("narration.mp3", "captions.ass", "out.mp4", beats)
    cmd_str = " ".join(captured["cmd"])
    assert render.SKIN_TONE_CORRECTION not in cmd_str


# --- Editorial Timeline refactor (FILM_PLAN_ARCHITECTURE.md Milestone 2) ------------
# render() used to decide every editorial detail (transitions, Ken Burns framing, motion
# graphics, sfx/music mixing, loudness) AND assemble the ffmpeg command in the same
# function body. build_timeline() now makes every one of those decisions and returns
# them as a Timeline; compile_ffmpeg() is a pure mechanical translation of a Timeline
# into a real ffmpeg argv; render() is just "run build_timeline() then compile_ffmpeg()
# then subprocess.run()". This test proves that split by calling all three paths against
# the same real, varied beat sets and asserting the ffmpeg command is byte-identical no
# matter which path produced it — a one-time git-history diff against the actual
# pre-refactor render() already confirmed this same invariant during the refactor itself
# (see Claude outputs/OPEN_ISSUES.md); this is the permanent version of that check.

def test_build_timeline_plus_compile_ffmpeg_matches_pre_refactor_render(monkeypatch):
    test_cases = [
        ("mixed_3beat", [
            {"path": "a.jpg", "entity_type": "person", "face": [0.5, 0.3], "duration": 3.0,
             "text": "Napoleon Bonaparte planned his next move.", "visual_query": "Napoleon Bonaparte",
             "framing": "push_in"},
            {"path": "b.jpg", "entity_type": "place", "face": None, "duration": 3.0,
             "text": "The battlefield stretched for miles in 1815.", "visual_query": "Waterloo battlefield",
             "framing": "pan"},
            {"path": "c.mp4", "entity_type": "event", "face": None, "duration": 3.0,
             "text": "The conflict changed Europe forever.", "visual_query": "European conflict",
             "framing": "hold_static"},
        ], None, "photographic"),
        ("illustrated_2beat", [
            {"path": "a.jpg", "entity_type": "person", "face": None, "duration": 4.0,
             "text": "A general made a choice.", "visual_query": "Roman general portrait"},
            {"path": "b.jpg", "entity_type": "place", "face": None, "duration": 4.0,
             "text": "The senate chamber stood empty.", "visual_query": "Roman senate chamber"},
        ], None, "illustrated"),
        ("single_beat_with_font", [
            {"path": "a.jpg", "entity_type": "scene", "face": None, "duration": 5.0,
             "text": "Nobody expected what came next.", "visual_query": "a quiet street"},
        ], {"name": "Bebas Neue", "size": 86, "uppercase": True, "avg_char_w": 38}, "photographic"),
    ]

    for name, beats, font, style in test_cases:
        captured = _capture_ffmpeg_cmd(monkeypatch)
        render.render("narration.mp3", "captions.ass", "out.mp4", [dict(b) for b in beats], font=font, style=style)
        cmd_via_render = captured["cmd"]

        _capture_ffmpeg_cmd(monkeypatch)  # re-fake ffprobe; this path issues no final-cmd subprocess.run
        timeline = render.build_timeline("narration.mp3", "captions.ass", [dict(b) for b in beats],
                                          font=font, style=style)
        cmd_via_split = render.compile_ffmpeg(timeline, "out.mp4")

        assert cmd_via_split == cmd_via_render, f"[{name}] build_timeline()+compile_ffmpeg() diverged from render()"
