#!/usr/bin/env python3
"""Synthesize narration audio with edge-tts (free, no API key) — one clip per script
beat rather than one clip for the whole narration. This is what gives render.py an
*exact* duration for each beat's visual (from the real synthesized audio, not an
approximation), and lets rate/pitch vary by beat position and sentence punctuation
instead of one flat, uniform reading for the entire video.

One voice is picked per video from VOICE_POOL (a real mix of male/female, US/GB) rather
than always the same voice for every generation — see pick_voice().

Usage: tts.py "<narration text>" <output.mp3> [voice]   — single-clip form, kept for
manual testing; the real caller is run_pipeline.py via synthesize_beats()/concat_audio().
"""
import asyncio
import random
import subprocess
import sys
from pathlib import Path

import edge_tts

DEFAULT_VOICE = "en-US-ChristopherNeural"

# A real mix of male/female, US/GB neural voices — Multilingual and kids' voices
# (Ana, Maisie) deliberately excluded. One is picked per video (pick_voice), not per
# beat — switching voice mid-narration would sound broken, switching between videos is
# what actually delivers "not always the same voice."
VOICE_POOL = [
    "en-US-ChristopherNeural", "en-US-GuyNeural", "en-US-AndrewNeural",
    "en-US-EricNeural", "en-US-RogerNeural", "en-US-BrianNeural",
    "en-US-AriaNeural", "en-US-JennyNeural", "en-US-AvaNeural",
    "en-US-EmmaNeural", "en-US-MichelleNeural",
    "en-GB-RyanNeural", "en-GB-SoniaNeural", "en-GB-ThomasNeural",
]


def pick_voice(rng: random.Random | None = None) -> str:
    return (rng or random).choice(VOICE_POOL)


def _combine_rate(base: str, delta: int) -> str:
    n = int(base.rstrip("%")) + delta
    return f"{'+' if n >= 0 else ''}{n}%"


def _combine_pitch(base: str, delta: int) -> str:
    n = int(base.rstrip("Hz")) + delta
    return f"{'+' if n >= 0 else ''}{n}Hz"


def _prosody_for(text: str, index: int, total: int) -> tuple[str, str]:
    """Rate/pitch vary by beat position (hook punchier, closer more deliberate) and by
    sentence-ending punctuation (a question lifts in pitch, an exclamation reads faster
    and slightly higher) — real, if modest, expressive variation using the prosody
    controls edge-tts actually exposes. It does not support Azure's separate "styles"/
    express-as feature (cheerful, excited, ...) — that's part of the paid Speech SDK,
    not the free Read-Aloud voice endpoint this library wraps, so it isn't available
    here at any settings."""
    if total <= 1:
        rate, pitch = "+4%", "+0Hz"
    elif index == 0:
        rate, pitch = "+9%", "+8Hz"  # the hook: urgent, slightly raised
    elif index == total - 1:
        rate, pitch = "+0%", "-6Hz"  # the closer: deliberate, slightly lower
    else:
        rate, pitch = "+4%", "+0Hz"

    stripped = text.strip()
    if stripped.endswith("?"):
        pitch = _combine_pitch(pitch, 10)  # a question lifts near the end
    elif stripped.endswith("!"):
        rate = _combine_rate(rate, 5)
        pitch = _combine_pitch(pitch, 6)

    return rate, pitch


def _probe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    return round(float(out.stdout.strip()), 3)


async def synthesize(text: str, out_path: str, voice: str, rate: str = "+4%", pitch: str = "+0Hz") -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(out_path)


async def synthesize_beats(beats: list[dict], out_dir: Path, voice: str | None = None) -> list[dict]:
    """Returns each beat with "path" (its own audio clip) and "duration" (its real,
    probed length) added — the ground truth render.py uses for per-beat cut timing.
    Concatenate the paths in order (concat_audio) for the full narration track."""
    voice = voice or pick_voice()
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, beat in enumerate(beats):
        path = out_dir / f"beat_{i:02d}.mp3"
        rate, pitch = _prosody_for(beat["text"], i, len(beats))
        await synthesize(beat["text"], str(path), voice, rate=rate, pitch=pitch)
        results.append({**beat, "path": str(path), "duration": _probe_duration(str(path))})
    return results


def concat_audio(paths: list[str], out_path: str) -> None:
    """Joins per-beat clips into the single narration track faster-whisper transcribes.
    All clips come from the same edge-tts voice/codec, so a demuxer-level concat (no
    re-encode) is safe and fast."""
    list_path = Path(out_path).with_suffix(".txt")
    escaped = (str(Path(p).resolve()).replace("'", "'\\''") for p in paths)
    list_path.write_text("".join(f"file '{p}'\n" for p in escaped), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", out_path],
        check=True, capture_output=True,
    )
    list_path.unlink(missing_ok=True)


if __name__ == "__main__":
    text = sys.argv[1]
    out_path = sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_VOICE
    asyncio.run(synthesize(text, out_path, voice))
    print(out_path)
