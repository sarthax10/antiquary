#!/usr/bin/env python3
"""Transcribe narration to word-level timestamps (faster-whisper, free, local) and render
a styled .ass subtitle file: short on-screen chunks with the currently-spoken word
highlighted in an accent color — the standard "TikTok/Reels caption" look, not a plain
sentence-at-a-time subtitle track.

Usage: captions.py <input.mp3> <output.ass>
"""
import sys
from pathlib import Path

from faster_whisper import WhisperModel

MODEL_SIZE = "small"
VIDEO_W, VIDEO_H = 1080, 1920
CHUNK_SIZE = 4  # words shown on screen at once
ACCENT_COLOR = "&H00D7FF&"  # ASS is BGR: this is gold (#FFD700)
WHITE = "&HFFFFFF&"

ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {VIDEO_W}
PlayResY: {VIDEO_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Noto Sans Black,78,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,4,2,2,60,60,460,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(seconds: float) -> str:
    cs = int(round((seconds - int(seconds)) * 100))
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape(word: str) -> str:
    return word.replace("{", "(").replace("}", ")")


def transcribe_words(audio_path: str) -> list[dict]:
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, word_timestamps=True)
    words = []
    for seg in segments:
        for w in seg.words:
            words.append({"word": w.word.strip(), "start": w.start, "end": w.end})
    return words


def build_ass(words: list[dict], out_path: str) -> None:
    lines = [ASS_HEADER]
    for chunk_start in range(0, len(words), CHUNK_SIZE):
        chunk = words[chunk_start:chunk_start + CHUNK_SIZE]
        for i, active in enumerate(chunk):
            parts = []
            for j, w in enumerate(chunk):
                text = _escape(w["word"])
                if j == i:
                    parts.append(f"{{\\c{ACCENT_COLOR}}}{text}{{\\c{WHITE}}}")
                else:
                    parts.append(text)
            line_text = " ".join(parts)
            lines.append(
                f"Dialogue: 0,{_ts(active['start'])},{_ts(active['end'])},Caption,,0,0,0,,{line_text}\n"
            )
    Path(out_path).write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    audio_path, out_path = sys.argv[1], sys.argv[2]
    build_ass(transcribe_words(audio_path), out_path)
    print(out_path)
