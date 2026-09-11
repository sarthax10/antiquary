#!/usr/bin/env python3
"""Generate a short history-story script via a local Ollama model, then run a
separate fact-check pass over its claims before returning it.

Usage: generate_script.py "<topic or leave blank for a free pick>"
Prints JSON: {"title", "hook", "narration", "on_screen_text",
              "fact_check": {"claims": [...], "overall_confidence"},
              "needs_human_review": bool}

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

WRITER_SYSTEM_PROMPT = """You write scripts for 30-45 second vertical history short-form videos \
(Instagram Reels / YouTube Shorts). Pick ONE narrow, specific, surprising true historical \
detail or story — not a generic "5 facts about X" list. Write for a viewer who will decide \
whether to keep watching within the first 2 seconds.

Return ONLY valid JSON with these keys:
- "title": short internal title (not shown on screen)
- "hook": the first spoken line, must create curiosity or tension immediately, max 15 words
- "narration": the full spoken script including the hook, 70-110 words, punchy, plain spoken \
English, no headers or bullet points, written to be read aloud in ~35-45 seconds
- "on_screen_text": a list of 4-8 short caption fragments (3-6 words each) pulled from the \
narration, in order, for on-screen text overlays
No commentary, no markdown, just the JSON object."""

VISUAL_QUERIES_SYSTEM_PROMPT = """You will be given the narration script for a short video. Break \
it into 4-6 short image/video search phrases (3-6 words each), IN NARRATION ORDER, each naming one \
concrete, specific, findable thing to show on screen while that part of the narration plays — a \
real person, place, artifact, painting, building, or event, specific enough to find an actual \
archival image, painting, or stock footage clip of it (e.g. "Augustus marble statue", "Roman forum \
ruins", "ancient Roman villa fresco" — not vague phrases like "ancient times" or "history concept").

Return ONLY valid JSON: {"visual_queries": ["...", "...", ...]}
No commentary, no markdown, just the JSON object."""

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


REQUIRED_SCRIPT_KEYS = {"title", "hook", "narration", "on_screen_text"}


def write_script(topic: str) -> dict:
    user_prompt = f"Topic seed: {topic}" if topic else "Pick any narrow, surprising true historical story."
    return _chat_json(OLLAMA_HOST, OLLAMA_MODEL, WRITER_SYSTEM_PROMPT, user_prompt)


def write_visual_queries(narration: str) -> list[str]:
    result = _chat_json(OLLAMA_HOST, OLLAMA_MODEL, VISUAL_QUERIES_SYSTEM_PROMPT, narration)
    queries = result.get("visual_queries")
    if not queries:
        raise ValueError("visual_queries output missing or empty")
    return queries


def fact_check(narration: str) -> dict:
    return _chat_json(OLLAMA_HOST, FACTCHECK_MODEL, FACTCHECK_SYSTEM_PROMPT, narration)


def generate(topic: str, max_attempts: int = 4, on_stage=None) -> dict:
    """A small local model occasionally: (a) returns JSON missing expected keys despite
    format="json" only guaranteeing valid JSON syntax, not our schema (more likely the
    larger/more the schema asks for in one call — so this is split into three focused
    calls: core script, then visual_queries derived from the finalized narration, then
    fact-check), or (b) writes content that deterministically fails Ollama's json-mode
    grammar on a later call (retrying the *same* content doesn't help — regenerating does,
    since that's content-dependent, not a transient network blip). So on any failure,
    regenerate the whole script from scratch rather than retry the same broken output.

    `on_stage`, if given, is called with "writing" before the writer/visual-queries calls
    and "fact_checking" before the fact-check call — real progress reporting for the UI,
    not a simulated timer. Optional so this module has no hard dependency on the caller."""
    last_error = None
    for attempt in range(max_attempts):
        try:
            if on_stage:
                on_stage("writing")
            script = write_script(topic)
            if not REQUIRED_SCRIPT_KEYS.issubset(script):
                raise ValueError(f"writer output missing keys: {REQUIRED_SCRIPT_KEYS - script.keys()}")
            script["visual_queries"] = write_visual_queries(script["narration"])
            if on_stage:
                on_stage("fact_checking")
            checked = fact_check(script["narration"])
        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
            last_error = e
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
