#!/usr/bin/env python3
"""Real, computable image-quality signals used by pipeline/asset_ranking.py — resolution
and sharpness (Laplacian variance), both measured directly on the actual downloaded/
generated image bytes, not invented numbers (see Claude outputs/OPEN_ISSUES.md #66).

Honest limitation, confirmed by direct experiment on this project's own GPU host, not
assumed: sharpness/resolution do NOT detect the specific SD-Turbo failure mode this
project has actually hit (see #61's "Roman legion marching" finding) — a degenerate,
repetitive multi-subject generation has just as much (sometimes more) local edge
contrast as a clean single-subject illustration, since the artifact IS high-frequency
noise. A side-by-side test this session (a clean portrait vs. a visibly broken crowd
scene, both at 4 inference steps) measured Laplacian variances of 2042 and 1945
respectively — indistinguishable by this metric. That failure mode is instead handled
upstream, before generation is even attempted, by illustrate.is_multi_subject_prompt().
What sharpness/resolution DO catch honestly: a flat, blurry, or low-resolution result —
a real "polish" signal, just not a distortion detector.
"""
from pathlib import Path

import cv2

# Calibrated against this project's own real SD-Turbo output (see module docstring) at
# its native 512x512 generation size, and real downloaded photos in the 600-2000px
# range from this pipeline's other sources — not arbitrary. A score of 1.0 means "at or
# above a genuinely sharp/high-res real photo," not "perfect."
SHARPNESS_REFERENCE = 1800.0  # ~the lower end of this session's own real SD-Turbo output
RESOLUTION_REFERENCE = 1_000_000.0  # 1MP — a modest real photo, not a demanding bar


def sharpness_score(path: str | Path) -> float:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0
    variance = cv2.Laplacian(img, cv2.CV_64F).var()
    return min(variance / SHARPNESS_REFERENCE, 1.0)


def resolution_score(path: str | Path) -> float:
    img = cv2.imread(str(path))
    if img is None:
        return 0.0
    h, w = img.shape[:2]
    return min((h * w) / RESOLUTION_REFERENCE, 1.0)


def technical_quality_score(path: str | Path) -> float:
    """0..1, higher is more polished. Weighted toward sharpness — a small sharp image
    Ken-Burns-crops fine (render.py already supersamples before zoompan); a large blurry
    one doesn't get any better for being big."""
    return 0.65 * sharpness_score(path) + 0.35 * resolution_score(path)
