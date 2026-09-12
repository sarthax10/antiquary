#!/usr/bin/env python3
"""Explainer motion graphics: a small, animated on-screen graphic for beats whose
narration names a specific year/date — not more editing polish on stock footage, but an
actual graphic generated *from the content itself* to help a viewer place an event in
time, the way a professional history/explainer video (Kurzgesagt-style) uses an animated
timeline marker. This is what the original prompt's "if there's timeline or stuff like
that requires animations for making the user understand" line actually asked for — see
Claude outputs/UNDERSTANDING.md #4 and OPEN_ISSUES.md #2.

v2 (this file): the v1 design — a wide flat semi-transparent bar, a linearly-growing
line, a square marker, a hard cut to nothing at the end — was called out directly as
looking like a generic template element ("like a basic element from Filmora"), and it
was a fair hit: linear motion and an abrupt vanish are exactly what an untreated,
off-the-shelf overlay looks like. This version fixes the actual causes:
  - No wide background bar — a tight box hugging just the year text (drawtext's own
    `box`/`boxcolor`/`boxborderw`, confirmed to fade as one unit with the text's own
    `alpha`), which reads as a considered lower-third instead of a template banner.
  - Eased motion (cubic ease-out on entry, cubic ease-in on exit) instead of linear —
    the single biggest tell of "automated" motion is constant-velocity movement.
  - A real fade-and-slide OUT, not a hard `enable` cutoff — the accent line retracts and
    the text slides down and fades as it leaves, mirroring its entrance, so nothing pops
    out of existence.
  - The line is now a short underline beneath the year, not a bar spanning most of the
    frame — a wide horizontal bar reads as a lower-third *template*; a short accent
    underline reads as typography.

Built entirely from ffmpeg's own drawtext/drawbox filters — no new dependency, no
pre-rendered assets. Every expression below was verified against a real ffmpeg encode
with extracted frames before being wired into render.py (see tests/test_motion_graphics.py
for the regression coverage, and OPEN_ISSUES.md for the frame-by-frame verification
notes) — this is not assumed to work from reading the expressions alone.
"""
import re

# An explicit era marker (BCE/BC/CE/AD) makes even a short number unambiguous ("44 BCE");
# without one, require a full 4-digit year in a plausible historical-to-present range so
# an unrelated small number ("3 ships", "12 men") is never mistaken for a date.
_ERA_RE = re.compile(r"\b(\d{1,4})\s*(BCE|BC|CE|AD)\b", re.IGNORECASE)
_BARE_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")

FONT_PATH = "/usr/share/fonts/truetype/antiquary/Anton-Regular.ttf"
ACCENT_COLOR = "0xE0A94D"  # the app's own warm gold accent (tungsten), for visual continuity

# Maps a captions.py font dict's "name" (see captions.CAPTION_FONTS) to its actual font
# file, so the timeline-marker graphic can be set in the SAME face as the video's own
# captions instead of always hardcoding Anton regardless of what was picked for this
# video — a real type-system mismatch on 3 of 4 generated videos, found in the 2026-09-12
# team audit (OPEN_ISSUES.md #33). Kept here (not in captions.py) since this module owns
# FONT_PATH and is the only thing that needs the resolved file path, not the font dict.
_FONT_FILES = {
    "Anton": FONT_PATH,
    "Bebas Neue": "/usr/share/fonts/truetype/antiquary/BebasNeue-Regular.ttf",
    "Archivo Black": "/usr/share/fonts/truetype/antiquary/ArchivoBlack-Regular.ttf",
    "DejaVu Sans": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
}


def font_path_for(font: dict | None) -> str:
    """Resolves a captions.py-style font dict to its font file, falling back to this
    module's own default (Anton) if `font` is None or names a face not in `_FONT_FILES`
    (defensive against a future caption font being added here without a matching entry)."""
    if font:
        path = _FONT_FILES.get(font.get("name"))
        if path:
            return path
    return FONT_PATH

TEXT_X, TEXT_Y, FONT_SIZE = 96, 220, 84

# Illustrated-mode's per-beat keyword card (see beat_keyword_label()/render.py's use of
# it) reuses this same overlay mechanism with a smaller font and a truncated label,
# since an arbitrary visual_query phrase ("British army officers") is much longer than
# a year ("1863"/"44 BCE") and would risk overflowing the frame at FONT_SIZE.
ILLUSTRATED_FONT_SIZE = 56
ILLUSTRATED_LABEL_MAX_CHARS = 24
BOX_BORDER = 20  # padding between the text glyph and the tight-fitting box edge

UNDERLINE_X_OFFSET = 4          # relative to TEXT_X, so it sits under the text's left edge
UNDERLINE_Y_OFFSET = FONT_SIZE + BOX_BORDER + 14   # relative to TEXT_Y
UNDERLINE_W_MAX = 210
UNDERLINE_H = 5

ENTRY_DURATION = 0.55            # eased grow/slide/fade-in
EXIT_DURATION = 0.5              # eased shrink/slide/fade-out
SLIDE_DISTANCE = 26              # px the text travels on entrance (from below) / exit (down)

MIN_SHOW = 1.5                   # below this, skip the overlay — no room for a full
                                  # entrance + hold + exit to read as intentional
MAX_SHOW = 2.6                   # cap even on a long beat — an accent, not a banner
TAIL_MARGIN = 0.3                # keep clear of the beat's own cut/crossfade


def extract_year_label(text: str) -> str | None:
    """The first year-like mention in a beat's narration text, formatted for display —
    "1872", "44 BCE" — or None if the beat doesn't name a specific year."""
    if not text:
        return None
    m = _ERA_RE.search(text)
    if m:
        return f"{m.group(1)} {m.group(2).upper()}"
    m = _BARE_YEAR_RE.search(text)
    return m.group(1) if m else None


def beat_keyword_label(beat: dict) -> str | None:
    """A short, presentable phrase for illustrated-mode's per-beat keyword card (see
    render.py) — every beat gets SOME motion-graphic content in illustrated mode, not
    only the ones whose narration happens to name a year (see Claude outputs/
    OPEN_ISSUES.md #56/#59: a real user report that 3 of 4 beats in an illustrated video
    showed nothing but the plain backdrop, since only extract_year_label's narrow
    trigger fired anything at all). Sourced from the beat's own `visual_query` — already
    a short, on-topic phrase the writer model produced for sourcing (see
    generate_script.py), which makes it a natural label here too, not a new derived
    concept. Uppercased to read as a title card rather than a caption fragment, and
    truncated (with an ellipsis) since an arbitrary phrase can be much longer than a
    year and would otherwise risk overflowing the frame at any reasonable font size."""
    query = (beat.get("visual_query") or "").strip()
    if not query:
        return None
    label = query.upper()
    if len(label) > ILLUSTRATED_LABEL_MAX_CHARS:
        label = label[: ILLUSTRATED_LABEL_MAX_CHARS - 1].rstrip() + "…"
    return label


def _ease_out_cubic(x_expr: str) -> str:
    """1-(1-x)^3 — fast start, gentle settle. Used for every entrance motion; a linear
    ramp here is exactly what read as untreated/automated in the previous version.
    ffmpeg-expression form: valid for drawtext's alpha=/y= (drawtext has no option named
    `t`, so its `t` genuinely means elapsed seconds — see the module-level note above
    _underline_width_segments() for why this is NOT safe to use for drawbox's w=/h=/x=/y=."""
    clamped = f"min(max(({x_expr}),0),1)"
    return f"(1-pow(1-{clamped},3))"


def _ease_in_cubic(x_expr: str) -> str:
    """x^3 — gentle start, fast finish. Used for every exit motion, so a graphic
    accelerates away instead of instantly vanishing. Same drawtext-only caveat as
    _ease_out_cubic above."""
    clamped = f"min(max(({x_expr}),0),1)"
    return f"pow({clamped},3)"


def _ease_out_cubic_py(x: float) -> float:
    """Plain-Python twin of _ease_out_cubic(), evaluated at build time — see
    _underline_width_segments() for why the underline's width has to be computed here
    instead of as an ffmpeg expression."""
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def _ease_in_cubic_py(x: float) -> float:
    """Plain-Python twin of _ease_in_cubic() — see _ease_out_cubic_py()."""
    x = min(max(x, 0.0), 1.0)
    return x ** 3


# How finely the eased width ramp is sampled, in seconds per step. ~20 steps/sec reads as
# smooth motion for a sub-second eased ramp (well under render.py's own 30fps, which
# would be the point of genuinely no return on perceptible smoothness) without emitting
# an excessive number of chained drawbox filters per graphic.
_WIDTH_STEP_DT = 0.05


def _underline_width_segments(
    entry_duration: float, exit_start: float, exit_duration: float, w_max: float
) -> list[tuple[float, float, float]]:
    """Returns [(window_start, window_end, width_px), ...] approximating the eased
    grow-hold-shrink underline animation as discrete fixed-width segments.

    This exists because of a real, confirmed ffmpeg quirk that the original per-frame
    `w='<eased expression using t>'` approach ran straight into: drawbox has its own
    option literally named `t` (an alias for `thickness`, e.g. `t=fill`), and inside
    drawbox's *own* w=/h=/x=/y= expressions, the bare identifier `t` resolves to that
    option's value, not to elapsed time — there is no parse error or warning, since `t`
    IS a recognized identifier in that context, just not the one intended. Confirmed by
    isolated testing: with `t=fill` set, `w='(500*t)'` evaluated to the *thickness*
    option's internal sentinel for "fill" (a huge value that clips to the frame edge)
    at every timestamp regardless of `-ss`/real elapsed time; with `t=2` (a plain
    numeric thickness), the same expression evaluated to a constant `500*2=1000`,
    completely ignoring real time. (`enable=` is unaffected — it's evaluated by
    ffmpeg's separate timeline-expression framework, confirmed by a matching isolated
    test — which is exactly what this function's fixed-width, `enable`-gated segments
    rely on instead.) The earlier "w=0 is a fill-to-edge sentinel" theory was a real,
    separately-confirmed ffmpeg behavior, but it was not the actual root cause here —
    it was a red herring the width being consistently near-frame-width made plausible.

    The fix: compute the eased width curve in plain Python (this function), then emit
    one drawbox per short time window with a literal, static width, each gated by a real
    `enable='between(t,...)'` clause — `enable` genuinely receives elapsed seconds."""
    segments: list[tuple[float, float, float]] = []

    def add_ramp(t0: float, t1: float, width_at) -> None:
        span = t1 - t0
        if span <= 0:
            return
        steps = max(1, round(span / _WIDTH_STEP_DT))
        for i in range(steps):
            s0 = t0 + span * i / steps
            s1 = t0 + span * (i + 1) / steps
            mid = (s0 + s1) / 2
            segments.append((s0, s1, width_at(mid)))

    add_ramp(0.0, entry_duration, lambda t: w_max * _ease_out_cubic_py(t / entry_duration))
    if exit_start > entry_duration:
        segments.append((entry_duration, exit_start, w_max))
    add_ramp(
        exit_start,
        exit_start + exit_duration,
        lambda t: w_max * (1 - _ease_in_cubic_py((t - exit_start) / exit_duration)),
    )
    return segments


def timeline_overlay_filter(
    label: str, beat_duration: float, in_label: str, out_label: str,
    font_path: str | None = None, fontsize: int = FONT_SIZE,
) -> str | None:
    """A drawtext+drawbox filter chain fragment (`[in_label] ... [out_label]`, both
    already-scaled 1080x1920 video streams) animating a year callout (or, via
    `fontsize`, illustrated-mode's per-beat keyword card — see beat_keyword_label) with
    a coordinated ease-in/hold/ease-out — entrance and exit mirror each other rather
    than the graphic just appearing and later being cut off. Returns None if the beat is
    too short for a full entrance+hold+exit to read as intentional rather than jarring."""
    show_until = min(MAX_SHOW, beat_duration - TAIL_MARGIN)
    if show_until < MIN_SHOW:
        return None
    exit_start = show_until - EXIT_DURATION
    resolved_font_path = font_path or FONT_PATH
    underline_y_offset = fontsize + BOX_BORDER + 14  # see UNDERLINE_Y_OFFSET's own
    # comment — recomputed here (not read from the module constant) so a non-default
    # fontsize still gets a correctly-spaced underline instead of one sized for FONT_SIZE.

    escaped = label.replace("'", "").replace(":", "").replace("\\", "")

    # ge: 0->1 eased over the entrance window, then holds at 1 for the rest of the clip
    # (t keeps climbing past ENTRY_DURATION, but the expression clamps x to 1 first).
    ge = _ease_out_cubic(f"t/{ENTRY_DURATION}")
    # xe_pos: 0 until the exit window starts, then 0->1 eased-IN over EXIT_DURATION —
    # right curve for a "departure" motion (slide/shrink accelerating away).
    xe_pos = _ease_in_cubic(f"(t-{exit_start:.3f})/{EXIT_DURATION}")
    # xe_alpha: same window, but eased-OUT — an ease-in curve applied to opacity leaves
    # the graphic looking fully solid for most of the exit window and then vanishing
    # abruptly in its last instants (checked by rendering and inspecting a mid-exit
    # frame — barely any visible dimming at the window's midpoint). Ease-out dims
    # quickly and evenly from the start of the exit instead, which is what actually
    # reads as a graceful fade rather than a delayed pop.
    xe_alpha = _ease_out_cubic(f"(t-{exit_start:.3f})/{EXIT_DURATION}")

    # Underline width: grows in eased, then shrinks back eased — never a hard cut. See
    # _underline_width_segments()'s docstring for why this is built as a chain of
    # fixed-width, enable-gated drawbox filters rather than one drawbox with a
    # time-varying w= expression (the latter silently doesn't work — drawbox's own `t`
    # option, not elapsed time, wins inside its w=/h=/x=/y= expressions).
    underline_x = TEXT_X + UNDERLINE_X_OFFSET
    underline_y = TEXT_Y + underline_y_offset
    width_segments = _underline_width_segments(ENTRY_DURATION, exit_start, EXIT_DURATION, UNDERLINE_W_MAX)
    underline_filters = ",".join(
        f"drawbox=x={underline_x}:y='{underline_y}':w={w:.2f}:h={UNDERLINE_H}:"
        f"color={ACCENT_COLOR}:t=fill:enable='between(t,{s0:.3f},{s1:.3f})'"
        for s0, s1, w in width_segments
    )

    # Text alpha: fades in, holds, fades out — one continuous expression, not a toggle.
    text_alpha = f"({ge})*(1-({xe_alpha}))"
    # Text y: starts SLIDE_DISTANCE below its resting position and eases up into place;
    # on exit it eases back down (departure curve) by the same distance as it fades —
    # a real, coordinated entrance/exit rather than a static position that just fades.
    # drawtext has no option named `t` (confirmed: `ffmpeg -h filter=drawtext` lists no
    # such option), so unlike drawbox's w=/h=/x=/y=, `t` here genuinely means elapsed
    # seconds — this expression form is safe.
    text_y = f"{TEXT_Y}+{SLIDE_DISTANCE}*(1-({ge}))+{SLIDE_DISTANCE}*({xe_pos})"

    enable = f"between(t,0,{show_until:.3f})"

    return (
        f"[{in_label}]"
        f"{underline_filters},"
        f"drawtext=text='{escaped}':fontfile={resolved_font_path}:fontsize={fontsize}:fontcolor=white:"
        f"x={TEXT_X}:y='{text_y}':box=1:boxcolor=black@0.45:boxborderw={BOX_BORDER}:"
        f"alpha='{text_alpha}':enable='{enable}'"
        f"[{out_label}]"
    )
