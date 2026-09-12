"""Tests for pipeline/image_quality.py — real, computed sharpness/resolution scoring on
real images (small real ffmpeg/PIL-generated test images, not mocked cv2 calls), plus
the honest limitation documented in that module: this does NOT reliably separate a
clean single-subject illustration from a degenerate multi-subject one (both can be
"sharp") — see pipeline/illustrate.py's is_multi_subject_prompt for how that's actually
handled."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import image_quality  # noqa: E402


def _solid_color_image(path: Path, size=(200, 200)):
    from PIL import Image
    Image.new("RGB", size, color=(120, 100, 80)).save(path)


def _noisy_image(path: Path, size=(200, 200)):
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(42)
    arr = rng.integers(0, 255, size=(size[1], size[0], 3), dtype="uint8")
    Image.fromarray(arr).save(path)


def test_sharpness_score_is_near_zero_for_a_flat_solid_color(tmp_path):
    path = tmp_path / "flat.png"
    _solid_color_image(path)
    assert image_quality.sharpness_score(path) < 0.05


def test_sharpness_score_is_higher_for_a_high_contrast_noisy_image(tmp_path):
    flat = tmp_path / "flat.png"
    noisy = tmp_path / "noisy.png"
    _solid_color_image(flat)
    _noisy_image(noisy)
    assert image_quality.sharpness_score(noisy) > image_quality.sharpness_score(flat)


def test_sharpness_score_returns_zero_for_a_nonexistent_or_unreadable_file(tmp_path):
    assert image_quality.sharpness_score(tmp_path / "does_not_exist.png") == 0.0


def test_resolution_score_scales_with_real_pixel_count(tmp_path):
    small = tmp_path / "small.png"
    large = tmp_path / "large.png"
    _solid_color_image(small, size=(100, 100))
    _solid_color_image(large, size=(1200, 1200))
    assert image_quality.resolution_score(large) > image_quality.resolution_score(small)


def test_resolution_score_caps_at_one(tmp_path):
    huge = tmp_path / "huge.png"
    _solid_color_image(huge, size=(2000, 2000))
    assert image_quality.resolution_score(huge) == 1.0


def test_technical_quality_score_is_bounded_zero_to_one(tmp_path):
    path = tmp_path / "noisy.png"
    _noisy_image(path)
    score = image_quality.technical_quality_score(path)
    assert 0.0 <= score <= 1.0
