#!/usr/bin/env python3
"""Synthesize narration audio with edge-tts (free, no API key) — one clip per script
beat rather than one clip for the whole narration. This is what gives render.py an
*exact* duration for each beat's visual (from the real synthesized audio, not an
approximation), and lets rate vary slightly by beat position: the hook reads a touch
faster/punchier, the closing beat a touch slower for emphasis — real prosody variation
instead of one flat rate for every video regardless of content.

Usage: tts.py "<narration text>" <output.mp3> [voice]   — single-clip form, kept for
manual testing; the real caller is run_pipeline.py via synthesize_beats()/concat_audio().
"""
import asyncio
import subprocess
import sys
from pathlib import Path

import edge_tts

DEFAULT_VOICE = "en-US-ChristopherNeural"  # calm documentary-style male voice
# Other good options: en-US-AriaNeural (female), en-GB-RyanNeural (British male)


def _rate_for(index: int, total: int) -> str:
    if total <= 1:
        return "+4%"
    if index == 0:
        return "+8%"  # the hook: read with more urgency to sell the pattern-interrupt
    if index == total - 1:
        return "+1%"  # the closer: a touch slower reads as more deliberate/weighty
    return "+4%"


def _probe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    return round(float(out.stdout.strip()), 3)


async def synthesize(text: str, out_path: str, voice: str, rate: str = "+4%") -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(out_path)


async def synthesize_beats(beats: list[dict], out_dir: Path, voice: str = DEFAULT_VOICE) -> list[dict]:
    """Returns each beat with "path" (its own audio clip) and "duration" (its real,
    probed length) added — the ground truth render.py uses for per-beat cut timing.
    Concatenate the paths in order (concat_audio) for the full narration track."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, beat in enumerate(beats):
        path = out_dir / f"beat_{i:02d}.mp3"
        await synthesize(beat["text"], str(path), voice, rate=_rate_for(i, len(beats)))
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
