"""Tests for the per-clip durable asset storage + render-from-timeline foundation
(Section D, "Phase A part 2" in Claude outputs/CHECKLIST.md): enqueue_story uploading
each beat's visual/audio clip to MinIO under the story's namespace and recording the
object key on the timeline, and render_timeline.py rebuilding a video from those durable
assets + the timeline's own caption track instead of the original run's (deleted) temp
files. No real MinIO/ffmpeg here — pure logic + monkeypatched I/O boundaries, the same
style test_beats.py uses for the Ollama call.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import captions  # noqa: E402
import enqueue_story  # noqa: E402
import render_timeline  # noqa: E402


def _words(*specs):
    return [{"word": w, "start": s, "end": e} for w, s, e in specs]


def test_build_ass_from_track_matches_build_ass_for_same_words(tmp_path):
    font = captions.CAPTION_FONTS[0]
    words = _words(("The", 0.0, 0.3), ("secret", 0.3, 0.8), ("letter", 0.8, 1.3), ("arrived", 1.3, 1.9))

    direct_path = tmp_path / "direct.ass"
    captions.build_ass(words, str(direct_path), font=font)

    track = captions.build_caption_track(words, font)
    from_track_path = tmp_path / "from_track.ass"
    captions.build_ass_from_track(track, font, str(from_track_path))

    assert direct_path.read_text(encoding="utf-8") == from_track_path.read_text(encoding="utf-8")


def test_build_ass_from_track_falls_back_without_word_timestamps(tmp_path):
    """A caption entry a human editor added (or one from before "words" existed) has no
    per-word data — must still render as a single dialogue line, not crash."""
    font = captions.font_by_name("Fira Sans Medium")
    track = [{"id": "cap_00", "text": "Hand edited caption", "start": 0.0, "end": 1.5, "emphasis": False}]
    out_path = tmp_path / "fallback.ass"
    captions.build_ass_from_track(track, font, str(out_path))
    content = out_path.read_text(encoding="utf-8")
    assert "Hand edited caption" in content
    assert content.count("Dialogue:") == 1


def test_font_by_name_roundtrips_every_caption_font():
    for font in captions.CAPTION_FONTS:
        assert captions.font_by_name(font["name"]) == font


def test_font_by_name_missing_returns_none():
    assert captions.font_by_name("Not A Real Font") is None


def test_upload_clip_assets_assigns_object_keys_in_order(monkeypatch):
    uploaded = []
    monkeypatch.setattr(enqueue_story, "upload_asset", lambda local, key, ct: uploaded.append((local, key, ct)))

    timeline = {
        "tracks": {
            "visual": [{"id": "clip_00"}, {"id": "clip_01"}],
            "narration": [{"id": "beat_00"}, {"id": "beat_01"}],
        }
    }
    clip_files = [
        {"visual_path": "/tmp/a.jpg", "audio_path": "/tmp/a.mp3"},
        {"visual_path": "/tmp/b.mp4", "audio_path": "/tmp/b.mp3"},
    ]

    result = enqueue_story._upload_clip_assets(timeline, clip_files, user_id=7, story_id="abc123")

    assert result["tracks"]["visual"][0]["object_key"] == "stories/7/abc123/clips/visual_00.jpg"
    assert result["tracks"]["visual"][1]["object_key"] == "stories/7/abc123/clips/visual_01.mp4"
    assert result["tracks"]["narration"][0]["object_key"] == "stories/7/abc123/clips/audio_00.mp3"
    assert result["tracks"]["narration"][1]["object_key"] == "stories/7/abc123/clips/audio_01.mp3"
    assert uploaded[0] == ("/tmp/a.jpg", "stories/7/abc123/clips/visual_00.jpg", "image/jpeg")
    assert uploaded[2] == ("/tmp/b.mp4", "stories/7/abc123/clips/visual_01.mp4", "video/mp4")


def test_render_from_timeline_rejects_empty_tracks():
    try:
        render_timeline.render_from_timeline({"tracks": {"visual": [], "narration": []}}, "/tmp/out.mp4")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_render_from_timeline_rejects_mismatched_track_lengths():
    timeline = {"tracks": {"visual": [{"object_key": "a"}, {"object_key": "b"}], "narration": [{"object_key": "c"}]}}
    try:
        render_timeline.render_from_timeline(timeline, "/tmp/out.mp4")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_render_from_timeline_rejects_missing_object_key():
    timeline = {
        "tracks": {
            "visual": [{"object_key": None}],
            "narration": [{"object_key": "stories/1/x/clips/audio_00.mp3", "duration": 1.0}],
        }
    }
    try:
        render_timeline.render_from_timeline(timeline, "/tmp/out.mp4")
        assert False, "expected ValueError"
    except ValueError:
        pass
