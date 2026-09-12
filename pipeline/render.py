#!/usr/bin/env python3
"""Render the final vertical video from per-beat visuals (see fetch_visuals.py/tts.py),
narration audio, and burned-in styled captions (.ass from captions.py).

Usage: render.py <narration.mp3> <captions.ass> <output.mp4> <beats.json>
  beats.json: a JSON list of {"path", "entity_type", "face": [fx,fy]|null, "duration"}

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
for variety (see `_zoompan_expr()`/`_pan_targets()`). A fixed color grade, subtle vignette
and film grain pass, plus an optional ducked music bed, are the last steps before captions
burn in.

Requires ffmpeg on PATH.
"""
import json
import random
import subprocess
import sys
from pathlib import Path

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

MUSIC_DIR = Path(__file__).resolve().parent / "assets" / "music"
MUSIC_VOLUME = 0.12


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
      - same subject continuing (same entity_type): a real crossfade duration, with a
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
    if at and at == bt:
        return XFADE_SMOOTH, ("smoothleft" if index % 2 == 0 else "smoothright")
    if bt == "person" and at in _PERSON_ACCENT_TYPES:
        return XFADE_SMOOTH, "circleopen"
    if at == "person" and bt in _PERSON_ACCENT_TYPES:
        return XFADE_SMOOTH, "radial"
    return XFADE_CUT, "fade"


def _pan_targets(px: float, py: float, index: int) -> tuple[float, float]:
    """End point of the Ken Burns pan, given its start point (the detected face center, or
    plain frame center) and the beat index. The drift direction cycles deterministically
    through the four diagonal quadrants every 4 beats (reusing the same index that drives
    zoom_in alternation for the horizontal component, and a slower-flipping vertical
    component) so consecutive beats don't all pan the same way, while staying reproducible
    for testing/debugging rather than randomized."""
    dx = PAN_MARGIN if index % 2 == 0 else -PAN_MARGIN
    dy = (PAN_MARGIN * 0.6) if (index // 2) % 2 == 0 else -(PAN_MARGIN * 0.6)
    return min(0.95, max(0.05, px + dx)), min(0.95, max(0.05, py + dy))


def _zoompan_expr(px: float, py: float, zoom_in: bool, index: int, frames: int) -> tuple[str, str, str]:
    """Ken Burns z/x/y expressions that zoom toward/away from the fractional point (px,
    py) — defaults to dead-center (0.5, 0.5) for a plain image, or the beat's detected face
    center when fetch_visuals.py found one — the same as before, PLUS a genuine pan: the
    crop center drifts linearly from (px, py) to a second point (`_pan_targets`) over the
    clip's duration, using ffmpeg's own output-frame-count variable `on` against the known
    total frame count so the drift is exactly in sync with the clip, no separate clock
    needed. x/y stay clamped with the same min/max approach as before so the animated,
    moving target can never pull the crop window outside the source frame at any frame."""
    if zoom_in:
        z = f"min(zoom+{ZOOM_RATE},{ZOOM_MAX})"
    else:
        z = f"if(eq(on,0),{ZOOM_MAX},max(zoom-{ZOOM_RATE},1.0))"
    px1, py1 = _pan_targets(px, py, index)
    denom = max(1, frames - 1)
    pan_x = f"({px:.6f}+({px1:.6f}-{px:.6f})*on/{denom})"
    pan_y = f"({py:.6f}+({py1:.6f}-{py:.6f})*on/{denom})"
    x = f"max(0,min(iw-iw/zoom,{pan_x}*iw-(iw/zoom/2)))"
    y = f"max(0,min(ih-ih/zoom,{pan_y}*ih-(ih/zoom/2)))"
    return z, x, y


def _music_tracks() -> list[Path]:
    if not MUSIC_DIR.is_dir():
        return []
    return [p for p in MUSIC_DIR.rglob("*.mp3") if p.is_file()]


def _pick_music() -> Path | None:
    """Random track under pipeline/assets/music/ (see documentary/SOURCE.md for
    licensing — all CC0). A single flat mood pool for now; picking by topic/tone is a
    natural follow-up once there's more than a handful of tracks to choose between."""
    tracks = _music_tracks()
    return random.choice(tracks) if tracks else None


def music_available() -> bool:
    """Whether a music bed will be mixed in at all — for timeline.py to record without
    reaching into the private track-picking helper above just to check a boolean."""
    return bool(_music_tracks())


def render(audio_path: str, ass_path: str, out_path: str, beats: list[dict]) -> None:
    total_duration = get_audio_duration(audio_path)
    beats = _cap_beats(beats, MAX_CLIPS)
    n = len(beats)

    transitions = [_transition_style(beats[i], beats[i + 1], i) for i in range(n - 1)]
    requested = []
    for i, beat in enumerate(beats):
        extra = (transitions[i - 1][0] / 2 if i > 0 else 0.0) + (transitions[i][0] / 2 if i < n - 1 else 0.0)
        requested.append(beat["duration"] + extra)

    cmd = ["ffmpeg", "-y"]
    for i, beat in enumerate(beats):
        path = beat["path"]
        if path.lower().endswith(VIDEO_EXTS):
            cmd += ["-stream_loop", "-1", "-t", f"{requested[i]:.3f}", "-i", path]
        else:
            cmd += ["-loop", "1", "-t", f"{requested[i]:.3f}", "-i", path]
    audio_input_index = n
    cmd += ["-i", audio_path]

    music_path = _pick_music()
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
    for i, beat in enumerate(beats):
        path = beat["path"]
        if path.lower().endswith(VIDEO_EXTS):
            filter_parts.append(
                f"[{i}:v:0]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[v{i}]"
            )
        else:
            face = beat.get("face")
            px, py = (face[0], face[1]) if face else (0.5, 0.5)
            frames = max(1, round(requested[i] * FPS))
            z, x, y = _zoompan_expr(px, py, zoom_in=(i % 2 == 0), index=i, frames=frames)
            filter_parts.append(
                f"[{i}:v:0]scale=8000:-1,"
                f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
                f"format=yuv420p[v{i}]"
            )

    prev_label = "v0"
    acc_duration = requested[0]
    for i in range(1, n):
        t, transition_name = transitions[i - 1]
        offset = acc_duration - t
        out_label = f"x{i}"
        filter_parts.append(
            f"[{prev_label}][v{i}]xfade=transition={transition_name}:duration={t:.3f}:offset={offset:.3f}[{out_label}]"
        )
        prev_label = out_label
        acc_duration += requested[i] - t

    # Fixed documentary-style grade + subtle vignette + film grain — applied once, after
    # the cut/crossfade chain and before captions burn in, so captions stay crisp on top
    # of the treated footage rather than being grained/vignetted themselves.
    filter_parts.append(
        f"[{prev_label}]eq=contrast=1.08:saturation=0.92:brightness=0.01,"
        f"vignette=PI/5,noise=alls=8:allf=t+u[graded]"
    )
    filter_parts.append(f"[graded]subtitles={ass_path}[vout]")

    audio_map = f"{audio_input_index}:a"  # a bare stream reference, no filter_complex label
    if music_input_index is not None:
        filter_parts.append(
            f"[{music_input_index}:a]volume={MUSIC_VOLUME},atrim=0:{total_duration:.3f},"
            f"asetpts=PTS-STARTPTS,afade=t=out:st={max(0, total_duration - 1.2):.3f}:d=1.2[music]"
        )
        filter_parts.append(f"[{audio_input_index}:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]")
        audio_map = "[aout]"  # now a filter_complex output label, needs brackets

    filter_complex = ";".join(filter_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", audio_map,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        out_path,
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    audio_path, ass_path, out_path, beats_json = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    render(audio_path, ass_path, out_path, json.loads(Path(beats_json).read_text()))
    print(out_path)
