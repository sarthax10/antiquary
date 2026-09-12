#!/usr/bin/env python3
"""Synthesizes pipeline/assets/sfx/whoosh.mp3 — a soft, restrained rising-sweep whoosh
accent, used sparingly (see render.py) on accent transitions ("circleopen"/"radial" —
a named person entering/leaving frame relative to a place/event, see
render._transition_style) and motion-graphic reveals (see motion_graphics.py's
timeline-marker overlay), never on every cut, per Claude outputs/OPEN_ISSUES.md #18.

Why generated instead of a downloaded CC0 asset: Kenney.nl's freely-scriptable CC0
audio packs (interface-sounds, impact-sounds, digital-audio — all confirmed CC0 via
their own license page, downloaded and inspected during this pass) are uniformly
game/sci-fi flavored (click/confirm/error/zap/laser/impact) — no whoosh among them —
which would clash with this project's own "documentary, not content" bar (see #16's
commentary) even if one existed. Freesound.org mixes per-file licenses that can't be
reliably verified/downloaded without a human in a browser (its search page is CC0-only-
filterable but downloads need OAuth), and Pixabay's sound-effects section blocks
non-browser fetches outright (403). Synthesizing from ffmpeg's own noise/filter
primitives — the same "generate, don't source" approach already used for
motion_graphics.py and fetch_visuals.py's animated placeholder backdrop — sidesteps all
of that and carries zero licensing risk: this is generated output, not a third-party
asset, so there is no SOURCE.md for this directory (see GENERATION.md instead).

Technique: two independent pink-noise sources (different seeds so they don't
correlate), each bandpassed to a different center frequency (~320Hz "low" band,
~2200Hz "high" band), crossfaded via linear volume envelopes — the low band fades out
while the high band fades in over the clip's duration. That reads as a rising spectral
sweep ("whoosh in") without needing a genuinely time-varying filter cutoff, which
ffmpeg's bandpass/highpass/lowpass don't expose (their `f=` is a static frequency, not
a per-sample expression). A short overall fade-in/out avoids a click at either end.

Run manually / on asset changes only — this is a one-time asset-generation step, not
part of the render-time path (render.py just mixes in the resulting file, exactly like
a music track).
"""
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent / "assets" / "sfx" / "whoosh.mp3"
DURATION = 0.45
ATTACK = 0.04
RELEASE = 0.12


def generate() -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    d = DURATION
    lo = (
        f"anoisesrc=color=pink:sample_rate=44100:duration={d}:seed=17,"
        f"bandpass=f=320:width_type=o:w=1.3,"
        f"volume=eval=frame:volume='(1-t/{d})'[lo]"
    )
    hi = (
        f"anoisesrc=color=pink:sample_rate=44100:duration={d}:seed=41,"
        f"bandpass=f=2200:width_type=o:w=1.6,"
        f"volume=eval=frame:volume='(t/{d})'[hi]"
    )
    mix = (
        f"[lo][hi]amix=inputs=2:duration=first,volume=2.2,"
        f"afade=t=in:st=0:d={ATTACK},afade=t=out:st={d - RELEASE}:d={RELEASE}[out]"
    )
    filter_complex = ";".join([lo, hi, mix])
    cmd = [
        "ffmpeg", "-y", "-filter_complex", filter_complex, "-map", "[out]",
        "-t", str(d), "-c:a", "libmp3lame", "-b:a", "192k", str(OUT),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return OUT


if __name__ == "__main__":
    path = generate()
    print(path)
