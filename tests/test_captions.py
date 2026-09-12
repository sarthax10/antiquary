"""Tests for pipeline/captions.py's Netflix-style caption rendering (Claude outputs/
OPEN_ISSUES.md #67) — replaces the old per-word karaoke pop-in/color-highlight style
with plain, sentence-case, single-line-per-chunk captions. These tests exist to pin down
exactly what changed: one real Dialogue line per on-screen chunk (not one per word), no
color/scale animation tags in the output, and text left in its original case.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import captions  # noqa: E402


def _words(*specs):
    return [{"word": w, "start": s, "end": e} for w, s, e in specs]


def test_dialogue_lines_produces_exactly_one_line_per_chunk():
    chunk = _words(("The", 0.0, 0.3), ("secret", 0.3, 0.8), ("letter", 0.8, 1.3))
    lines = captions._dialogue_lines(chunk, captions.CAPTION_FONTS[0])
    assert len(lines) == 1
    assert lines[0].count("Dialogue:") == 1


def test_dialogue_lines_spans_the_full_chunk_start_to_end():
    chunk = _words(("The", 0.0, 0.3), ("secret", 0.3, 0.8), ("letter", 0.8, 1.3))
    lines = captions._dialogue_lines(chunk, captions.CAPTION_FONTS[0])
    assert captions._ts(0.0) in lines[0]
    assert captions._ts(1.3) in lines[0]


def test_dialogue_lines_has_no_per_word_color_or_scale_animation():
    # The old karaoke style used \c (color override) and \t/\fscx (pop-in scale
    # animation) tags per active word -- confirms that's genuinely gone, not just
    # unused.
    chunk = _words(("The", 0.0, 0.3), ("year", 0.3, 0.8), ("1815", 0.8, 1.3))
    lines = captions._dialogue_lines(chunk, captions.CAPTION_FONTS[0])
    assert "\\c" not in lines[0]
    assert "\\t(" not in lines[0]
    assert "\\fscx" not in lines[0]


def test_dialogue_lines_preserves_sentence_case():
    chunk = _words(("The", 0.0, 0.3), ("Radium", 0.3, 0.8), ("Girls", 0.8, 1.3))
    lines = captions._dialogue_lines(chunk, captions.CAPTION_FONTS[0])
    assert "The Radium Girls" in lines[0]
    assert "THE RADIUM GIRLS" not in lines[0]


def test_build_ass_produces_one_dialogue_per_chunk(tmp_path):
    words = _words(
        ("In", 0.0, 0.1), ("the", 0.1, 0.2), ("1920s,", 0.2, 0.6), ("hundreds", 0.6, 1.0),
        ("of", 1.0, 1.1), ("women", 1.1, 1.5), ("worked", 1.5, 1.9), ("at", 1.9, 2.0),
        ("factories", 2.0, 2.6), ("painting", 2.6, 3.1), ("watch", 3.1, 3.4), ("faces.", 3.4, 3.9),
    )
    out_path = tmp_path / "out.ass"
    captions.build_ass(words, str(out_path), font=captions.CAPTION_FONTS[0])
    content = out_path.read_text(encoding="utf-8")
    chunks = captions._chunk_words(words, captions.CAPTION_FONTS[0])
    assert content.count("Dialogue:") == len(chunks)
    assert content.count("Dialogue:") > 1  # confirms this sentence actually needed >1 chunk


def test_ass_header_has_no_forced_bold_and_a_thin_outline():
    header = captions._ass_header(captions.CAPTION_FONTS[0])
    style_line = next(line for line in header.splitlines() if line.startswith("Style:"))
    fields = style_line.split(",")
    # Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour,
    # BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle,
    # BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
    bold = int(fields[7])
    border_style = int(fields[15])
    outline = float(fields[16])
    assert bold == 0
    assert border_style == 1  # outline+shadow, not a box (BorderStyle=3)
    assert outline < 2.0  # thin, not the old style's heavy 4px outline


def test_pick_font_only_returns_real_static_reading_faces():
    for _ in range(10):
        font = captions.pick_font()
        assert font["name"] in ("Fira Sans Medium", "PT Sans")
        assert "uppercase" not in font
