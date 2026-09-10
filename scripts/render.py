#!/usr/bin/env python3
"""Render the final vertical video: a crossfading slideshow/reel of the supplied media
clips, narration audio, and burned-in styled captions (.ass from captions.py).

Usage: render.py <narration.mp3> <captions.ass> <output.mp4> <clip1> [clip2] [clip3] ...

Each clip is either a real video (.mp4/.mov/.webm — cover-cropped to fill the frame, real
motion preserved) or a still image (.jpg/.png — Ken Burns pan applied). fetch_visuals.py
produces this mix automatically, real footage first. With one clip it's a single pan/clip
(no crossfade); with several, they crossfade in narration order.

Requires ffmpeg on PATH.
"""
import subprocess
import sys

WIDTH, HEIGHT = 1080, 1920
FPS = 30
ZOOM_RATE = 0.0008
XFADE_DURATION = 0.6  # seconds
MIN_CLIP_SECONDS = 4.0
MAX_CLIPS = 6
VIDEO_EXTS = (".mp4", ".mov", ".webm", ".m4v")


def get_audio_duration(audio_path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def render(audio_path: str, ass_path: str, out_path: str, media: list[str]) -> None:
    total_duration = get_audio_duration(audio_path)

    max_n = max(1, int(total_duration // MIN_CLIP_SECONDS))
    n = max(1, min(len(media), max_n, MAX_CLIPS))
    media = media[:n]

    if n == 1:
        clip_len = total_duration
    else:
        clip_len = (total_duration + (n - 1) * XFADE_DURATION) / n
    clip_frames = max(1, int(clip_len * FPS))

    cmd = ["ffmpeg", "-y"]
    for path in media:
        if path.lower().endswith(VIDEO_EXTS):
            cmd += ["-stream_loop", "-1", "-t", f"{clip_len:.3f}", "-i", path]
        else:
            cmd += ["-loop", "1", "-t", f"{clip_len:.3f}", "-i", path]
    cmd += ["-i", audio_path]

    filter_parts = []
    for i, path in enumerate(media):
        if path.lower().endswith(VIDEO_EXTS):
            filter_parts.append(
                f"[{i}:v]scale=-2:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[v{i}]"
            )
        else:
            filter_parts.append(
                f"[{i}:v]scale=8000:-1,"
                f"zoompan=z='min(zoom+{ZOOM_RATE},1.3)':d={clip_frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
                f"format=yuv420p[v{i}]"
            )

    prev_label = "v0"
    for i in range(1, n):
        offset = i * (clip_len - XFADE_DURATION)
        out_label = f"x{i}"
        filter_parts.append(
            f"[{prev_label}][v{i}]xfade=transition=fade:duration={XFADE_DURATION:.3f}:"
            f"offset={offset:.3f}[{out_label}]"
        )
        prev_label = out_label

    filter_parts.append(f"[{prev_label}]subtitles={ass_path}[vout]")
    filter_complex = ";".join(filter_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", f"{n}:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        out_path,
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    audio_path, ass_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    media = sys.argv[4:]
    render(audio_path, ass_path, out_path, media)
    print(out_path)
