#!/usr/bin/env python3
"""Render the final vertical video from per-beat visuals (see fetch_visuals.py/tts.py),
narration audio, and burned-in styled captions (.ass from captions.py).

Usage: render.py <narration.mp3> <captions.ass> <output.mp4> <beats.json>
  beats.json: a JSON list of {"path", "entity_type", "face": [fx,fy]|null, "duration",
  "text" (optional — enables the year/timeline overlay, see motion_graphics.py)}

Each beat's own visual plays for exactly its own real narration duration (from tts.py's
per-beat synthesis) — not a flat division of total runtime — so a cut lands where the
sentence it illustrates actually does. Consecutive beats about the same kind of subject
(same entity_type) crossfade smoothly into each other with a gentle directional wipe; a
plain change of subject cuts hard; and a named person entering/leaving frame relative to
a place or event gets a sparing, purposeful accent transition (circleopen/radial) — see
`_transition_style()`. Still images get a Ken Burns pan+zoom framed around the beat's
detected face when there is one (fetch_visuals.py's OpenCV pass) instead of blindly
cropping to center — the crop drifts (a real pan, not just a scale change) from that point
toward a nearby offset, and alternates both zoom direction and pan direction across beats
for variety (see `_zoompan_expr()`/`_pan_targets()`). A beat whose narration names a
specific year additionally gets an animated timeline-marker graphic over its first ~2s
(see motion_graphics.py) — an actual explainer graphic generated from the content, not
more footage treatment. A fixed color grade, subtle vignette and film grain pass, plus an
optional ducked music bed, are the last steps before captions burn in.

Requires ffmpeg on PATH.
"""
import json
import random
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import motion_graphics

WIDTH, HEIGHT = 1080, 1920
FPS = 30
ZOOM_RATE = 0.0008
ZOOM_MAX = 1.3
PAN_MARGIN = 0.09  # fractional drift of the crop center over a clip's duration — kept
# small on purpose: a slow, deliberate documentary pan, not a swoop. Safe against the
# face-framing requirement below: even at ZOOM_MAX the crop window's half-width/height in
# frame-fraction terms is 1/(2*ZOOM_MAX) ~= 0.38, well beyond this drift, so a face or
# center point that starts in-frame never drifts out of the crop.
XFADE_CUT = 0.08  # a change of subject: near-instant, reads as a hard cut
XFADE_SMOOTH = 0.45  # same subject continuing, or a deliberate accent transition
_PERSON_ACCENT_TYPES = ("place", "event")
MAX_CLIPS = 8
VIDEO_EXTS = (".mp4", ".mov", ".webm", ".m4v")

# Per-beat framing/mood intent (Professional Quality Roadmap Tier 3 #13) — a lightweight
# camera-planning hint the writer model proposes per beat (see generate_script.py's
# FRAMING_TYPES/BEATS_SYSTEM_PROMPT), closing the gap between "shot list" (what's on
# screen) and actual camera planning (how it moves). Multipliers on the existing
# zoom/pan mechanics rather than a new rendering system: "push_in"/"pull_back" force a
# deliberate zoom direction (instead of the old plain index-parity alternation) and
# soften the pan so the zoom itself reads as the intentional move; "hold_static"
# dampens BOTH zoom and pan well below the default for a beat that should read as
# comparatively still; "pan" does the opposite — flattens the zoom rate and widens the
# pan margin so lateral drift carries the beat instead. An absent/unrecognized framing
# value (any beat from before this existed, or a small-model miss) falls all the way
# back to the exact pre-existing behavior (1.0x both multipliers, plain index-parity
# zoom-direction alternation) — this is additive, not a behavior change for anyone not
# using it.
_FRAMING_ZOOM_RATE_MULT = {"push_in": 1.6, "pull_back": 1.6, "hold_static": 0.3, "pan": 0.5}
_FRAMING_PAN_MARGIN_MULT = {"push_in": 0.7, "pull_back": 0.7, "hold_static": 0.35, "pan": 1.8}

MUSIC_DIR = Path(__file__).resolve().parent / "assets" / "music"
MUSIC_VOLUME = 0.12

# Sparing sound-design accent (see Claude outputs/OPEN_ISSUES.md #18 and
# pipeline/assets/sfx/GENERATION.md) — a soft synthesized whoosh, never layered onto
# every cut. Fired only on an accent transition (circleopen/radial) or a motion-graphic
# reveal (see _accumulate_beat_starts/the sfx_cues collection in render()). Silently
# skipped if the file is missing, same graceful-degradation convention as music.
SFX_DIR = Path(__file__).resolve().parent / "assets" / "sfx"
WHOOSH_PATH = SFX_DIR / "whoosh.mp3"
SFX_VOLUME = 0.35
_ACCENT_TRANSITIONS = ("circleopen", "radial")

# Per-clip auto black/white-point correction, applied before the single shared creative
# grade below — "correction before grading" (see Claude outputs/PROFESSIONAL_QUALITY_
# ROADMAP.md §1.4/§7 Tier 1 #1). Our clips come from three unrelated origins (Wikidata
# portraits, Commons scans, Pexels stock) with no shared color science, and today only
# the shared grade touches them — this is the single biggest cause of clips in one video
# visibly not belonging to the same "production." independence=0 links R/G/B scaling
# (stretches contrast/exposure range without shifting hue/white balance — a corrective
# move, not a creative one); strength=0.6 is deliberately partial, not a full stretch,
# so a source image with genuine intentional contrast isn't flattened; smoothing damps
# frame-to-frame flicker on real video clips (irrelevant for a still, harmless either way).
CLIP_NORMALIZE = "normalize=independence=0:strength=0.6:smoothing=20"

# Secondary, skin-tone-targeted correction — distinct from CLIP_NORMALIZE above, which
# stretches RGB *levels* globally and can't fix a hue-specific cast (see
# PROFESSIONAL_QUALITY_ROADMAP.md §7 Tier 3 #10). Old Wikidata/Commons portrait scans
# (aged paper, period photochemistry, lossy digitization) commonly carry a yellow/sepia
# cast — excess red+green relative to blue — that sits specifically in the range of
# luminosities real skin tones occupy, which spans midtones through highlights (a
# forehead highlight reads brighter than a cheek in shadow). `colorbalance`'s tonal-range
# controls were chosen over `selectivecolor`'s hue-range buckets after real testing
# showed selectivecolor's fuzzy hue/luminosity membership barely touched a bright,
# already fairly-neutral skin tone (~1-2/255 shift) — too weak to call a real
# correction. colorbalance's own per-range weighting turned out to matter too: applying
# only to midtones (rm/gm/bm) had *zero* effect on a bright, highlight-range skin tone
# (confirmed directly) — real skin pixels commonly sit there, not at true midtone
# luminosity — so both midtones and highlights get the same small nudge, confirmed by
# testing against skin tones at two different real luminosity levels (see
# tests/test_render.py). Small magnitude throughout (correction, not a stylizing grade),
# matching CLIP_NORMALIZE's own "partial, not full" philosophy. Only applied to
# "person" beats' own still images (paintings/photos/busts) — never to a real video
# clip (person beats never source real video, only Wikidata/Commons/placeholder — see
# fetch_visuals._fetch_person) and never to illustrated-mode's synthetic backdrops
# (which have no skin-tone content to correct at all).
#
# Honest limit, stated plainly: this is a real, verified corrective mechanism (mechanism
# and direction confirmed against real, decoded pixel output — see OPEN_ISSUES.md #58),
# not a creatively "tuned" result — confirming it looks right across many real, wildly
# different historical portrait sources (a 1600s oil painting vs. a 1920s photograph vs.
# a modern museum scan) is inherently a human visual-judgment task the roadmap itself
# flagged as needing "real tuning/testing," not something a single automated pass can
# claim to have finished.
SKIN_TONE_CORRECTION = "colorbalance=rm=-0.08:gm=-0.03:bm=0.08:rh=-0.08:gh=-0.03:bh=0.08"

# Target integrated loudness for the final mix — matches YouTube's own normalization
# target (see PROFESSIONAL_QUALITY_ROADMAP.md §1.5/§7 Tier 2 #8), so a video isn't
# perceptibly re-adjusted (and its dynamics further squashed) by the platform on top of
# whatever level render.py already produced. TP (true peak ceiling) and LRA (loudness
# range) use ffmpeg's own loudnorm defaults tuned slightly for narration+music content.
LOUDNORM = "loudnorm=I=-14:LRA=11:TP=-1.5"

_SUBJECT_STOPWORDS = frozenset({
    "a", "an", "the", "of", "in", "at", "on", "and", "to", "with", "his", "her", "their",
    "its", "for", "from", "by", "as", "is", "was", "were", "are", "this", "that",
})


def _subject_key(beat: dict) -> set[str]:
    """A rough bag-of-significant-words from a beat's own visual_query — used to tell
    whether two consecutive beats that happen to share an entity_type are actually about
    the *same* subject (a person beat about Caesar, followed by another about Caesar) or
    just coincidentally the same type (Caesar, then Brutus — both "person", but a real
    subject change that deserves a hard cut, not a continuity crossfade). See
    OPEN_ISSUES.md audit #34 — entity_type alone was never a claim about sameness."""
    words = re.findall(r"[a-z']+", (beat.get("visual_query") or "").lower())
    return {w for w in words if w not in _SUBJECT_STOPWORDS and len(w) > 2}


def _same_subject(a: dict, b: dict) -> bool:
    ka, kb = _subject_key(a), _subject_key(b)
    if not ka or not kb:
        return False
    overlap = ka & kb
    return bool(overlap) and len(overlap) / min(len(ka), len(kb)) >= 0.4


def get_audio_duration(audio_path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _cap_beats(beats: list[dict], max_clips: int) -> list[dict]:
    """Beat count is already bounded upstream (the writer prompt asks for 4-6), but this
    keeps render.py safe standalone — any overflow's duration is folded into the last
    kept beat rather than silently dropping narration time."""
    if len(beats) <= max_clips:
        return beats
    kept = [dict(b) for b in beats[:max_clips]]
    kept[-1]["duration"] += sum(b["duration"] for b in beats[max_clips:])
    return kept


def _transition_style(a: dict, b: dict, index: int) -> tuple[float, str]:
    """Picks both the xfade duration and the ffmpeg transition= type for the cut from beat
    a to beat b (index is this transition's position, for deterministic direction
    alternation). Three cases, chosen the way a real edit would use them — see
    `ffmpeg -h filter=xfade` for the confirmed transition name list on this build:
      - same subject continuing (same entity_type *and* a real overlap between the two
        beats' own visual_query words, via _same_subject() — matching entity_type alone
        isn't a claim about sameness: a "person" beat about Caesar followed by a "person"
        beat about Brutus is a real subject change, not a continuation, even though both
        are "person"; see OPEN_ISSUES.md audit #34): a real crossfade duration, with a
        gentle directional "smooth" wipe rather than a plain dissolve — reads as connected
        motion. Direction alternates by transition index so it isn't the same slide twice
        running.
      - a named person entering or leaving frame relative to a place/event: the one kind
        of subject change worth an actual visual accent, since introducing or leaving a
        specific historical figure is a real narrative turn — "circleopen" (a spotlight-
        style reveal) when a person appears, "radial" when a person's beat gives way to
        their broader world/event. Uses the longer (smooth) duration so the effect is
        actually visible, but stays sparing: only these two entity_type pairings qualify,
        and "person" beats are the minority of a typical 4-6 beat script.
      - every other subject change: unchanged from before — a near-instant hard cut.
    """
    at, bt = a.get("entity_type"), b.get("entity_type")
    if at and at == bt and _same_subject(a, b):
        return XFADE_SMOOTH, ("smoothleft" if index % 2 == 0 else "smoothright")
    if bt == "person" and at in _PERSON_ACCENT_TYPES:
        return XFADE_SMOOTH, "circleopen"
    if at == "person" and bt in _PERSON_ACCENT_TYPES:
        return XFADE_SMOOTH, "radial"
    return XFADE_CUT, "fade"


def _pan_targets(px: float, py: float, index: int, pan_margin: float = PAN_MARGIN) -> tuple[float, float]:
    """End point of the Ken Burns pan, given its start point (the detected face center, or
    plain frame center) and the beat index. The drift direction cycles deterministically
    through the four diagonal quadrants every 4 beats (reusing the same index that drives
    zoom_in alternation for the horizontal component, and a slower-flipping vertical
    component) so consecutive beats don't all pan the same way, while staying reproducible
    for testing/debugging rather than randomized. `pan_margin` defaults to the module
    constant but is scaled by a beat's framing hint, if any — see _FRAMING_PAN_MARGIN_MULT."""
    dx = pan_margin if index % 2 == 0 else -pan_margin
    dy = (pan_margin * 0.6) if (index // 2) % 2 == 0 else -(pan_margin * 0.6)
    return min(0.95, max(0.05, px + dx)), min(0.95, max(0.05, py + dy))


def _resolve_zoom_in(framing: str | None, index: int) -> bool:
    """"push_in"/"pull_back" force a deliberate zoom direction; anything else (no
    framing hint, "hold_static", "pan", or an unrecognized value) falls back to the
    original plain index-parity alternation — variety with no particular intent, exactly
    the pre-existing default behavior for every beat that doesn't specify one."""
    if framing == "push_in":
        return True
    if framing == "pull_back":
        return False
    return index % 2 == 0


def _zoompan_expr(
    px: float, py: float, zoom_in: bool, index: int, frames: int, framing: str | None = None,
) -> tuple[str, str, str]:
    """Ken Burns z/x/y expressions that zoom toward/away from the fractional point (px,
    py) — defaults to dead-center (0.5, 0.5) for a plain image, or the beat's detected face
    center when fetch_visuals.py found one — the same as before, PLUS a genuine pan: the
    crop center drifts linearly from (px, py) to a second point (`_pan_targets`) over the
    clip's duration, using ffmpeg's own output-frame-count variable `on` against the known
    total frame count so the drift is exactly in sync with the clip, no separate clock
    needed. x/y stay clamped with the same min/max approach as before so the animated,
    moving target can never pull the crop window outside the source frame at any frame.

    `framing`, when it names a recognized hint (see _FRAMING_ZOOM_RATE_MULT/
    _FRAMING_PAN_MARGIN_MULT), scales the zoom rate and pan margin so the beat reads as
    the intended camera move rather than the same generic drift every other beat gets —
    still built from the same primitives, not a new mechanism."""
    zoom_rate = ZOOM_RATE * _FRAMING_ZOOM_RATE_MULT.get(framing, 1.0)
    pan_margin = PAN_MARGIN * _FRAMING_PAN_MARGIN_MULT.get(framing, 1.0)
    if zoom_in:
        z = f"min(zoom+{zoom_rate},{ZOOM_MAX})"
    else:
        z = f"if(eq(on,0),{ZOOM_MAX},max(zoom-{zoom_rate},1.0))"
    px1, py1 = _pan_targets(px, py, index, pan_margin=pan_margin)
    denom = max(1, frames - 1)
    pan_x = f"({px:.6f}+({px1:.6f}-{px:.6f})*on/{denom})"
    pan_y = f"({py:.6f}+({py1:.6f}-{py:.6f})*on/{denom})"
    x = f"max(0,min(iw-iw/zoom,{pan_x}*iw-(iw/zoom/2)))"
    y = f"max(0,min(ih-ih/zoom,{pan_y}*ih-(ih/zoom/2)))"
    return z, x, y


_WORD_RE = re.compile(r"[a-z']+")

# Coarse tone classification (Professional Quality Roadmap Tier 3 #11) — whole-word
# matching against each beat's own narration text, not substring matching, so e.g. "war"
# doesn't false-positive on "warm"/"warrior"/"reward". Deliberately a short, high-
# precision list per mood rather than an exhaustive one: a false "documentary" (the
# default/no-signal case) is a safe miss, a wrong mood swap is not.
_MOOD_KEYWORDS: dict[str, set[str]] = {
    "tense": {
        "war", "wars", "warfare", "battle", "battles", "attack", "attacked", "attacks",
        "execution", "executed", "betray", "betrayed", "betrayal", "danger", "dangerous",
        "murder", "murdered", "assassin", "assassinated", "assassination", "fear",
        "afraid", "escape", "escaped", "siege", "captured", "capture", "torture",
        "tortured", "threat", "threatened", "enemy", "enemies", "fight", "fought",
        "kill", "killed", "blood", "bloody", "conspiracy", "plot", "revolt", "uprising",
        "rebellion", "invasion", "invaded", "hunted", "trapped", "ambush",
    },
    "somber": {
        "death", "died", "dying", "dead", "grief", "loss", "lost", "tragedy", "tragic",
        "mourning", "mourned", "funeral", "extinct", "extinction", "disaster", "farewell",
        "buried", "grave", "sorrow", "wept", "weeping", "ashes", "ruins", "vanished",
        "forgotten", "lonely", "despair", "starvation", "starved", "plague", "famine",
        "collapse", "collapsed", "destroyed", "destruction",
    },
    "uplifting": {
        "triumph", "triumphant", "hope", "hopeful", "joy", "joyful", "discover",
        "discovered", "discovery", "celebrate", "celebrated", "celebration", "victory",
        "victorious", "inspire", "inspired", "inspiring", "breakthrough", "achieve",
        "achieved", "achievement", "wonder", "wondrous", "miracle", "love", "loved",
        "reunite", "reunited", "rescue", "rescued", "saved", "freedom", "liberated",
        "liberation", "healed", "recovered", "hero", "heroic", "proud", "pride",
    },
}


def _classify_mood(beats: list[dict] | None) -> str:
    """Picks a mood bucket from the beats' own narration text — falls back to
    "documentary" (the original, always-present bucket) when nothing scores, which
    covers both a genuinely neutral story and any mood whose directory doesn't exist
    yet (see _music_tracks' own directory-exists fallback for the latter case too)."""
    if not beats:
        return "documentary"
    words = _WORD_RE.findall(" ".join(b.get("text", "") for b in beats).lower())
    if not words:
        return "documentary"
    scores = {mood: sum(1 for w in words if w in kws) for mood, kws in _MOOD_KEYWORDS.items()}
    best_mood, best_score = max(scores.items(), key=lambda kv: kv[1])
    return best_mood if best_score > 0 else "documentary"


def _music_tracks(mood: str | None = None) -> list[Path]:
    if not MUSIC_DIR.is_dir():
        return []
    if mood:
        mood_dir = MUSIC_DIR / mood
        if mood_dir.is_dir():
            tracks = [p for p in mood_dir.rglob("*.mp3") if p.is_file()]
            if tracks:
                return tracks
    return [p for p in MUSIC_DIR.rglob("*.mp3") if p.is_file()]


def _pick_music(beats: list[dict] | None = None) -> Path | None:
    """Track from the mood bucket classified from the beats' own text (see
    _classify_mood) when one matches and has tracks; otherwise any track under
    pipeline/assets/music/ (see documentary/SOURCE.md and the per-mood SOURCE.md files
    for licensing — all CC0). Falls back to the flat pool rather than returning None so
    an unclassified/neutral story still gets a music bed."""
    tracks = _music_tracks(_classify_mood(beats))
    return random.choice(tracks) if tracks else None


def music_available() -> bool:
    """Whether a music bed will be mixed in at all — for timeline.py to record without
    reaching into the private track-picking helper above just to check a boolean."""
    return bool(_music_tracks())


@dataclass
class Timeline:
    """The declarative output of build_timeline() — every editorial decision already
    made (transitions, Ken Burns framing, motion-graphic overlays, sfx cues, music,
    loudness) expressed as ffmpeg inputs + filter-graph fragments, with no editorial
    judgment left for compile_ffmpeg() to make. See Claude outputs/
    FILM_PLAN_ARCHITECTURE.md Milestone 2 — before this split, the same code that
    decided *what* to render also built the ffmpeg command string deciding *how*, in
    the same loop, at the same time; this dataclass is the seam between the two that
    didn't exist before, and is what makes a later automated-QC pass (Milestone 7)
    able to inspect what render() actually decided instead of only pixels after the
    fact."""
    cmd_inputs: list[str]
    filter_parts: list[str]
    video_map: str
    audio_map: str


def build_timeline(
    audio_path: str, ass_path: str, beats: list[dict],
    font: dict | None = None, style: str = "photographic",
) -> Timeline:
    """Every editorial decision this pipeline makes about a video — transition style,
    Ken Burns framing, which motion graphic fires and when, sfx cue placement, music
    mood/mixing, final loudness — expressed as a Timeline, with zero ffmpeg-command
    assembly left to do afterward (see compile_ffmpeg()). This is exactly render()'s
    own pre-Milestone-2 body, moved here unchanged: see FILM_PLAN_ARCHITECTURE.md's
    Milestone 2 and its own byte-identical-output test
    (tests/test_render.py::test_build_timeline_plus_compile_ffmpeg_matches_pre_refactor_render)
    for why this split is trusted not to have changed behavior.

    `font` is an optional captions.py-style font dict (see captions.CAPTION_FONTS) —
    when given, the timeline-marker motion graphic is set in the same face as this
    video's own captions instead of always defaulting to Anton (see
    motion_graphics.font_path_for() and OPEN_ISSUES.md audit #33).

    `style`: "photographic" (default, unchanged behavior) or "illustrated" — in
    illustrated mode, a beat with no year-callout still gets a motion-graphic keyword
    card (see motion_graphics.beat_keyword_label) instead of nothing but the plain
    animated backdrop. See OPEN_ISSUES.md #59: a real production run showed 3 of 4
    beats in an illustrated video with no motion-graphic content at all, since
    extract_year_label's trigger is narrow by design and most beats don't name a year."""
    total_duration = get_audio_duration(audio_path)
    font_path = motion_graphics.font_path_for(font)
    beats = _cap_beats(beats, MAX_CLIPS)
    n = len(beats)

    transitions = [_transition_style(beats[i], beats[i + 1], i) for i in range(n - 1)]
    requested = []
    for i, beat in enumerate(beats):
        extra = (transitions[i - 1][0] / 2 if i > 0 else 0.0) + (transitions[i][0] / 2 if i < n - 1 else 0.0)
        requested.append(beat["duration"] + extra)

    # Each beat's absolute start time in the final concatenated output, and each
    # transition's *effective* (possibly short-first-beat-clamped) duration — computed
    # once here so the xfade chain below and the sfx cue collection (both need the same
    # numbers) can't drift apart into two independently-maintained copies of this math.
    beat_start = [0.0] * n
    effective_t = [0.0] * (n - 1)
    _acc = requested[0]
    for i in range(1, n):
        t, _ = transitions[i - 1]
        offset = _acc - t
        if offset < 0:
            t = max(0.0, _acc)
            offset = 0.0
        beat_start[i] = offset
        effective_t[i - 1] = t
        _acc += requested[i] - t

    # Sound-design accent cues (see #18/GENERATION.md) — absolute seconds in the final
    # output where a soft whoosh should fire. Collected below, sparingly: only on an
    # accent transition or a motion-graphic reveal, never on every cut.
    sfx_cues: list[float] = []

    cmd = ["ffmpeg", "-y"]
    for i, beat in enumerate(beats):
        path = beat["path"]
        if path.lower().endswith(VIDEO_EXTS):
            cmd += ["-stream_loop", "-1", "-t", f"{requested[i]:.3f}", "-i", path]
        else:
            cmd += ["-loop", "1", "-t", f"{requested[i]:.3f}", "-i", path]
    audio_input_index = n
    cmd += ["-i", audio_path]

    music_path = _pick_music(beats)
    music_input_index = None
    if music_path is not None:
        music_input_index = n + 1
        cmd += ["-stream_loop", "-1", "-i", str(music_path)]

    # [i:v:0], not [i:v]: some downloaded stock clips ship as a "stream group" with more
    # than one video stream bundled in the container (an HDR/enhancement-layer variant, in
    # one observed crash) — automatic stream selection ([i:v]) can pick ambiguously inside
    # a multi-input filter_complex and crash ffmpeg outright. Pinning stream 0 explicitly
    # avoids that regardless of how any given source file is muxed.
    filter_parts = []
    labels = [f"v{i}" for i in range(n)]
    for i, beat in enumerate(beats):
        path = beat["path"]
        if path.lower().endswith(VIDEO_EXTS):
            filter_parts.append(
                f"[{i}:v:0]{CLIP_NORMALIZE},"
                f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[v{i}]"
            )
        else:
            face = beat.get("face")
            px, py = (face[0], face[1]) if face else (0.5, 0.5)
            frames = max(1, round(requested[i] * FPS))
            framing = beat.get("framing")
            z, x, y = _zoompan_expr(
                px, py, zoom_in=_resolve_zoom_in(framing, i), index=i, frames=frames, framing=framing,
            )
            # CLIP_NORMALIZE (and SKIN_TONE_CORRECTION, when it applies) run BEFORE
            # scale=8000 (not after, where CLIP_NORMALIZE was first wired), and that
            # ordering is load-bearing, not cosmetic: applying either on the post-upscale
            # ~8000x14222px intermediate frame (the source's native resolution upscaled
            # 8000px wide before zoompan crops back down) made a single ~2s clip balloon
            # to 6.5GB+ RSS and effectively hang — confirmed by isolated testing (memory
            # stayed flat applying it pre-upscale on the small source image instead,
            # identical visual result). Not documented behavior anyone would guess; found
            # by watching real memory usage during a render that was mysteriously
            # getting SIGKILLed, not by reading the filter docs.
            correction = CLIP_NORMALIZE
            if beat.get("entity_type") == "person":
                correction = f"{CLIP_NORMALIZE},{SKIN_TONE_CORRECTION}"
            filter_parts.append(
                f"[{i}:v:0]{correction},scale=8000:-1,"
                f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
                f"format=yuv420p[v{i}]"
            )

        # A beat whose narration names a specific year gets an animated timeline-marker
        # graphic over its first ~2s — see motion_graphics.py for why this is a distinct
        # feature from the pan/zoom/transition treatment above, not more of the same.
        # In illustrated mode specifically, a beat with no year still gets SOME
        # motion-graphic content — its own visual_query as a smaller keyword card —
        # instead of nothing but the plain animated backdrop (see #59: a real production
        # run showed 3 of 4 beats with no motion graphic at all, since most beats don't
        # name a year). Photographic mode is unaffected: it relies on real imagery, not
        # a graphic, for beats without a year.
        year_label = motion_graphics.extract_year_label(beat.get("text", ""))
        overlay_label = year_label
        overlay_fontsize = motion_graphics.FONT_SIZE
        if not overlay_label and style == "illustrated":
            overlay_label = motion_graphics.beat_keyword_label(beat)
            overlay_fontsize = motion_graphics.ILLUSTRATED_FONT_SIZE
        if overlay_label:
            overlay = motion_graphics.timeline_overlay_filter(
                overlay_label, requested[i], f"v{i}", f"v{i}o",
                font_path=font_path, fontsize=overlay_fontsize,
            )
            if overlay:
                filter_parts.append(overlay)
                labels[i] = f"v{i}o"
                # Sparing on purpose (see #18): only a genuine year reveal gets the
                # whoosh accent. Illustrated mode's keyword card fires on nearly every
                # beat, and a whoosh on every single beat would violate "never on every
                # cut" — the whole reason the sfx cue collection exists to be selective.
                if year_label:
                    sfx_cues.append(beat_start[i] + 0.1)

    prev_label = labels[0]
    for i in range(1, n):
        _, transition_name = transitions[i - 1]
        t = effective_t[i - 1]
        offset = beat_start[i]
        out_label = f"x{i}"
        filter_parts.append(
            f"[{prev_label}][{labels[i]}]xfade=transition={transition_name}:duration={t:.3f}:offset={offset:.3f}[{out_label}]"
        )
        prev_label = out_label
        if transition_name in _ACCENT_TRANSITIONS:
            sfx_cues.append(offset + t / 2)

    # Fixed documentary-style grade + subtle vignette + film grain — applied once, after
    # the cut/crossfade chain and before captions burn in, so captions stay crisp on top
    # of the treated footage rather than being grained/vignetted themselves.
    filter_parts.append(
        f"[{prev_label}]eq=contrast=1.08:saturation=0.92:brightness=0.01,"
        f"vignette=PI/5,noise=alls=8:allf=t+u[graded]"
    )
    filter_parts.append(f"[graded]subtitles={ass_path}[vout]")

    # Sound-design accent (see #18/GENERATION.md) — added as one more ffmpeg input only
    # if there's actually at least one cue and the asset exists, matching music's own
    # graceful-degradation convention. Sits after the beat clips + narration + optional
    # music inputs already appended to `cmd` above, so its index is whatever the next
    # free slot is.
    sfx_input_index = None
    if sfx_cues and WHOOSH_PATH.is_file():
        sfx_input_index = n + 1 + (1 if music_input_index is not None else 0)
        cmd += ["-i", str(WHOOSH_PATH)]

    # Every real audio source (narration always; music/sfx only if present) is mixed
    # together in one amix rather than nested two-input mixes, so any combination of
    # "music only" / "sfx only" / "both" / "neither" is just a longer or shorter branch
    # list, not a different code path.
    audio_branches = [f"[{audio_input_index}:a]"]

    if music_input_index is not None:
        # Mirror the fade-out with a fade-in — without this, music hit its full ducked
        # volume the instant the filter chain started, an audible hard cut on entry that
        # contradicted the "no audible hard cut in or out" bar (Dana Okafor's persona)
        # despite the *presence* of ducking/fade-out having already been verified (#9).
        # Clamped to half the total duration so a very short video can't make the two
        # fades overlap into something louder than either alone.
        fade_d = min(1.2, total_duration / 2) if total_duration > 0 else 0.0
        filter_parts.append(
            f"[{music_input_index}:a]volume={MUSIC_VOLUME},atrim=0:{total_duration:.3f},"
            f"asetpts=PTS-STARTPTS,afade=t=in:st=0:d={fade_d:.3f},"
            f"afade=t=out:st={max(0, total_duration - fade_d):.3f}:d={fade_d:.3f}[music]"
        )
        audio_branches.append("[music]")

    if sfx_input_index is not None:
        # adelay places each cue at its real absolute position in the final timeline;
        # `all=1` applies the one delay value to every channel regardless of whether the
        # source is mono or stereo. asplit is only needed once there's more than one cue
        # to delay independently from the same short source clip.
        cue_ms = [max(0, round(c * 1000)) for c in sfx_cues]
        if len(cue_ms) == 1:
            filter_parts.append(
                f"[{sfx_input_index}:a]adelay=delays={cue_ms[0]}:all=1,volume={SFX_VOLUME}[sfx0]"
            )
            audio_branches.append("[sfx0]")
        else:
            splits = "".join(f"[sfxsrc{k}]" for k in range(len(cue_ms)))
            filter_parts.append(f"[{sfx_input_index}:a]asplit={len(cue_ms)}{splits}")
            for k, ms in enumerate(cue_ms):
                filter_parts.append(
                    f"[sfxsrc{k}]adelay=delays={ms}:all=1,volume={SFX_VOLUME}[sfx{k}]"
                )
                audio_branches.append(f"[sfx{k}]")

    if len(audio_branches) > 1:
        # duration=first: the output is trimmed/held to the *first* branch's length,
        # which is always the narration branch (audio_branches[0]) regardless of how
        # many music/sfx branches follow — so total runtime is never accidentally
        # extended by a music track or shortened by a stray short sfx clip.
        joined = "".join(audio_branches)
        filter_parts.append(f"{joined}amix=inputs={len(audio_branches)}:duration=first:dropout_transition=2[aout]")
        audio_map = "[aout]"
    else:
        audio_map = audio_branches[0]  # already bracketed

    # Final loudness pass, after narration+music+sfx are already mixed — targets the
    # same ~-14 LUFS YouTube itself normalizes to, so a video isn't further re-adjusted
    # (and its dynamics squashed again) by the platform on top of whatever level we
    # produced. audio_map is already bracket-form either way at this point.
    loud_in = audio_map if audio_map.startswith("[") else f"[{audio_map}]"
    audio_map = "[loud]"
    filter_parts.append(f"{loud_in}{LOUDNORM}[loud]")

    return Timeline(cmd_inputs=cmd, filter_parts=filter_parts, video_map="[vout]", audio_map=audio_map)


def compile_ffmpeg(timeline: Timeline, out_path: str) -> list[str]:
    """Pure mechanical translation from a Timeline to a real ffmpeg command line — no
    editorial judgment happens here, only in build_timeline() above. Exactly what
    render()'s own tail end did before Milestone 2, just reading from a Timeline
    object instead of two loose local variables (`cmd`/`filter_parts`) that only
    existed inside render()'s own stack frame."""
    filter_complex = ";".join(timeline.filter_parts)
    return timeline.cmd_inputs + [
        "-filter_complex", filter_complex,
        "-map", timeline.video_map, "-map", timeline.audio_map,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        out_path,
    ]


def render(
    audio_path: str, ass_path: str, out_path: str, beats: list[dict],
    font: dict | None = None, style: str = "photographic",
) -> None:
    """As of Milestone 2 (see FILM_PLAN_ARCHITECTURE.md), this is a thin wrapper:
    build_timeline() makes every editorial decision, compile_ffmpeg() mechanically
    translates the result into a real ffmpeg command, this function just runs it.
    Nothing about calling render() itself changed — same signature, same behavior,
    same output — this split only changes what's INSIDE it."""
    timeline = build_timeline(audio_path, ass_path, beats, font=font, style=style)
    cmd = compile_ffmpeg(timeline, out_path)
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    audio_path, ass_path, out_path, beats_json = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    render(audio_path, ass_path, out_path, json.loads(Path(beats_json).read_text()))
    print(out_path)
