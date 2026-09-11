#!/usr/bin/env python3
"""Render the final vertical video from per-beat visuals (see fetch_visuals.py/tts.py),
narration audio, and burned-in styled captions (.ass from captions.py, including its own
title card).

Usage: render.py <narration.mp3> <captions.ass> <output.mp4> <beats.json>
  beats.json: a JSON list of {"path", "entity_type", "face": [fx,fy]|null, "duration"}

Each beat's own visual plays for exactly its own real narration duration (from tts.py's
per-beat synthesis) — not a flat division of total runtime — so a cut lands where the
sentence it illustrates actually does. Consecutive beats about the same kind of subject
(same entity_type) crossfade smoothly into each other; a change of subject cuts hard,
which reads as more deliberate/edited than one uniform transition throughout. Still
images get a Ken Burns pan/zoom framed around the beat's detected face when there is one
(fetch_visuals.py's OpenCV pass) instead of blindly cropping to center — and alternate
zoom-in/zoom-out across beats for variety. A fixed color grade, subtle vignette and film
grain pass, plus an optional ducked music bed, are the last steps before captions burn in.

Requires ffmpeg on PATH.
"""
import json
import subprocess
import sys
from pathlib import Path

WIDTH, HEIGHT = 1080, 1920
FPS = 30
ZOOM_RATE = 0.0008
ZOOM_MAX = 1.3
XFADE_CUT = 0.08  # a change of subject: near-instant, reads as a hard cut
XFADE_SMOOTH = 0.45  # same subject continuing: an actual crossfade
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


def _transition_duration(a: dict, b: dict) -> float:
    same_subject = a.get("entity_type") and a.get("entity_type") == b.get("entity_type")
    return XFADE_SMOOTH if same_subject else XFADE_CUT


def _zoompan_expr(px: float, py: float, zoom_in: bool) -> tuple[str, str, str]:
    """Ken Burns z/x/y expressions that zoom toward (or away from) the fractional point
    (px, py) — defaults to dead-center (0.5, 0.5) for a plain image, or the beat's
    detected face center when fetch_visuals.py found one. x/y are clamped with min/max so
    an off-center target can never pull the crop window outside the source frame."""
    if zoom_in:
        z = f"min(zoom+{ZOOM_RATE},{ZOOM_MAX})"
    else:
        z = f"if(eq(on,0),{ZOOM_MAX},max(zoom-{ZOOM_RATE},1.0))"
    x = f"max(0,min(iw-iw/zoom,{px}*iw-(iw/zoom/2)))"
    y = f"max(0,min(ih-ih/zoom,{py}*ih-(ih/zoom/2)))"
    return z, x, y


def _pick_music() -> Path | None:
    """First track found under pipeline/assets/music/ (alphabetical, deterministic — no
    files shipped in the repo, see CLAUDE.md/docs for where to source CC0 tracks). A
    single flat pool for now; picking by topic/tone is a natural follow-up once there's
    more than a handful of tracks to choose between."""
    if not MUSIC_DIR.is_dir():
        return None
    tracks = sorted(p for p in MUSIC_DIR.rglob("*.mp3") if p.is_file())
    return tracks[0] if tracks else None


def render(audio_path: str, ass_path: str, out_path: str, beats: list[dict]) -> None:
    total_duration = get_audio_duration(audio_path)
    beats = _cap_beats(beats, MAX_CLIPS)
    n = len(beats)

    transitions = [_transition_duration(beats[i], beats[i + 1]) for i in range(n - 1)]
    requested = []
    for i, beat in enumerate(beats):
        extra = (transitions[i - 1] / 2 if i > 0 else 0.0) + (transitions[i] / 2 if i < n - 1 else 0.0)
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
            z, x, y = _zoompan_expr(px, py, zoom_in=(i % 2 == 0))
            frames = max(1, round(requested[i] * FPS))
            filter_parts.append(
                f"[{i}:v:0]scale=8000:-1,"
                f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
                f"format=yuv420p[v{i}]"
            )

    prev_label = "v0"
    acc_duration = requested[0]
    for i in range(1, n):
        t = transitions[i - 1]
        offset = acc_duration - t
        out_label = f"x{i}"
        filter_parts.append(
            f"[{prev_label}][v{i}]xfade=transition=fade:duration={t:.3f}:offset={offset:.3f}[{out_label}]"
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
