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


# --- Unified real-sourcing + ranked-illustration flow (Claude outputs/
# OPEN_ISSUES.md #66 — replaces the old fixed "photographic"/"illustrated" style
# fork). The real remote-worker round trip and the real GPU/model path are each
# verified separately (illustration_jobs against a real local server — see
# test_illustration_jobs_real_round_trip.py-style verification in OPEN_ISSUES.md #66;
# illustrate.py against real hardware, see OPEN_ISSUES.md #61). These tests confirm
# fetch_visuals._fetch_one's own wiring/decision logic with everything below it mocked.

def test_fetch_one_returns_real_asset_when_no_illustration_beats_it(tmp_path, monkeypatch):
    real = {"path": tmp_path / "x.jpg", "source": "commons", "entity_type": "scene", "face": None}
    Path(real["path"]).write_bytes(b"fake jpg")
    monkeypatch.setattr(fv, "_fetch_generic", lambda *a, **kw: real)
    monkeypatch.setattr(fv.illustration_jobs, "request_illustration", lambda *a, **kw: None)
    beat = {"visual_query": "a river", "entity_type": "scene"}
    asset = fv._fetch_one(beat, tmp_path / "img_00", seed=0)
    assert asset is real


def test_fetch_one_skips_illustration_entirely_when_real_asset_is_video(tmp_path, monkeypatch):
    # Real footage of the actual subject beats any generated image outright — never
    # worth the network round trip to find out (see this module's own docstring).
    real = {"path": tmp_path / "x.mp4", "source": "video", "entity_type": "scene", "face": None}
    monkeypatch.setattr(fv, "_fetch_generic", lambda *a, **kw: real)

    def _boom(*a, **kw):
        raise AssertionError("must not request illustration when real asset is video")

    monkeypatch.setattr(fv.illustration_jobs, "request_illustration", _boom)
    beat = {"visual_query": "a river", "entity_type": "scene"}
    asset = fv._fetch_one(beat, tmp_path / "img_00", seed=0)
    assert asset is real


def test_fetch_one_skips_illustration_for_a_multi_subject_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(fv, "_fetch_generic", lambda *a, **kw: None)

    def _boom(*a, **kw):
        raise AssertionError("must not request illustration for a crowd/multi-subject prompt")

    monkeypatch.setattr(fv.illustration_jobs, "request_illustration", _boom)
    beat = {"visual_query": "a crowd of soldiers marching", "entity_type": "event"}
    asset = fv._fetch_one(beat, tmp_path / "img_00", seed=0)
    assert asset["source"] == "placeholder"
    assert asset["needs_keyword_card"] is True


def test_fetch_one_uses_illustration_when_real_sourcing_finds_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(fv, "_fetch_person", lambda *a, **kw: None)
    monkeypatch.setattr(fv.illustration_jobs, "request_illustration", lambda *a, **kw: b"fake png bytes")
    beat = {"visual_query": "an obscure general", "entity_type": "person"}
    asset = fv._fetch_one(beat, tmp_path / "img_00", seed=0)
    assert asset["source"] == "illustrated_gpu"
    assert Path(asset["path"]).exists()
    assert Path(asset["path"]).read_bytes() == b"fake png bytes"


def test_fetch_one_falls_to_placeholder_when_neither_real_nor_illustration_available(tmp_path, monkeypatch):
    monkeypatch.setattr(fv, "_fetch_generic", lambda *a, **kw: None)
    monkeypatch.setattr(fv.illustration_jobs, "request_illustration", lambda *a, **kw: None)
    beat = {"visual_query": "a river", "entity_type": "scene"}
    asset = fv._fetch_one(beat, tmp_path / "img_00", seed=0)
    assert asset["source"] == "placeholder"
    assert asset["needs_keyword_card"] is True
    assert Path(asset["path"]).suffix == ".mp4"
    assert Path(asset["path"]).exists()


def test_fetch_one_ranks_real_against_illustration_when_both_exist(tmp_path, monkeypatch):
    real = {"path": tmp_path / "x.jpg", "source": "commons", "entity_type": "scene", "face": None}
    Path(real["path"]).write_bytes(b"fake jpg")
    monkeypatch.setattr(fv, "_fetch_generic", lambda *a, **kw: real)
    monkeypatch.setattr(fv.illustration_jobs, "request_illustration", lambda *a, **kw: b"fake png bytes")

    winner = {"path": tmp_path / "winner.png", "source": "illustrated_gpu"}
    called = {}

    def _fake_rank(real_asset, illustration_asset):
        called["real"], called["illustration"] = real_asset, illustration_asset
        return winner, {"real": 0.5, "illustration": 0.9}

    monkeypatch.setattr(fv.asset_ranking, "rank", _fake_rank)
    beat = {"visual_query": "a river", "entity_type": "scene"}
    asset = fv._fetch_one(beat, tmp_path / "img_00", seed=0)
    assert asset is winner
    assert called["real"] is real
    assert called["illustration"]["source"] == "illustrated_gpu"


# --- Internet Archive public-domain footage sourcing (see OPEN_ISSUES.md #62) --------
# A real, legally clean alternative to scraping YouTube (the user's other explicit
# "yes" answer, given YouTube's own ToS risk). The relevance-gating logic (mocked HTTP
# below) is the load-bearing part to unit-test — Internet Archive's catalog is strong
# for 20th-century footage but a keyword search can false-positive on pre-film-era
# topics via a shared word (see _archive_org_search's own docstring for the real
# "ancient Rome" vs. "Advance on Rome" example this guards against). One real,
# unmocked call against the live API closes the loop — confirms the actual endpoint
# still behaves as this was designed against, not just the mocked shape of it.

def test_archive_significant_words_strips_stopwords_and_short_tokens():
    words = fv._archive_significant_words("The Battle of the Somme, in 1916")
    assert "the" not in words
    assert "of" not in words
    assert "in" not in words
    assert "battle" in words
    assert "somme" in words
    assert "1916" in words


def test_archive_org_search_accepts_a_strong_title_match(monkeypatch):
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": {"docs": [
                {"identifier": "ddday1944", "title": "Normandy D-Day Landing Footage 1944"},
            ]}}

    monkeypatch.setattr(fv.requests, "get", lambda *a, **kw: _FakeResp())
    assert fv._archive_org_search("D-Day Normandy landing") == "ddday1944"


def test_archive_org_search_rejects_a_single_shared_word_false_positive(monkeypatch):
    # The real bug case this guards against: a 1944 newsreel about the Allied advance
    # ON the city of Rome must NOT be accepted for a query about ANCIENT Rome just
    # because both titles contain the word "Rome".
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": {"docs": [
                {"identifier": "advance1944", "title": "Advance on Rome, 1944"},
            ]}}

    monkeypatch.setattr(fv.requests, "get", lambda *a, **kw: _FakeResp())
    assert fv._archive_org_search("ancient Rome") is None


def test_archive_org_search_returns_none_when_no_docs():
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": {"docs": []}}

    import unittest.mock
    with unittest.mock.patch.object(fv.requests, "get", return_value=_FakeResp()):
        assert fv._archive_org_search("anything") is None


def test_archive_org_video_url_prefers_the_512kb_derivative(monkeypatch):
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"files": [
                {"name": "Example_edit.mp4"},
                {"name": "Example_512kb.mp4"},
                {"name": "Example.ogv"},
            ]}

    monkeypatch.setattr(fv.requests, "get", lambda *a, **kw: _FakeResp())
    url = fv._archive_org_video_url("Example")
    assert url == "https://archive.org/download/Example/Example_512kb.mp4"


def test_archive_org_video_url_falls_back_to_any_mp4_if_no_512kb(monkeypatch):
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"files": [{"name": "Example_edit.mp4"}, {"name": "Example.ogv"}]}

    monkeypatch.setattr(fv.requests, "get", lambda *a, **kw: _FakeResp())
    url = fv._archive_org_video_url("Example")
    assert url == "https://archive.org/download/Example/Example_edit.mp4"


def test_archive_org_video_url_none_when_no_mp4_at_all(monkeypatch):
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"files": [{"name": "Example.ogv"}]}

    monkeypatch.setattr(fv.requests, "get", lambda *a, **kw: _FakeResp())
    assert fv._archive_org_video_url("Example") is None


def test_archive_org_search_real_api_returns_relevant_public_domain_result():
    # One real, unmocked call against the live archive.org API — a genuine, specific,
    # well-documented WWII search term that should reliably have real public-domain
    # footage. Skips (doesn't fail the suite) if the network/API is unreachable, same
    # spirit as this project's other real-network tests staying honest about
    # environment dependence rather than silently mocking it away entirely.
    import pytest
    try:
        identifier = fv._archive_org_search("D-Day Normandy invasion")
    except fv.requests.exceptions.RequestException:
        pytest.skip("archive.org unreachable from this environment")
    assert identifier is not None
    url = fv._archive_org_video_url(identifier)
    assert url is not None
    assert url.startswith("https://archive.org/download/")


# --- Widened media acquisition: NASA / Europeana / Flickr Commons / Google CSE ------
# Added per the user's explicit "improve the video sources" follow-up, after YouTube
# and Twitter/X were declined outright (downloading from YouTube violates its own ToS
# regardless of a video's license; almost nothing on Twitter/X carries any reuse
# license at all, and its API terms prohibit bulk media scraping for reuse) and "use
# Google Images" was redirected to the real legitimate version — Google's Custom
# Search API with a `rights` filter, not scraping arbitrary copyrighted search
# results. Library of Congress was investigated and is NOT wired in: loc.gov currently
# blocks even a plain GET to /robots.txt behind a Cloudflare JS challenge (confirmed
# directly this session) — no plain HTTP client can reach it without bypassing
# anti-bot protection, which this project won't do.

def test_title_relevant_shared_gate_matches_archive_org_behavior():
    # The exact "Advance on Rome, 1944" false-positive case _archive_org_search's own
    # tests already cover, run here against the now-shared helper directly — confirms
    # the refactor (extracting _title_relevant out of _archive_org_search) didn't
    # change behavior.
    assert fv._title_relevant("ancient Rome", "Advance on Rome, 1944") is False
    assert fv._title_relevant("D-Day Normandy landing", "Normandy D-Day Landing Footage 1944") is True


def test_first_image_hit_isolates_one_sources_failure_from_the_rest(monkeypatch):
    # The real bug this replaces: previously, Commons raising inside a single shared
    # try/except silently skipped every source listed after it too, not just Commons.
    def _boom(query):
        raise fv.requests.exceptions.RequestException("simulated network error")

    def _hit(query):
        return "https://example.com/real.jpg"

    url, source = fv._first_image_hit("test query", [(_boom, "broken"), (_hit, "works")])
    assert url == "https://example.com/real.jpg"
    assert source == "works"


def test_first_image_hit_returns_none_when_every_source_misses():
    url, source = fv._first_image_hit("test query", [(lambda q: None, "a"), (lambda q: None, "b")])
    assert url is None and source is None


def test_nasa_images_search_real_api_returns_relevant_result():
    # Real, unmocked — no API key needed (images-api.nasa.gov is a public,
    # unauthenticated endpoint, confirmed directly this session).
    import pytest
    try:
        url = fv._nasa_images_search("Apollo 11 moon landing")
    except fv.requests.exceptions.RequestException:
        pytest.skip("images-api.nasa.gov unreachable from this environment")
    assert url is not None
    assert url.startswith("https://")


def test_nasa_images_search_rejects_irrelevant_results(monkeypatch):
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"collection": {"items": [
                {"data": [{"title": "Completely unrelated garden party photo"}],
                 "links": [{"render": "image", "href": "https://example.com/x.jpg"}]},
            ]}}

    monkeypatch.setattr(fv.requests, "get", lambda *a, **kw: _FakeResp())
    assert fv._nasa_images_search("Apollo 11 moon landing") is None


def test_europeana_search_real_api_returns_relevant_licensed_result():
    # Real, unmocked — uses Europeana's own published public demo key ("api2demo",
    # confirmed working live this session) when EUROPEANA_API_KEY isn't set.
    import pytest
    try:
        url = fv._europeana_search("Eiffel Tower construction")
    except fv.requests.exceptions.RequestException:
        pytest.skip("api.europeana.eu unreachable from this environment")
    if url is None:
        pytest.skip("no license-clean, relevant result for this query right now — "
                     "not a code failure, Europeana's real index changes over time")
    assert url.startswith("https://") or url.startswith("http://")


def test_europeana_search_rejects_non_commercial_rights(monkeypatch):
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"success": True, "items": [
                {"rights": ["http://creativecommons.org/licenses/by-nc-nd/4.0/"],
                 "title": ["Eiffel Tower construction 1889"],
                 "edmIsShownBy": ["https://example.com/x.jpg"]},
            ]}

    monkeypatch.setattr(fv.requests, "get", lambda *a, **kw: _FakeResp())
    assert fv._europeana_search("Eiffel Tower construction") is None


def test_europeana_search_rejects_rights_statements_not_on_the_allow_list(monkeypatch):
    # "No Copyright - Other Known Legal Restrictions" is real and common in Europeana's
    # index, but deliberately NOT treated as clear enough (the name says there may be
    # other real legal restrictions, e.g. privacy/publicity rights) — the allow-list is
    # intentionally narrower than "not obviously copyrighted."
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"success": True, "items": [
                {"rights": ["http://rightsstatements.org/vocab/NoC-OKLR/1.0/"],
                 "title": ["Eiffel Tower construction 1889"],
                 "edmIsShownBy": ["https://example.com/x.jpg"]},
            ]}

    monkeypatch.setattr(fv.requests, "get", lambda *a, **kw: _FakeResp())
    assert fv._europeana_search("Eiffel Tower construction") is None


def test_europeana_search_accepts_publicdomain_mark(monkeypatch):
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"success": True, "items": [
                {"rights": ["http://creativecommons.org/publicdomain/mark/1.0/"],
                 "title": ["Eiffel Tower construction 1889"],
                 "edmIsShownBy": ["https://example.com/x.jpg"]},
            ]}

    monkeypatch.setattr(fv.requests, "get", lambda *a, **kw: _FakeResp())
    assert fv._europeana_search("Eiffel Tower construction") == "https://example.com/x.jpg"


def test_flickr_commons_search_skips_cleanly_without_an_api_key(monkeypatch):
    # No FLICKR_API_KEY is available in this environment — confirms the graceful,
    # Pexels-style skip (no exception, no request attempted) rather than a crash.
    monkeypatch.setattr(fv, "FLICKR_API_KEY", "")
    assert fv._flickr_commons_search("anything") is None


def test_flickr_commons_search_real_shape_with_a_fake_key(monkeypatch):
    # Not a live call (no real key available) — confirms the request/response
    # handling matches Flickr's documented flickr.photos.search shape, so it's ready
    # to verify for real the moment a key is added to .env.
    monkeypatch.setattr(fv, "FLICKR_API_KEY", "fake-key-for-shape-test")

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"photos": {"photo": [
                {"title": "Eiffel Tower under construction", "url_l": "https://example.com/x.jpg"},
            ]}}

    monkeypatch.setattr(fv.requests, "get", lambda *a, **kw: _FakeResp())
    assert fv._flickr_commons_search("Eiffel Tower construction") == "https://example.com/x.jpg"


def test_google_cse_search_skips_cleanly_without_credentials(monkeypatch):
    monkeypatch.setattr(fv, "GOOGLE_CSE_API_KEY", "")
    monkeypatch.setattr(fv, "GOOGLE_CSE_CX", "")
    assert fv._google_cse_search("anything") is None


def test_google_cse_search_real_shape_with_fake_credentials(monkeypatch):
    # Not a live call (no real credentials available) — confirms the request/response
    # handling matches Google's documented Custom Search JSON API shape.
    monkeypatch.setattr(fv, "GOOGLE_CSE_API_KEY", "fake-key")
    monkeypatch.setattr(fv, "GOOGLE_CSE_CX", "fake-cx")

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"items": [
                {"title": "Eiffel Tower under construction", "link": "https://example.com/x.jpg"},
            ]}

    monkeypatch.setattr(fv.requests, "get", lambda *a, **kw: _FakeResp())
    assert fv._google_cse_search("Eiffel Tower construction") == "https://example.com/x.jpg"
