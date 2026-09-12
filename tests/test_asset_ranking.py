"""Tests for pipeline/asset_ranking.py — the real source-tier + technical-quality
scoring that replaces the old fixed "photographic"/"illustrated" style fork (Claude
outputs/OPEN_ISSUES.md #66). image_quality's real scoring functions are mocked here (a
fixed 0..1 number per test) since these tests are about the RANKING decision, not about
re-verifying image_quality.py's own scoring (see tests/test_image_quality.py for that).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import asset_ranking  # noqa: E402


def test_rank_prefers_real_archival_source_over_illustration_at_equal_quality(monkeypatch, tmp_path):
    monkeypatch.setattr(asset_ranking, "technical_quality_score", lambda path: 0.5)
    real = {"path": tmp_path / "real.jpg", "source": "commons"}
    illustration = {"path": tmp_path / "illustration.png", "source": "illustrated_gpu"}
    winner, scores = asset_ranking.rank(real, illustration)
    assert winner is real
    assert scores["real"] > scores["illustration"]


def test_rank_lets_a_much_sharper_illustration_beat_a_low_quality_real_photo(monkeypatch, tmp_path):
    def _fake_quality(path):
        return 0.1 if "real" in str(path) else 0.95
    monkeypatch.setattr(asset_ranking, "technical_quality_score", _fake_quality)
    real = {"path": tmp_path / "real_blurry.jpg", "source": "pexels_photo"}
    illustration = {"path": tmp_path / "illustration_sharp.png", "source": "illustrated_gpu"}
    winner, scores = asset_ranking.rank(real, illustration)
    assert winner is illustration
    assert scores["illustration"] > scores["real"]


def test_rank_ties_go_to_the_real_asset(monkeypatch, tmp_path):
    monkeypatch.setattr(asset_ranking, "technical_quality_score", lambda path: 0.5)
    # Force an exact tie by using the same source tier for both.
    real = {"path": tmp_path / "real.jpg", "source": "illustrated_gpu"}
    illustration = {"path": tmp_path / "illustration.png", "source": "illustrated_gpu"}
    winner, _ = asset_ranking.rank(real, illustration)
    assert winner is real


def test_rank_unrecognized_source_treated_as_generic_stock(monkeypatch, tmp_path):
    monkeypatch.setattr(asset_ranking, "technical_quality_score", lambda path: 0.5)
    assert asset_ranking.SOURCE_TIER.get("some_new_source_not_yet_added") is None
    real = {"path": tmp_path / "real.jpg", "source": "some_new_source_not_yet_added"}
    illustration = {"path": tmp_path / "illustration.png", "source": "illustrated_gpu"}
    winner, scores = asset_ranking.rank(real, illustration)
    # DEFAULT_TIER (0.85) beats illustration's fixed 0.7 tier at equal quality.
    assert winner is real


def test_source_tier_ranks_illustration_below_every_real_source():
    illustration_tier = asset_ranking.SOURCE_TIER["illustrated_gpu"]
    for source, tier in asset_ranking.SOURCE_TIER.items():
        if source == "illustrated_gpu":
            continue
        assert tier > illustration_tier, f"{source} should rank above illustrated_gpu"
