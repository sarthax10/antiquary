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


def test_fallback_query_trims_to_a_whole_word_not_mid_word():
    """Real bug caught during a creative-quality review (Claude outputs/OPEN_ISSUES.md
    #23): the old text[:60] hard slice regularly cut a word in half, and — combined with
    the fallback firing whenever the model fails beat-grouping validation — produced
    badly generic/truncated search queries that sourced visibly wrong stock footage."""
    text = "Initially, the stone was seen as just a curiosity, but with the deciphering"
    query = gs._fallback_query(text, max_len=55)
    assert text.startswith(query)
    assert len(query) <= 55
    assert not query.endswith("decip")  # the exact mid-word cut this fixes
    # the character right after the query in the original text is a space (or the
    # string ended) — confirms the cut landed on a real word boundary
    assert text[len(query):len(query) + 1] in (" ", "")


def test_fallback_query_short_text_is_unchanged():
    assert gs._fallback_query("A short sentence.", max_len=55) == "A short sentence."


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


def test_chunk_words_respects_character_budget():
    import captions

    font = {"name": "Test", "size": 80, "uppercase": False, "avg_char_w": 40}
    words = [{"word": w, "start": i, "end": i + 1} for i, w in enumerate(
        ["An", "extraordinarily", "long", "word", "sequence", "here", "today"]
    )]
    max_chars = captions.USABLE_WIDTH // font["avg_char_w"]
    for chunk in captions._chunk_words(words, font):
        line = " ".join(w["word"] for w in chunk)
        assert len(line) <= max_chars or len(chunk) == 1  # a single overlong word is allowed through


def test_chunk_words_covers_every_word_in_order():
    import captions

    font = captions.CAPTION_FONTS[0]
    words = [{"word": w, "start": i, "end": i + 1} for i, w in enumerate(
        ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    )]
    chunks = captions._chunk_words(words, font)
    flat = [w for chunk in chunks for w in chunk]
    assert flat == words
    assert all(len(c) <= captions.MAX_WORDS_PER_CHUNK for c in chunks)
