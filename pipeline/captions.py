#!/usr/bin/env python3
"""Transcribe narration to word-level timestamps (faster-whisper, free, local) and render
a styled .ass subtitle file: short on-screen chunks with the currently-spoken word
highlighted (gold normally, a hotter orange for numbers/superlatives — a real semantic
emphasis, not just "whichever word is playing") — the standard "TikTok/Reels caption"
look, not a plain sentence-at-a-time subtitle track. Also burns in a title card for the
first ~2.2s using the script's on-screen title, positioned at the top so it doesn't
collide with the running captions at the bottom — the "pattern interrupt" research says
matters most for retention in the first couple of seconds.

Usage: captions.py <input.mp3> <output.ass> ["<title>"]
"""
import re
import sys
from pathlib import Path

from faster_whisper import WhisperModel

MODEL_SIZE = "small"
VIDEO_W, VIDEO_H = 1080, 1920
CHUNK_SIZE = 4  # words shown on screen at once
ACCENT_COLOR = "&H00D7FF&"  # ASS is BGR: this is gold (#FFD700)
EMPHASIS_COLOR = "&H00285AFF&"  # a hotter orange (#FF5A28), for numbers/superlatives
WHITE = "&HFFFFFF&"
TITLE_CARD_SECONDS = 2.2

ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {VIDEO_W}
PlayResY: {VIDEO_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Noto Sans Black,78,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,4,2,2,60,60,460,1
Style: Title,Noto Sans Black,72,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,5,3,8,70,70,150,1

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


TITLE_MAX_CHARS_PER_LINE = 22  # WrapStyle:2 (below) means ASS won't auto-wrap — this does


def _wrap_title(text: str, max_chars: int = TITLE_MAX_CHARS_PER_LINE) -> str:
    words = text.split()
    lines, current = [], ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = w
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\\N".join(lines)


def _title_dialogue(title: str) -> str:
    text = _wrap_title(_escape(title.strip()))
    return f"Dialogue: 1,{_ts(0)},{_ts(TITLE_CARD_SECONDS)},Title,,0,0,0,,{{\\fad(300,400)}}{text}\n"


def build_ass(words: list[dict], out_path: str, title: str | None = None) -> None:
    lines = [ASS_HEADER]
    if title:
        lines.append(_title_dialogue(title))

    for chunk_start in range(0, len(words), CHUNK_SIZE):
        chunk = words[chunk_start:chunk_start + CHUNK_SIZE]
        for i, active in enumerate(chunk):
            parts = []
            for j, w in enumerate(chunk):
                text = _escape(w["word"])
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
    title = sys.argv[3] if len(sys.argv) > 3 else None
    build_ass(transcribe_words(audio_path), out_path, title=title)
    print(out_path)
