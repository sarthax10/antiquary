#!/usr/bin/env python3
"""Picks the better of a real sourced image and a generated illustration for one beat —
the ranking half of merging the old fixed "photographic"/"illustrated" styles into one
flow (Claude outputs/OPEN_ISSUES.md #66). Only ever compares two STILL IMAGES:
pipeline/fetch_visuals.py never requests an illustration for a beat whose real
candidate is video (real footage of the actual subject beats any generated image,
full stop — see fetch_visuals._fetch_one's own comment), so this module doesn't need to
reason about video at all.

Real, computable score, not an invented "quality number" (this project's own standing
rule — see Claude outputs/OPEN_ISSUES.md): source tier reflects this project's already-
documented visual evidence hierarchy (real/archival evidence over generic stock over
generated filler); technical quality is pipeline/image_quality.py's real, measured
sharpness+resolution signal. Both components and the weights between them are stated
plainly below, not hidden in a formula — read this module's SOURCE_TIER and the two
weight constants to see exactly what decides a beat's asset.
"""
from pathlib import Path

from image_quality import technical_quality_score

# 1.0 = real, on-subject evidence (archival photo, a named person's actual portrait,
# institutional archive). 0.85 = generic modern stock photography of the same subject —
# real, but not evidence of THIS subject specifically. 0.7 = a generated illustration —
# ranked below every real source by default (this project's evidence-hierarchy
# principle), but not so far below that a genuinely sharp, well-composed illustration
# can never beat a low-quality or barely-relevant real photo; see TIER_WEIGHT/
# QUALITY_WEIGHT below for how much room technical quality has to close that gap.
SOURCE_TIER = {
    "wikidata": 1.0, "commons": 1.0, "archive_org": 1.0, "nasa": 1.0,
    "europeana": 1.0, "flickr_commons": 1.0,
    "google_cse": 0.85, "pexels_photo": 0.85,
    "illustrated_gpu": 0.7,
}
DEFAULT_TIER = 0.85  # an unrecognized source is treated as generic stock, not archival

TIER_WEIGHT = 0.6
QUALITY_WEIGHT = 0.4


def _score(source: str, path: str | Path) -> float:
    tier = SOURCE_TIER.get(source, DEFAULT_TIER)
    quality = technical_quality_score(path)
    return TIER_WEIGHT * tier + QUALITY_WEIGHT * quality


def rank(real_asset: dict, illustration_asset: dict) -> tuple[dict, dict]:
    """Both args are fetch_visuals-shaped asset dicts ({"path", "source", ...}) for
    real vs. generated stills of the SAME beat. Returns (winner, scores) where scores
    is {"real": float, "illustration": float} for logging — fetch_visuals.py prints
    this so a ranking decision is inspectable after the fact, not a black box."""
    real_score = _score(real_asset["source"], real_asset["path"])
    illustration_score = _score(illustration_asset["source"], illustration_asset["path"])
    scores = {"real": real_score, "illustration": illustration_score}
    # Ties go to the real asset — a deliberate, stated default, not an accident of
    # float comparison order.
    winner = illustration_asset if illustration_score > real_score else real_asset
    return winner, scores
