#!/usr/bin/env python3
"""Synthesize narration audio with edge-tts (free, no API key).

Usage: tts.py "<narration text>" <output.mp3> [voice]
"""
import asyncio
import sys
import edge_tts

DEFAULT_VOICE = "en-US-ChristopherNeural"  # calm documentary-style male voice
# Other good options: en-US-AriaNeural (female), en-GB-RyanNeural (British male)


async def synthesize(text: str, out_path: str, voice: str) -> None:
    communicate = edge_tts.Communicate(text, voice, rate="+4%")
    await communicate.save(out_path)


if __name__ == "__main__":
    text = sys.argv[1]
    out_path = sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_VOICE
    asyncio.run(synthesize(text, out_path, voice))
    print(out_path)
