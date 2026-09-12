"""Tests for pipeline/motion_graphics.py — the animated timeline-marker graphic for
beats that name a specific year (see Claude outputs/OPEN_ISSUES.md #2 for why this
exists: it's a real, distinct explainer-graphics feature, not the same thing as the
existing Ken Burns pan/caption pop-in/transition-variety editing polish). Pure-function
tests only — no ffmpeg invocation here; the actual filter string was verified by hand
against a real ffmpeg render (frames extracted and visually inspected) before this was
wired into render.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import motion_graphics as mg  # noqa: E402


def test_extract_year_label_bare_four_digit_year():
    assert mg.extract_year_label("In 1872, a ship was found adrift.") == "1872"


def test_extract_year_label_prefers_era_marked_date():
    assert mg.extract_year_label("Around 1200 BCE, the Bronze Age collapsed.") == "1200 BCE"


def test_extract_year_label_short_number_with_era_is_not_ignored():
    assert mg.extract_year_label("Caesar was killed in 44 BCE by senators.") == "44 BCE"


def test_extract_year_label_ignores_unrelated_small_numbers():
    assert mg.extract_year_label("The 3 ships carried 12 men each.") is None


def test_extract_year_label_no_date_in_text():
    assert mg.extract_year_label("Nobody knows what really happened that night.") is None


def test_extract_year_label_empty_text():
    assert mg.extract_year_label("") is None
    assert mg.extract_year_label(None) is None


def test_timeline_overlay_filter_skips_too_short_beat():
    # MIN_SHOW is 1.5s and TAIL_MARGIN is 0.3s, so anything under 1.8s can't fit.
    assert mg.timeline_overlay_filter("1872", 1.0, "v0", "v0o") is None


def test_timeline_overlay_filter_caps_show_time_on_long_beat():
    result = mg.timeline_overlay_filter("1872", 30.0, "v0", "v0o")
    assert result is not None
    # MAX_SHOW is 2.2 — a 30s beat must not keep the overlay up the whole time.
    assert f"between(t,0,{mg.MAX_SHOW:.3f})" in result


def test_timeline_overlay_filter_shrinks_show_time_on_short_beat():
    # 2.0s beat, 0.3s tail margin -> show_until = 1.7s: above MIN_SHOW (1.5s, so the
    # overlay still fits) but below MAX_SHOW (2.6s, so it's the beat that's constraining
    # show_until here, not the cap).
    result = mg.timeline_overlay_filter("1872", 2.0, "v0", "v0o")
    assert result is not None
    assert "between(t,0,1.700)" in result


def test_timeline_overlay_filter_references_in_and_out_labels():
    result = mg.timeline_overlay_filter("1872", 5.0, "v3", "v3o")
    assert result.startswith("[v3]")
    assert result.endswith("[v3o]")


def test_timeline_overlay_filter_sanitizes_label_text():
    # A label must never be able to inject a stray quote/colon into the drawtext option
    # value it's embedded in — both are structurally significant in ffmpeg's filtergraph
    # syntax (colon separates filter options, quote closes the text='...' value).
    result = mg.timeline_overlay_filter("19'72:x", 5.0, "v0", "v0o")
    text_value = result.split("text='", 1)[1].split("'", 1)[0]
    assert "'" not in text_value
    assert ":" not in text_value


def test_timeline_overlay_filter_underline_width_is_never_a_t_expression():
    # Regression test for a real, confirmed ffmpeg bug: drawbox has its own option
    # literally named `t` (alias for `thickness`, set here via `t=fill`), and inside
    # drawbox's *own* w=/h=/x=/y= expressions the bare identifier `t` resolves to that
    # option's value, not to elapsed time — silently, with no parse error. A width
    # expression like `w='(210*...*t...)'` looked correct on paper but always evaluated
    # against the thickness option's value (verified: constant regardless of real time
    # or -ss). The fix computes the eased width in Python and emits one drawbox per
    # short time window with a literal, static width — assert that shape here so a
    # future edit can't reintroduce a `t`-based width expression without this failing.
    result = mg.timeline_overlay_filter("1872", 3.5, "v0", "v0o")
    assert result is not None
    drawbox_calls = [seg for seg in result.split(",") if seg.startswith("drawbox=") or "]drawbox=" in seg]
    assert len(drawbox_calls) > 1, "expected multiple stepped drawbox segments for the underline"
    for call in drawbox_calls:
        w_value = call.split("w=", 1)[1].split(":", 1)[0]
        assert "t" not in w_value, f"drawbox width must be a static number, not a `t`-expression: {w_value!r}"
        float(w_value)  # must parse as a plain number


def test_underline_width_segments_grows_holds_and_shrinks():
    # Pure-function check on the eased width curve itself, independent of ffmpeg: starts
    # near 0, reaches the full width during the hold, ends near 0.
    segments = mg._underline_width_segments(
        entry_duration=0.55, exit_start=2.1, exit_duration=0.5, w_max=210
    )
    widths = [w for _, _, w in segments]
    assert widths[0] < 30  # just starting to grow
    assert any(w >= 209 for w in widths)  # reaches (approximately) full width somewhere
    assert widths[-1] < 30  # nearly gone by the end
    # Monotonically non-decreasing through the entry ramp, then non-increasing through exit.
    entry_widths = [w for s0, s1, w in segments if s1 <= 0.55]
    exit_widths = [w for s0, s1, w in segments if s0 >= 2.1]
    assert entry_widths == sorted(entry_widths)
    assert exit_widths == sorted(exit_widths, reverse=True)
