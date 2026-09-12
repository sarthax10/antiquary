# Sound-design accents — generated, not sourced

Unlike `pipeline/assets/music/`, this directory has no `SOURCE.md` because nothing here
is a third-party asset: `whoosh.mp3` is synthesized entirely from ffmpeg's own noise/
filter primitives by `pipeline/generate_sfx.py` (run manually, on asset changes only —
it is not part of the render-time path). Zero licensing risk, by construction.

## Why generated instead of downloaded

The same CC0-licensing discipline used for the music bed was applied here first:
Kenney.nl's freely-scriptable CC0 audio packs (`interface-sounds`, `impact-sounds`,
`digital-audio` — all confirmed CC0 via their own license pages) were downloaded and
inspected, but every sound in them is game/sci-fi flavored (click, confirm, error, zap,
laser, impact) — nothing resembling a soft cinematic whoosh, and none of it fits this
project's own "documentary, not content" bar even where a whoosh-adjacent sound existed.
Freesound.org mixes per-file licenses that can't be reliably verified/downloaded without
a human in a browser (its search is CC0-filterable, but download requires OAuth).
Pixabay's sound-effects section blocks non-browser fetches outright (403). Generating
the sound from ffmpeg's own primitives — the same approach already used for
`motion_graphics.py` and `fetch_visuals.py`'s animated placeholder backdrop — sidesteps
all of that.

## How `whoosh.mp3` is made

Two independent pink-noise sources (different seeds, so they don't correlate), each
bandpassed to a different center frequency (~320Hz "low" band, ~2200Hz "high" band),
crossfaded via linear volume envelopes: the low band fades out while the high band
fades in over the clip's 0.45s duration. That reads as a rising spectral sweep without
needing a genuinely time-varying filter cutoff (ffmpeg's bandpass/highpass/lowpass
expose a static frequency, not a per-sample expression). A short overall fade-in/out
avoids a click at either end.

**Verified, not assumed**: decoded the real mp3 to raw PCM and computed an FFT-based
spectral centroid in early/mid/late thirds of the clip — confirmed a real, monotonic,
substantial rise (2141Hz → 3445Hz → 4124Hz on the reference build), a genuine fade-in
(first 10ms peak ~12% of the clip's overall peak, not a hard edge), and no clipping.

## How it's used

`render.py` mixes this in sparingly (see its own `SFX_VOLUME`/cue-collection logic) on
exactly two moments, never on every cut:
- An **accent transition** (`"circleopen"`/`"radial"` — a named person entering/leaving
  frame relative to a place/event, see `_transition_style()`), timed to the middle of
  the crossfade.
- A **motion-graphic reveal** (the year/timeline-marker overlay, see
  `motion_graphics.py`), timed just after that beat's own clip begins.

Regenerate with `python pipeline/generate_sfx.py` if the synthesis parameters ever
change; commit the resulting file the same way the music tracks are committed (this is
a small, fixed, versioned asset — not something regenerated at render time).
