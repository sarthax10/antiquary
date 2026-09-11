"""Pure-function tests for the sentence/beat-grouping math in generate_script.py — no
DB, no network, no Ollama. This is the logic the whole beat-based visual-sourcing/render
system depends on being exactly right: a wrong grouping either loses narration content or
desyncs a beat's visual from the sentence it's meant to illustrate."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import generate_script as gs  # noqa: E402


def test_split_sentences_basic():
    narration = "First sentence here. Second one follows! Is this a question? Yes it is."
    sentences = gs.split_sentences(narration)
    assert sentences == [
        "First sentence here.",
        "Second one follows!",
        "Is this a question?",
        "Yes it is.",
    ]


def test_split_sentences_reconstructs_exactly():
    narration = "In 1901, a clerk found a letter. It changed everything. Nobody believed him."
    sentences = gs.split_sentences(narration)
    assert " ".join(sentences) == narration


def test_split_sentences_empty():
    assert gs.split_sentences("") == []
    assert gs.split_sentences("   ") == []


def test_split_sentences_no_terminal_punctuation_is_one_sentence():
    assert gs.split_sentences("just a fragment with no ending") == ["just a fragment with no ending"]


def test_validate_beat_groups_accepts_contiguous_full_coverage():
    raw = [{"sentences": [1, 2]}, {"sentences": [3]}, {"sentences": [4, 5]}]
    assert gs._validate_beat_groups(raw, 5) == [[0, 1], [2], [3, 4]]


def test_validate_beat_groups_rejects_gap():
    raw = [{"sentences": [1, 2]}, {"sentences": [4, 5]}]  # skips sentence 3
    assert gs._validate_beat_groups(raw, 5) is None


def test_validate_beat_groups_rejects_out_of_order():
    raw = [{"sentences": [3]}, {"sentences": [1, 2]}]
    assert gs._validate_beat_groups(raw, 3) is None


def test_validate_beat_groups_rejects_incomplete_coverage():
    raw = [{"sentences": [1, 2]}]  # only covers 2 of 5
    assert gs._validate_beat_groups(raw, 5) is None


def test_validate_beat_groups_rejects_malformed_entries():
    assert gs._validate_beat_groups([{"sentences": []}], 3) is None
    assert gs._validate_beat_groups([{"nope": [1]}], 1) is None
    assert gs._validate_beat_groups("not a list", 1) is None


def test_even_groups_covers_every_sentence_in_order():
    for n in range(1, 12):
        groups = gs._even_groups(n)
        flat = [i for group in groups for i in group]
        assert flat == list(range(n))


def test_even_groups_never_exceeds_target_beats():
    assert len(gs._even_groups(20, target_beats=5)) == 5
    assert len(gs._even_groups(2, target_beats=5)) == 2  # can't exceed sentence count


def test_write_beats_fallback_reconstructs_narration(monkeypatch):
    """When the model's grouping never validates, the fallback must still cover every
    sentence — never silently drop narration content."""
    def _bad_chat_json(*a, **k):
        return {"beats": [{"sentences": [1, 3], "visual_query": "x", "entity_type": "scene"}]}

    monkeypatch.setattr(gs, "_chat_json", _bad_chat_json)
    sentences = ["One.", "Two.", "Three.", "Four."]
    beats = gs.write_beats(sentences, max_attempts=1)
    assert " ".join(b["text"] for b in beats) == " ".join(sentences)
    assert all(b["entity_type"] == "scene" for b in beats)


def test_write_beats_accepts_valid_model_output(monkeypatch):
    def _good_chat_json(*a, **k):
        return {
            "beats": [
                {"sentences": [1], "visual_query": "a portrait", "entity_type": "person"},
                {"sentences": [2, 3], "visual_query": "a place", "entity_type": "place"},
                {"sentences": [4], "visual_query": "an artifact", "entity_type": "artifact"},
            ]
        }

    monkeypatch.setattr(gs, "_chat_json", _good_chat_json)
    sentences = ["One.", "Two.", "Three.", "Four."]
    beats = gs.write_beats(sentences, max_attempts=1)
    assert [b["entity_type"] for b in beats] == ["person", "place", "artifact"]
    assert beats[1]["text"] == "Two. Three."


def test_wrap_title_stays_within_line_budget():
    import captions

    text = "A Very Long Historical Title About Something Surprising That Happened"
    result = captions._wrap_title(text, max_chars=22)
    for line in result.split("\\N"):
        assert len(line) <= 22 or " " not in line  # a single overlong word is allowed through


def test_wrap_title_reconstructs_words():
    import captions

    text = "Short Title Here"
    result = captions._wrap_title(text, max_chars=22)
    assert result.replace("\\N", " ") == text
