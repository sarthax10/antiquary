#!/usr/bin/env python3
"""Transcribe narration to word-level timestamps (faster-whisper, free, local) and render
a styled .ass subtitle file: plain, sentence-case, modestly-sized captions with a soft
shadow and no box — the accessibility-caption look real streaming platforms use (Claude
outputs/OPEN_ISSUES.md #67), not the "TikTok/Reels" bouncing-karaoke-word style this
replaces. The user's own words, from early in this project: "THE SUBTITLES SHOULD BE
LIKE NETFLIX."

One of a few real, distinct sans-serif reading faces is picked per video (see
CAPTION_FONTS) — pipeline/assets/fonts/ ships the actual font files (OFL licensed, see
OFL.txt there) since the base ffmpeg image only has DejaVu, and asking for a font name
that isn't installed just silently falls back to it. Chunk boundaries are picked by an
estimated character budget per font, not a fixed word count — a fixed count overflows
the frame on longer words/fonts, which is the "subtitles get out of screen" bug this
avoids.

Usage: captions.py <input.mp3> <output.ass>
"""
import random
import sys
from pathlib import Path

from faster_whisper import WhisperModel

MODEL_SIZE = "small"
VIDEO_W, VIDEO_H = 1080, 1920
MARGIN_L = MARGIN_R = 60
USABLE_WIDTH = VIDEO_W - MARGIN_L - MARGIN_R
MAX_WORDS_PER_CHUNK = 10
WHITE = "&HFFFFFF&"

# avg_char_w is a conservative (slightly under-estimated, biased toward wrapping a
# little early rather than risking overflow) px-per-character at this font's own size —
# there's no real text-measurement available at this stage, just ffmpeg/libass output.
# Both are real, statically-shipped OFL sans-serif reading faces (not display/headline
# faces like the old Anton/Bebas Neue/Archivo Black, which stay in use for
# motion_graphics.py's bold on-screen graphics — a genuinely different typographic role
# from a plain running caption; see that module's own _FONT_FILES comment).
CAPTION_FONTS = [
    {"name": "Fira Sans Medium", "size": 58, "avg_char_w": 27},
    {"name": "PT Sans", "size": 60, "avg_char_w": 28},
]


def _ass_header(font: dict) -> str:
    # BorderStyle=1 (outline+shadow, not a box) with a thin outline and a soft shadow —
    # legible against any background without reading as a graphic element the way the
    # old style's heavy 4px outline did. No Bold: the font file's own weight (Medium/
    # Regular) is the whole point of picking real reading faces instead of display ones.
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {VIDEO_W}
PlayResY: {VIDEO_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font["name"]},{font["size"]},{WHITE},{WHITE},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1.4,2.6,2,{MARGIN_L},{MARGIN_R},460,1

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


def build_caption_track(words: list[dict], font: dict) -> list[dict]:
    """The same on-screen chunking build_ass() uses, shaped as timeline data instead of
    burned into an .ass file — the editor's caption track. Kept here (not re-derived
    elsewhere) so there's exactly one place chunk boundaries are decided.

    Each entry's "words" list preserves per-word timestamps (used for re-deriving exact
    chunk start/end on a re-render, see build_ass_from_track()) even though the burned-in
    style no longer animates word-by-word."""
    track = []
    for i, chunk in enumerate(_chunk_words(words, font)):
        track.append({
            "id": f"cap_{i:02d}",
            "text": " ".join(w["word"] for w in chunk),
            "start": round(chunk[0]["start"], 3),
            "end": round(chunk[-1]["end"], 3),
            "words": [{"word": w["word"], "start": round(w["start"], 3), "end": round(w["end"], 3)} for w in chunk],
        })
    return track


def font_by_name(name: str) -> dict | None:
    """Looks up a full font dict (size/avg_char_w/...) from just the name saved on
    Story.timeline["style"]["caption_font"] — used when re-rendering from a timeline,
    which only has the name, not the full CAPTION_FONTS entry."""
    return next((f for f in CAPTION_FONTS if f["name"] == name), None)


def _dialogue_lines(chunk: list[dict], font: dict) -> list[str]:
    """One plain Dialogue line for the whole chunk — sentence case as transcribed, no
    per-word color/scale animation. Shared by build_ass() (raw whisper words) and
    build_ass_from_track() (a timeline's stored caption track) so the two only ever
    produce identical output."""
    text = " ".join(_escape(w["word"]) for w in chunk)
    return [f"Dialogue: 0,{_ts(chunk[0]['start'])},{_ts(chunk[-1]['end'])},Caption,,0,0,0,,{text}\n"]


def build_ass(words: list[dict], out_path: str, font: dict | None = None) -> None:
    font = font or pick_font()
    lines = [_ass_header(font)]
    for chunk in _chunk_words(words, font):
        lines.extend(_dialogue_lines(chunk, font))
    Path(out_path).write_text("".join(lines), encoding="utf-8")


def build_ass_from_track(caption_track: list[dict], font: dict, out_path: str) -> None:
    """Re-renders the exact same .ass as build_ass(), but sourced from an editable
    timeline's caption track (build_caption_track's output) instead of raw whisper words —
    what render_timeline.py uses so a human's edit to a caption's text/timing actually
    changes the burned-in output on re-render. Falls back to a single-word "chunk" for any
    entry with no "words" (e.g. a caption a human editor adds with no per-word data)."""
    lines = [_ass_header(font)]
    for cap in caption_track:
        chunk = cap.get("words") or [{"word": cap["text"], "start": cap["start"], "end": cap["end"]}]
        lines.extend(_dialogue_lines(chunk, font))
    Path(out_path).write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    audio_path, out_path = sys.argv[1], sys.argv[2]
    build_ass(transcribe_words(audio_path), out_path)
    print(out_path)
