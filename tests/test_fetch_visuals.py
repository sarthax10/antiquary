"""Tests for pipeline/fetch_visuals.py's animated placeholder backdrop (see Claude
outputs/OPEN_ISSUES.md #16). Real ffmpeg encode (small/fast — short duration, low fps),
not mocked, matching this project's "verify against the real stack" precedent — the
whole point of this feature is that it produces genuine motion, which a mocked
ffmpeg call couldn't confirm anyway.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import fetch_visuals as fv  # noqa: E402


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _extract_frame(path: Path, t: float, out: Path) -> np.ndarray:
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(t), "-i", str(path), "-frames:v", "1", str(out)],
        check=True, capture_output=True,
    )
    from PIL import Image
    return np.array(Image.open(out).convert("RGB"), dtype=np.float32)


def test_placeholder_clip_is_a_valid_video_of_the_requested_duration(tmp_path):
    out = tmp_path / "placeholder.mp4"
    fv._placeholder_clip(out, seed=0, duration=0.6, fps=10)
    assert out.exists() and out.stat().st_size > 0
    assert abs(_probe_duration(out) - 0.6) < 0.15  # container rounding, not exact


def test_placeholder_clip_actually_has_motion_between_frames(tmp_path):
    """The whole point of this feature: NOT a still image. Confirms two frames from the
    same clip are meaningfully different, not identical (which a static backdrop would
    produce even if saved as a video)."""
    out = tmp_path / "placeholder.mp4"
    fv._placeholder_clip(out, seed=1, duration=2.0, fps=10)
    first = _extract_frame(out, 0.05, tmp_path / "f0.png")
    mid = _extract_frame(out, 1.0, tmp_path / "f1.png")
    diff = np.abs(first - mid).mean()
    assert diff > 1.0  # comfortably above encoder noise floor for two identical frames


def test_placeholder_clip_loops_near_seamlessly(tmp_path):
    """render.py plays this with -stream_loop -1 for any beat longer than `duration` —
    the drift/sweep must be periodic so the loop point doesn't visibly jump."""
    out = tmp_path / "placeholder.mp4"
    fv._placeholder_clip(out, seed=2, duration=2.0, fps=10)
    start = _extract_frame(out, 0.05, tmp_path / "start.png")
    end = _extract_frame(out, 1.9, tmp_path / "end.png")
    diff = np.abs(start - end).mean()
    assert diff < 12.0  # close, not identical (still real motion), for a seamless loop


def test_placeholder_palette_varies_by_seed():
    colors = {fv.PLACEHOLDER_PALETTE[seed % len(fv.PLACEHOLDER_PALETTE)][0] for seed in range(3)}
    assert len(colors) == 3


def _blank_image(tmp_path: Path) -> Path:
    """A real solid-color image with no detectable face — a genuine cv2 call against it
    naturally returns None, the same as a real painting/bust/engraving the Haar cascade
    (trained on frontal photos) fails to find a face in (see OPEN_ISSUES.md audit #35).
    Not mocked: this is exactly the "detection failed" case the fallback exists for."""
    from PIL import Image
    path = tmp_path / "blank.jpg"
    Image.new("RGB", (400, 600), color=(80, 80, 80)).save(path)
    return path


def test_detect_face_center_returns_none_on_a_faceless_image(tmp_path):
    assert fv._detect_face_center(_blank_image(tmp_path)) is None


def test_portrait_fallback_used_when_no_face_detected_on_a_person_beat(tmp_path):
    # Real detection failure (no mock) on a "person" beat -> the documented upper-third
    # framing guess, not None (which render.py would otherwise treat as "blind center").
    result = fv._face_or_portrait_fallback(_blank_image(tmp_path), "person")
    assert result == list(fv.PORTRAIT_FALLBACK_CENTER)


def test_no_portrait_fallback_for_non_person_beats(tmp_path):
    # A "place"/"event"/"scene" beat has no portrait-composition assumption to lean on —
    # detection failure there should still fall all the way through to None.
    for entity_type in ("place", "event", "scene"):
        assert fv._face_or_portrait_fallback(_blank_image(tmp_path), entity_type) is None


def test_face_or_portrait_fallback_prefers_a_real_detected_face(tmp_path, monkeypatch):
    # When a real face IS found, use it -- never overridden by the portrait guess.
    monkeypatch.setattr(fv, "_detect_face_center", lambda path: [0.42, 0.5])
    result = fv._face_or_portrait_fallback(_blank_image(tmp_path), "person")
    assert result == [0.42, 0.5]
