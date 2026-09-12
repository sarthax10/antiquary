#!/usr/bin/env python3
"""Explainer motion graphics: a small, animated on-screen graphic for beats whose
narration names a specific year/date — not more editing polish on stock footage, but an
actual graphic generated *from the content itself* to help a viewer place an event in
time, the way a professional history/explainer video (Kurzgesagt-style) uses an animated
timeline marker. This is what the original prompt's "if there's timeline or stuff like
that requires animations for making the user understand" line actually asked for — see
Claude outputs/UNDERSTANDING.md #4 and OPEN_ISSUES.md #2. It is deliberately distinct
from render.py's existing Ken Burns pan / caption pop-in / transition variety, which are
real but are about *how footage is cut and treated*, not about generating an explanatory
graphic.

Built entirely from ffmpeg's own drawbox/drawtext filters — no new dependency, no
pre-rendered assets, no extra pass over the video. A horizontal line draws in, a marker
lands at its tip, and the year fades in, all timed against the beat's own local clock
(`t`, zeroed by the setpts=PTS-STARTPTS render.py already applies before this runs), then
the whole thing disappears well before the beat's own cut, so it reads as a purposeful
accent rather than a sustained banner.
"""
import re

# An explicit era marker (BCE/BC/CE/AD) makes even a short number unambiguous ("44 BCE");
# without one, require a full 4-digit year in a plausible historical-to-present range so
# an unrelated small number ("3 ships", "12 men") is never mistaken for a date.
_ERA_RE = re.compile(r"\b(\d{1,4})\s*(BCE|BC|CE|AD)\b", re.IGNORECASE)
_BARE_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")

FONT_PATH = "/usr/share/fonts/truetype/antiquary/Anton-Regular.ttf"
ACCENT_COLOR = "0xE0A94D"  # the app's own warm gold accent (tungsten), for visual continuity

BOX_X, BOX_Y, BOX_W, BOX_H = 80, 190, 920, 150
LINE_X, LINE_Y, LINE_W_MAX, LINE_H = 140, 290, 700, 6
MARKER_W, MARKER_H = 16, 30
TEXT_X, TEXT_Y, FONT_SIZE = 160, 320, 64

DRAW_DURATION = 0.6              # seconds for the line to grow in
FADE_START, FADE_DURATION = 0.4, 0.5   # year text fade-in window
MIN_SHOW = 1.0                   # below this, skip the overlay entirely — not enough
                                  # time left in the beat for it to read as intentional
MAX_SHOW = 2.2                   # cap even on a long beat — an accent, not a banner
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


def timeline_overlay_filter(label: str, beat_duration: float, in_label: str, out_label: str) -> str | None:
    """A drawbox/drawtext filter chain fragment (`[in_label] ... [out_label]`, both
    already-scaled 1080x1920 video streams) animating a timeline marker + year callout
    over the first ~2 seconds of a beat. Returns None if the beat is too short for the
    animation to read as intentional rather than jarring — callers must handle that by
    keeping the original label unchanged."""
    show_until = min(MAX_SHOW, beat_duration - TAIL_MARGIN)
    if show_until < MIN_SHOW:
        return None

    escaped = label.replace("'", "").replace(":", "").replace("\\", "")
    grow = f"if(lt(t,{DRAW_DURATION}),(t/{DRAW_DURATION})*{LINE_W_MAX},{LINE_W_MAX})"
    marker_x = f"{LINE_X}+({grow})-{MARKER_W // 2}"
    alpha = f"if(lt(t,{FADE_START + FADE_DURATION}),max(0,(t-{FADE_START})/{FADE_DURATION}),1)"
    enable = f"between(t,0,{show_until:.3f})"
    marker_enable = f"between(t,{DRAW_DURATION - 0.05:.3f},{show_until:.3f})"

    return (
        f"[{in_label}]"
        f"drawbox=x={BOX_X}:y={BOX_Y}:w={BOX_W}:h={BOX_H}:color=black@0.55:t=fill:enable='{enable}',"
        f"drawbox=x={LINE_X}:y={LINE_Y}:w='{grow}':h={LINE_H}:color={ACCENT_COLOR}:t=fill:enable='{enable}',"
        f"drawbox=x='{marker_x}':y={LINE_Y - (MARKER_H - LINE_H) // 2}:w={MARKER_W}:h={MARKER_H}:"
        f"color={ACCENT_COLOR}:t=fill:enable='{marker_enable}',"
        f"drawtext=text='{escaped}':fontfile={FONT_PATH}:fontsize={FONT_SIZE}:fontcolor=white:"
        f"x={TEXT_X}:y={TEXT_Y}:alpha='{alpha}':enable='{enable}'"
        f"[{out_label}]"
    )
