#!/usr/bin/env python3
"""Transcribe narration to word-level timestamps (faster-whisper, free, local) and render
a styled .ass subtitle file: short on-screen chunks with the currently-spoken word
highlighted (gold normally, a hotter orange for numbers/superlatives — a real semantic
emphasis, not just "whichever word is playing") — the standard "TikTok/Reels caption"
look, not a plain sentence-at-a-time subtitle track.

One of a few real, distinct display fonts is picked per video (see CAPTION_FONTS) rather
than always the same face — pipeline/assets/fonts/ ships the actual font files (OFL
licensed, see OFL.txt there) since the base ffmpeg image only has DejaVu, and asking for
a font name that isn't installed just silently falls back to it. Chunk boundaries are
picked by an estimated character budget per font, not a fixed word count — a fixed count
overflows the frame on longer words/fonts, which is the "subtitles get out of screen" bug
this replaces.

Usage: captions.py <input.mp3> <output.ass>
"""
import random
import re
import sys
from pathlib import Path

from faster_whisper import WhisperModel

MODEL_SIZE = "small"
VIDEO_W, VIDEO_H = 1080, 1920
MARGIN_L = MARGIN_R = 60
USABLE_WIDTH = VIDEO_W - MARGIN_L - MARGIN_R
MAX_WORDS_PER_CHUNK = 6
ACCENT_COLOR = "&H00D7FF&"  # ASS is BGR: this is gold (#FFD700)
EMPHASIS_COLOR = "&H00285AFF&"  # a hotter orange (#FF5A28), for numbers/superlatives
WHITE = "&HFFFFFF&"

# avg_char_w is a conservative (slightly under-estimated, biased toward wrapping a
# little early rather than risking overflow) px-per-character at this font's own size —
# there's no real text-measurement available at this stage, just ffmpeg/libass output.
CAPTION_FONTS = [
    {"name": "Anton", "size": 80, "uppercase": True, "avg_char_w": 44},
    {"name": "Bebas Neue", "size": 86, "uppercase": True, "avg_char_w": 38},
    {"name": "Archivo Black", "size": 70, "uppercase": False, "avg_char_w": 46},
    {"name": "DejaVu Sans", "size": 74, "bold": True, "uppercase": False, "avg_char_w": 45},
]


def _ass_header(font: dict) -> str:
    bold = 1  # every option here is a bold/black display weight
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {VIDEO_W}
PlayResY: {VIDEO_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font["name"]},{font["size"]},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,{bold},0,0,0,100,100,0,0,1,4,2,2,{MARGIN_L},{MARGIN_R},460,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


# Numbers, or a short list of words that tend to carry the "surprising" weight of a
# history-short sentence — a cheap, deterministic stand-in for real emphasis detection
# that's good enough to make captions feel directed rather than uniformly flat.
_EMPHASIS_RE = re.compile(
    r"\d|^(first|only|secret|never|forgotten|lost|hidden|vanished|discovered|impossible|"
    r"true|real|actual|no\W*one|nobody|everyone|everything|last|final)$",
    re.IGNORECASE,
)


def _is_emphasis(word: str) -> bool:
    return bool(_EMPHASIS_RE.search(word.strip(".,!?;:\"'‘’“”")))


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


def pick_font(rng: random.Random | None = None) -> dict:
    return (rng or random).choice(CAPTION_FONTS)


def _chunk_words(words: list[dict], font: dict) -> list[list[dict]]:
    """Groups words for one on-screen caption line, bounded by an estimated character
    budget for this font/size (not a fixed word count) so a chunk of longer words wraps
    to fewer of them instead of running past the frame edge."""
    max_chars = max(8, USABLE_WIDTH // font["avg_char_w"])
    chunks, current, current_len = [], [], 0
    for w in words:
        word_len = len(w["word"])
        added_len = word_len + (1 if current else 0)  # +1 for the joining space
        if current and (current_len + added_len > max_chars or len(current) >= MAX_WORDS_PER_CHUNK):
            chunks.append(current)
            current, current_len = [w], word_len
        else:
            current.append(w)
            current_len += added_len
    if current:
        chunks.append(current)
    return chunks


def build_ass(words: list[dict], out_path: str, font: dict | None = None) -> None:
    font = font or pick_font()
    lines = [_ass_header(font)]

    for chunk in _chunk_words(words, font):
        for i, active in enumerate(chunk):
            parts = []
            for j, w in enumerate(chunk):
                text = _escape(w["word"])
                if font.get("uppercase"):
                    text = text.upper()
                if j == i:
                    color = EMPHASIS_COLOR if _is_emphasis(w["word"]) else ACCENT_COLOR
                    parts.append(f"{{\\c{color}}}{text}{{\\c{WHITE}}}")
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
