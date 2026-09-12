"""Pure-logic tests for run_pipeline.py's _merge_short_beats() — see OPEN_ISSUES.md audit
#38 / PROFESSIONAL_QUALITY_ROADMAP.md Tier 1 #4: a beat whose real synthesized narration
comes out under MIN_BEAT_DURATION previously produced a sub-second visual clip that reads
as a glitch, not a deliberate quick cut. tts.concat_audio is monkeypatched so this stays a
pure-logic test (list restructuring, text/duration bookkeeping) with no real ffmpeg call —
the actual audio concatenation mechanism (tts.concat_audio itself) already has its own
real, ffmpeg-backed verification elsewhere in this project's history.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import run_pipeline  # noqa: E402


def _patch_concat(monkeypatch):
    calls = []

    def fake_concat_audio(paths, out_path):
        calls.append((list(paths), out_path))
        Path(out_path).write_bytes(b"fake-merged-audio")

    monkeypatch.setattr(run_pipeline.tts, "concat_audio", fake_concat_audio)
    return calls


def test_no_merge_when_every_beat_is_long_enough(monkeypatch, tmp_path):
    calls = _patch_concat(monkeypatch)
    beats = [{"text": "First.", "visual_query": "a"}, {"text": "Second.", "visual_query": "b"}]
    assets = [{"id": 0}, {"id": 1}]
    beat_audio = [
        {"text": "First.", "path": str(tmp_path / "b0.mp3"), "duration": 1.5},
        {"text": "Second.", "path": str(tmp_path / "b1.mp3"), "duration": 1.8},
    ]

    merged_beats, merged_assets, merged_audio = run_pipeline._merge_short_beats(beats, assets, beat_audio)

    assert merged_beats == beats
    assert merged_assets == assets
    assert merged_audio == beat_audio
    assert calls == []  # nothing needed merging, so concat_audio was never called


def test_short_beat_merges_forward_into_the_next_beat(monkeypatch, tmp_path):
    calls = _patch_concat(monkeypatch)
    beats = [
        {"text": "Yes.", "visual_query": "a", "entity_type": "event"},
        {"text": "This is the real second beat.", "visual_query": "b", "entity_type": "event"},
    ]
    assets = [{"id": "asset0"}, {"id": "asset1"}]
    beat_audio = [
        {"text": "Yes.", "path": str(tmp_path / "beat_00.mp3"), "duration": 0.3},
        {"text": "This is the real second beat.", "path": str(tmp_path / "beat_01.mp3"), "duration": 2.5},
    ]

    merged_beats, merged_assets, merged_audio = run_pipeline._merge_short_beats(beats, assets, beat_audio)

    assert len(merged_beats) == 1
    assert merged_beats[0]["text"] == "Yes. This is the real second beat."
    # Keeps the SURVIVING (next) beat's own visual asset, not the dropped short one's.
    assert merged_assets == [{"id": "asset1"}]
    assert merged_audio[0]["duration"] == 0.3 + 2.5
    assert merged_audio[0]["text"] == "Yes. This is the real second beat."
    assert len(calls) == 1


def test_short_last_beat_merges_backward_into_the_previous_beat(monkeypatch, tmp_path):
    calls = _patch_concat(monkeypatch)
    beats = [
        {"text": "A long, normal first beat with real content.", "visual_query": "a"},
        {"text": "The end.", "visual_query": "b"},
    ]
    assets = [{"id": "asset0"}, {"id": "asset1"}]
    beat_audio = [
        {"text": "A long, normal first beat with real content.", "path": str(tmp_path / "b0.mp3"), "duration": 2.2},
        {"text": "The end.", "path": str(tmp_path / "b1.mp3"), "duration": 0.4},
    ]

    merged_beats, merged_assets, merged_audio = run_pipeline._merge_short_beats(beats, assets, beat_audio)

    assert len(merged_beats) == 1
    assert merged_beats[0]["text"] == "A long, normal first beat with real content. The end."
    # Keeps the surviving (previous) beat's own visual asset.
    assert merged_assets == [{"id": "asset0"}]
    assert merged_audio[0]["duration"] == 2.2 + 0.4
    assert len(calls) == 1


def test_two_consecutive_short_beats_cascade_into_one(monkeypatch, tmp_path):
    _patch_concat(monkeypatch)
    beats = [
        {"text": "Ok.", "visual_query": "a"},
        {"text": "Wait.", "visual_query": "b"},
        {"text": "A real, sufficiently long closing beat here.", "visual_query": "c"},
    ]
    assets = [{"id": 0}, {"id": 1}, {"id": 2}]
    beat_audio = [
        {"text": "Ok.", "path": str(tmp_path / "b0.mp3"), "duration": 0.3},
        {"text": "Wait.", "path": str(tmp_path / "b1.mp3"), "duration": 0.35},
        {"text": "A real, sufficiently long closing beat here.", "path": str(tmp_path / "b2.mp3"), "duration": 2.6},
    ]

    merged_beats, merged_assets, merged_audio = run_pipeline._merge_short_beats(beats, assets, beat_audio)

    assert len(merged_beats) == 1
    assert merged_beats[0]["text"] == "Ok. Wait. A real, sufficiently long closing beat here."
    assert merged_assets == [{"id": 2}]
    assert round(merged_audio[0]["duration"], 2) == round(0.3 + 0.35 + 2.6, 2)


def test_single_short_beat_alone_is_kept_as_is(monkeypatch, tmp_path):
    calls = _patch_concat(monkeypatch)
    beats = [{"text": "Short.", "visual_query": "a"}]
    assets = [{"id": 0}]
    beat_audio = [{"text": "Short.", "path": str(tmp_path / "b0.mp3"), "duration": 0.2}]

    merged_beats, merged_assets, merged_audio = run_pipeline._merge_short_beats(beats, assets, beat_audio)

    assert merged_beats == beats
    assert merged_assets == assets
    assert merged_audio == beat_audio
    assert calls == []
