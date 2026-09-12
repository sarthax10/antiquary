#!/usr/bin/env python3
"""Generate a short history-story script via a local Ollama model, then run a
separate fact-check pass over its claims before returning it.

Usage: generate_script.py "<topic or leave blank for a free pick>"
Prints JSON: {"title", "hook", "narration",
              "beats": [{"text", "visual_query", "entity_type"}, ...],
              "fact_check": {"claims": [...], "overall_confidence"},
              "needs_human_review": bool}

"beats" is the narration split into ordered visual segments — each beat's "text" is an
exact, contiguous slice of "narration" (concatenating every beat's text in order
reconstructs it exactly), paired with a search query and an entity_type
("person"/"place"/"artifact"/"event"/"scene") that downstream visual sourcing
(fetch_visuals.py) and render timing (render.py, via tts.py's per-beat clip durations)
both key off. Getting the LLM to name specific people/places/events per beat
rather than one flat per-video keyword list is what lets sourcing fetch an actual named
person's portrait instead of a generic stock photo, and what lets the renderer cut to a
new image on the actual sentence it's relevant to instead of a fixed fraction of the
total runtime.

IMPORTANT: this fact-check is a second LLM pass, not a search against real
sources. It catches some internal inconsistencies and claims the model itself
is unsure about, but a small local model can still confidently confirm its own
hallucinations. Treat "needs_human_review": false as "nothing obviously wrong
flagged itself", not as "verified true" — the human approval step stays
mandatory regardless of this flag until you've validated the fact-checker's
track record.
"""
import json
import os
import re
import sys
import time
import requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
# Point this at a stronger/different model than OLLAMA_MODEL if you have one —
# checking a claim with a different model than the one that wrote it is more
# likely to catch a hallucination than asking the same model to grade itself.
# `or` (not `.get(..., default)`) so an empty-but-present OLLAMA_FACTCHECK_MODEL — e.g. from
# sourcing .env's commented-out-by-value template line — falls back correctly instead of
# silently sending model="" to Ollama (which 400s with "model is required").
FACTCHECK_MODEL = os.environ.get("OLLAMA_FACTCHECK_MODEL") or OLLAMA_MODEL

ENTITY_TYPES = ("person", "place", "artifact", "event", "scene")

WRITER_SYSTEM_PROMPT = """You write scripts for 30-45 second vertical history short-form videos \
(Instagram Reels / YouTube Shorts). Pick ONE narrow, specific, surprising true historical \
detail or story — not a generic "5 facts about X" list. Write for a viewer who will decide \
whether to keep watching within the first 2 seconds — both platforms' algorithms weight early \
retention above almost everything else, so the opening line has to work as a genuine \
pattern-interrupt, not a slow windup.

Return ONLY valid JSON with these keys:
- "title": a punchy, scroll-stopping title using a proven pattern — a curiosity gap \
("The King Who Vanished From His Own Portrait"), a contrarian claim ("Everything You Know About \
the Boston Tea Party Is Wrong"), or a number-plus-surprising-detail ("The Ship That Sailed Itself \
for Nine Days"). Under 70 characters. This is shown in the app (story cards, the review desk) — \
not burned into the video itself — so it should read as a complete, sensible phrase on its own,
not a clickbait fragment.
- "hook": the first spoken line, a genuine pattern-interrupt — an emotional trigger, a direct \
question, or a contrarian claim that forces the viewer to keep watching to resolve it. Max 15 \
words.
- "narration": the full spoken script including the hook, 70-110 words, punchy, plain spoken \
English, written in complete sentences (this gets split into sentences programmatically \
afterward, so normal sentence-ending punctuation matters), no headers or bullet points, written \
to be read aloud in ~35-45 seconds
No commentary, no markdown, just the JSON object."""

BEATS_SYSTEM_PROMPT = """You will be given a video narration script, split into numbered \
sentences. Group the sentences into visual "beats" that together cover every sentence exactly \
once, in order. A single beat covering the ENTIRE narration is WRONG even if the topic doesn't \
change — a viewer needs to see something different on screen every few seconds, not one static \
image for the whole video. Use AT LEAST 3 beats, ideally 4-6, even for a short, single-topic \
narration: split by sentence if nothing else changes, not by subject. Never skip a sentence or \
put them out of order.

For each beat, name one concrete, specific, findable thing to show on screen while that beat \
plays, and return:
- "sentences": the sentence numbers in this beat, consecutive and in increasing order (e.g. [1,2])
- "visual_query": a 3-6 word image/video search phrase for this beat — a real person, place, \
artifact, painting, building, or event, specific enough to find an actual photo, portrait, \
painting, or stock footage clip of it (e.g. "Augustus marble statue", "Roman forum ruins" — \
never vague phrases like "ancient times" or "history concept")
- "entity_type": one of "person", "place", "artifact", "event", "scene" — use "person" ONLY when \
the visual_query names a specific real individual whose actual likeness/portrait should be \
shown, not a generic or anonymous figure

Example, for a 6-sentence narration all about the same person: \
{"beats": [{"sentences": [1], "visual_query": "Marie Curie portrait", "entity_type": "person"}, \
{"sentences": [2,3], "visual_query": "Curie laboratory Paris", "entity_type": "place"}, \
{"sentences": [4], "visual_query": "radium glowing vial", "entity_type": "artifact"}, \
{"sentences": [5,6], "visual_query": "Nobel Prize ceremony 1903", "entity_type": "event"}]} \
— four beats, one static subject, still four different things shown on screen.

Return ONLY valid JSON: {"beats": [{"sentences": [...], "visual_query": "...", "entity_type": "..."}, ...]}
Every sentence number from 1 up to the last one must appear in exactly one beat, covering all of \
them in increasing order across beats. No commentary, no markdown, just the JSON object."""

FACTCHECK_SYSTEM_PROMPT = """You are a skeptical historical fact-checker. You will be given a \
narration script for a short video. You did not write it and have no reason to defend it.

Break it into its discrete factual claims (names, relationships, dates, causes, quotes, "firsts", \
numbers). For each claim, give your honest best judgment of whether it is accurate.

Return ONLY valid JSON with these keys:
- "claims": a list of objects, each with:
  - "claim": the specific factual assertion, quoted or closely paraphrased from the script
  - "verdict": one of "verified" (you're confident it's correct), "uncertain" (plausible but you \
can't confirm it, or it's a common misconception), "false" (you're confident it's wrong)
  - "note": one short sentence explaining the verdict, and the correction if verdict is "false"
- "overall_confidence": "high" only if every claim is "verified", "medium" if all claims are \
"verified" or "uncertain" with no "false", "low" if any claim is "false"
No commentary, no markdown, just the JSON object."""


def _chat_json(host: str, model: str, system_prompt: str, user_prompt: str, max_retries: int = 3) -> dict:
    """Local Ollama calls occasionally 400 (the model emits output that fails its own
    format="json" schema check server-side) or hit a transient connection error under
    CPU load — both are worth a retry rather than failing the whole pipeline run."""
    last_error = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                f"{host}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "format": "json",
                },
                timeout=240,
            )
            resp.raise_for_status()
            return json.loads(resp.json()["message"]["content"])
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
    raise last_error


REQUIRED_SCRIPT_KEYS = {"title", "hook", "narration"}

# Splits on sentence-ending punctuation followed by whitespace and a capital letter/quote —
# good enough for short, plainly-punctuated narration prose without pulling in a full NLP
# dependency. Falls back to treating the whole narration as one sentence if this matches nothing.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"‘“])")


def split_sentences(narration: str) -> list[str]:
    text = (narration or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_RE.split(text) if p.strip()]
    return parts or [text]


def _validate_beat_groups(raw_beats, n_sentences: int) -> list[list[int]] | None:
    """Returns 0-based sentence-index groups if raw_beats' "sentences" lists are
    contiguous, ordered, and cover every sentence exactly once — otherwise None."""
    groups = []
    covered = 0
    for b in raw_beats:
        nums = b.get("sentences") if isinstance(b, dict) else None
        if not isinstance(nums, list) or not nums:
            return None
        # The model has been observed returning JSON-string numbers (["1","2"]) or floats
        # ([1.0, 2.0]) instead of ints — `n - 1` on a string raises an uncaught TypeError
        # that kills the whole generation (no retry), and a float slips past this check
        # silently (0.0 == 0) only to blow up later on float indexing. Reject both here so
        # a model quirk falls through to the same retry/fallback path every other
        # validation failure already uses, instead of crashing generate() outright.
        if not all(isinstance(n, int) and not isinstance(n, bool) for n in nums):
            return None
        idx = [n - 1 for n in nums]
        if idx != list(range(covered, covered + len(idx))):
            return None
        groups.append(idx)
        covered += len(idx)
    return groups if covered == n_sentences else None


def _even_groups(n_sentences: int, target_beats: int = 5) -> list[list[int]]:
    n_beats = max(1, min(target_beats, n_sentences))
    base, extra = divmod(n_sentences, n_beats)
    groups, start = [], 0
    for i in range(n_beats):
        size = base + (1 if i < extra else 0)
        groups.append(list(range(start, start + size)))
        start += size
    return groups


def _fallback_query(text: str, max_len: int = 55) -> str:
    """Used only when the model didn't supply a real visual_query for a beat (either a
    per-beat miss, or the whole-script deterministic fallback below) — a real search
    phrase beats a truncated sentence fragment, but even this fallback shouldn't cut a
    word in half (a query search engines see less of, and a genuinely worse-looking
    truncation if it ever surfaces in a UI). Trims to the last complete word within the
    budget instead of a hard character slice."""
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    return truncated.rsplit(" ", 1)[0] if " " in truncated else truncated


def _beats_from_groups(sentences: list[str], groups: list[list[int]], raw_beats: list[dict]) -> list[dict] | None:
    beats = []
    for group, meta in zip(groups, raw_beats):
        text = " ".join(sentences[i] for i in group)
        query = (meta.get("visual_query") or "").strip()
        entity_type = meta.get("entity_type") if meta.get("entity_type") in ENTITY_TYPES else "scene"
        beats.append({"text": text, "visual_query": query or _fallback_query(text), "entity_type": entity_type})
    return beats if all(b["visual_query"] for b in beats) else None


def write_beats(sentences: list[str], max_attempts: int = 3) -> list[dict]:
    """Groups the (already Python-split, exact) sentences into visual beats. Never
    trusts the LLM to reproduce narration text — only to partition sentence *numbers*,
    which is validated. The model demonstrably can do this correctly but isn't
    consistent about it, so a bad attempt (wrong beat count, non-contiguous ranges) is
    worth a couple of fresh retries before giving up to the deterministic even-split
    fallback, which loses per-beat entity_type/query quality (no more "person" detection
    for that beat, just its own truncated sentence text as a generic search query)."""
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sentences))
    min_beats = min(3, len(sentences))

    for _ in range(max_attempts):
        try:
            result = _chat_json(OLLAMA_HOST, OLLAMA_MODEL, BEATS_SYSTEM_PROMPT, numbered)
        except (requests.exceptions.RequestException, json.JSONDecodeError):
            continue
        raw_beats = result.get("beats") or []
        groups = _validate_beat_groups(raw_beats, len(sentences))
        # A grouping that's merely *structurally* valid (contiguous, ordered, full
        # coverage) can still be a single beat spanning the whole narration if the model
        # ignores the "4-6 beats" instruction — technically valid, but exactly the
        # one-image-for-the-whole-video problem this beat system exists to fix.
        if groups is not None and len(groups) >= min_beats:
            beats = _beats_from_groups(sentences, groups, raw_beats)
            if beats is not None:
                return beats

    # Silent until now: this path means the model failed beat-grouping validation on
    # every attempt, so every beat loses real entity_type detection AND gets a truncated
    # sentence fragment as its visual search query instead of a real one — exactly the
    # "generic AI video" quality regression the beats system exists to prevent, just
    # reintroduced via this fallback. Caught by manually inspecting a generation's
    # timeline during a creative-quality review (see Claude outputs/QUALITY_BAR.md) with
    # no log trail explaining why the sourcing looked generic. Printed here so it shows
    # up in job_manager's captured generation log — a real fix (better prompt, more
    # retries, a repair pass) needs to know how often this actually fires first.
    print(
        f"[generate_script] beat-grouping fallback: model failed validation on all "
        f"{max_attempts} attempts, falling back to flat even-split with generic scene "
        f"queries — sourcing quality for this generation will be degraded",
        file=sys.stderr,
    )
    return [
        {
            "text": (text := " ".join(sentences[i] for i in group)),
            "visual_query": _fallback_query(text),
            "entity_type": "scene",
        }
        for group in _even_groups(len(sentences))
    ]


def write_script(topic: str) -> dict:
    user_prompt = f"Topic seed: {topic}" if topic else "Pick any narrow, surprising true historical story."
    return _chat_json(OLLAMA_HOST, OLLAMA_MODEL, WRITER_SYSTEM_PROMPT, user_prompt)


def fact_check(narration: str) -> dict:
    return _chat_json(OLLAMA_HOST, FACTCHECK_MODEL, FACTCHECK_SYSTEM_PROMPT, narration)


def generate(topic: str, max_attempts: int = 4, on_stage=None) -> dict:
    """A small local model occasionally: (a) returns JSON missing expected keys despite
    format="json" only guaranteeing valid JSON syntax, not our schema (more likely the
    larger/more the schema asks for in one call — so this is split into three focused
    calls: core script, then beats derived from the finalized narration, then
    fact-check), or (b) writes content that deterministically fails Ollama's json-mode
    grammar on a later call (retrying the *same* content doesn't help — regenerating does,
    since that's content-dependent, not a transient network blip). So on any failure,
    regenerate the whole script from scratch rather than retry the same broken output.

    `on_stage`, if given, is called with "writing" before the writer/beats calls and
    "fact_checking" before the fact-check call — real progress reporting for the UI, not
    a simulated timer. Optional so this module has no hard dependency on the caller."""
    last_error = None
    for attempt in range(max_attempts):
        try:
            if on_stage:
                on_stage("writing")
            script = write_script(topic)
            if not REQUIRED_SCRIPT_KEYS.issubset(script):
                raise ValueError(f"writer output missing keys: {REQUIRED_SCRIPT_KEYS - script.keys()}")
            sentences = split_sentences(script["narration"])
            script["beats"] = write_beats(sentences)
            if on_stage:
                on_stage("fact_checking")
            checked = fact_check(script["narration"])
        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
            last_error = e
            # Same bug class already fixed in write_beats(): every attempt-level failure
            # here was silently swallowed, with only a bare, stage-agnostic RuntimeError
            # once every attempt was exhausted — no way to tell which stage broke or why
            # without this. Printed so it lands in job_manager's captured generation log.
            print(
                f"[generate_script] generate() attempt {attempt + 1}/{max_attempts} failed: "
                f"{type(e).__name__}: {e}",
                file=sys.stderr,
            )
            continue

        claims = checked.get("claims", [])
        overall_confidence = checked.get("overall_confidence", "low")
        needs_human_review = overall_confidence != "high" or any(
            c.get("verdict") != "verified" for c in claims
        )
        script["fact_check"] = checked
        script["needs_human_review"] = needs_human_review
        return script
    raise RuntimeError(f"generate() failed after {max_attempts} attempts") from last_error


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else ""
    print(json.dumps(generate(topic), ensure_ascii=False, indent=2))
