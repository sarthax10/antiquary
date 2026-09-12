#!/usr/bin/env python3
"""FilmPlan — the versioned, structured intermediate representation between "what the
writer/director decided" and "what render.py executes" (Milestone 1 of Claude outputs/
FILM_PLAN_ARCHITECTURE.md). Extends the existing beat schema (text/visual_query/
entity_type/framing) rather than replacing it: every field already proven reliable
against a real local Ollama model this session (entity_type, framing) carries over
unchanged; new fields (purpose, shots, typography, ...) are additive, each defaulting
to today's exact effective behavior when absent.

Version "0" is today's ACTUAL real shape — confirmed against a real story pulled from
the database, not assumed — at two different points in the pipeline:
  - `Story.beats` (what's actually persisted, per pipeline/enqueue_story.py): just
    {text, visual_query, entity_type}. No framing, no shots, no purpose.
  - `run_pipeline.py`'s `beats_final` (what render.py's render() is actually called
    with): {path, entity_type, face, duration, text, visual_query, framing}.
`from_beats_v0()` lifts either shape up into a valid, single-shot-per-scene FilmPlan
(missing fields take real, documented defaults — never silently invented). `to_beats_v0()`
and `to_beats_final()` are the exact inverse projections, so anything still reading
either shape directly (the API response, the frontend, render.py itself) keeps working
completely unchanged regardless of which FilmPlan version actually produced a story.

This file changes nothing about how a video is actually generated or rendered yet — it
is the schema only, verified by round-tripping against real beats pulled from the real
database (see tests/test_film_plan.py), not synthesized examples.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field

FILM_PLAN_VERSION = "1.0"

# Closed vocabularies — validated the same defensive way entity_type/framing already
# are elsewhere in this pipeline (see generate_script.py): an invalid or missing value
# falls back to a documented default rather than reaching downstream code unvalidated.
VALID_SHOT_TYPES = (
    "establishing", "wide", "medium", "close_up", "extreme_close_up", "detail",
    "portrait", "environmental_portrait", "document", "map", "diagram", "aerial",
    "archival_footage", "texture", "graphic_composition",
)
VALID_PURPOSES = (
    "establish", "reveal", "contextualize", "humanize", "escalate", "resolve",
    "transition", "inform",
)
VALID_TRANSITIONS = ("cut", "dissolve", "match_cut", "accent")
VALID_TYPOGRAPHY_ROLES = (
    "narration_caption", "lower_third", "location_card", "date_card", "quote",
    "chapter_title",
)
VALID_MUSIC_CUES = ("hold", "shift", "swell", "silence")

DEFAULT_SHOT_TYPE = "medium"
DEFAULT_PURPOSE = "inform"
DEFAULT_TRANSITION = "cut"
DEFAULT_MUSIC_CUE = "hold"
DEFAULT_FRAMING = "hold_static"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class TypographyCue:
    role: str
    content: str
    attribution: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict | None) -> "TypographyCue | None":
        if not d:
            return None
        role = d.get("role", "narration_caption")
        if role not in VALID_TYPOGRAPHY_ROLES:
            role = "narration_caption"
        return TypographyCue(role=role, content=d.get("content", ""), attribution=d.get("attribution"))


@dataclass
class Shot:
    shot_id: str
    scene_id: str
    shot_type: str = DEFAULT_SHOT_TYPE
    visual_query: str = ""
    entity_type: str = "scene"
    source_preference: list[str] = field(default_factory=list)
    asset_id: str | None = None
    duration_share: float = 1.0
    framing: str = DEFAULT_FRAMING
    camera_motion: str | None = None
    crop: dict | None = None
    confidence: float = 1.0
    # Carried from today's render-ready beat shape (run_pipeline.py's beats_final) —
    # filled in once real sourcing/TTS actually run; absent on a freshly-written plan
    # that hasn't been sourced yet.
    path: str | None = None
    face: list[float] | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Shot":
        shot_type = d.get("shot_type", DEFAULT_SHOT_TYPE)
        if shot_type not in VALID_SHOT_TYPES:
            shot_type = DEFAULT_SHOT_TYPE
        return Shot(
            shot_id=d.get("shot_id") or _new_id("shot"),
            scene_id=d.get("scene_id", ""),
            shot_type=shot_type,
            visual_query=d.get("visual_query", ""),
            entity_type=d.get("entity_type", "scene"),
            source_preference=list(d.get("source_preference") or []),
            asset_id=d.get("asset_id"),
            duration_share=float(d.get("duration_share", 1.0)),
            framing=d.get("framing") or DEFAULT_FRAMING,
            camera_motion=d.get("camera_motion"),
            crop=d.get("crop"),
            confidence=float(d.get("confidence", 1.0)),
            path=d.get("path"),
            face=d.get("face"),
        )


@dataclass
class Scene:
    scene_id: str
    sentences: list[int] = field(default_factory=list)
    narration: str = ""
    purpose: str = DEFAULT_PURPOSE
    narrative_beat: str | None = None
    visual_strategy: str = "single_shot"
    shots: list[Shot] = field(default_factory=list)
    transition_in: str = DEFAULT_TRANSITION
    typography: TypographyCue | None = None
    sound_design: list[str] = field(default_factory=list)
    music_cue: str = DEFAULT_MUSIC_CUE
    confidence: float = 1.0
    locked: bool = False
    # v0-era field, carried for round-trip fidelity with run_pipeline.py's real
    # beats_final shape (the TTS-measured real duration of this beat's narration).
    duration: float | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["typography"] = self.typography.to_dict() if self.typography else None
        return d

    @staticmethod
    def from_dict(d: dict) -> "Scene":
        scene_id = d.get("scene_id") or _new_id("scene")
        shots = [Shot.from_dict({**s, "scene_id": s.get("scene_id", scene_id)}) for s in (d.get("shots") or [])]
        purpose = d.get("purpose", DEFAULT_PURPOSE)
        if purpose not in VALID_PURPOSES:
            purpose = DEFAULT_PURPOSE
        transition_in = d.get("transition_in", DEFAULT_TRANSITION)
        if transition_in not in VALID_TRANSITIONS:
            transition_in = DEFAULT_TRANSITION
        music_cue = d.get("music_cue", DEFAULT_MUSIC_CUE)
        if music_cue not in VALID_MUSIC_CUES:
            music_cue = DEFAULT_MUSIC_CUE
        return Scene(
            scene_id=scene_id,
            sentences=list(d.get("sentences") or []),
            narration=d.get("narration") or d.get("text", ""),
            purpose=purpose,
            narrative_beat=d.get("narrative_beat"),
            visual_strategy=d.get("visual_strategy", "single_shot"),
            shots=shots,
            transition_in=transition_in,
            typography=TypographyCue.from_dict(d.get("typography")),
            sound_design=list(d.get("sound_design") or []),
            music_cue=music_cue,
            confidence=float(d.get("confidence", 1.0)),
            locked=bool(d.get("locked", False)),
            duration=d.get("duration"),
        )

    @property
    def primary_shot(self) -> Shot | None:
        """The single shot most v0-era code should look at — the first one, or None
        for a (shouldn't happen, but handled) scene with no shots at all. Every
        FilmPlan produced by from_beats_v0() has exactly one shot per scene, so this
        is always today's actual (only) shot for anything not yet multi-shot-aware."""
        return self.shots[0] if self.shots else None


@dataclass
class FilmPlan:
    version: str = FILM_PLAN_VERSION
    title: str = ""
    subject: str = ""
    scenes: list[Scene] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "title": self.title,
            "subject": self.subject,
            "scenes": [s.to_dict() for s in self.scenes],
        }

    @staticmethod
    def from_dict(d: dict) -> "FilmPlan":
        return FilmPlan(
            version=d.get("version", FILM_PLAN_VERSION),
            title=d.get("title", ""),
            subject=d.get("subject", ""),
            scenes=[Scene.from_dict(s) for s in (d.get("scenes") or [])],
        )


def from_beats_v0(beats: list[dict], title: str = "") -> FilmPlan:
    """Lifts today's real beat shape — anywhere from the 3 fields Story.beats actually
    persists ({text, visual_query, entity_type}) up to the 7 fields run_pipeline.py's
    beats_final actually carries ({..., framing, duration, path, face}) — into a valid,
    single-shot-per-scene FilmPlan. Every beat becomes exactly one Scene with exactly
    one Shot. Missing fields take the same real defaults their own modules already use
    (DEFAULT_FRAMING matches render.py's own fallback for an absent/unrecognized
    framing value) — nothing invented, nothing silently different from what render()
    would have done with the same beat today."""
    scenes = []
    for i, beat in enumerate(beats):
        scene_id = f"scene_{i:02d}"
        shot = Shot(
            shot_id=f"{scene_id}_shot_00",
            scene_id=scene_id,
            visual_query=beat.get("visual_query", ""),
            entity_type=beat.get("entity_type", "scene"),
            framing=beat.get("framing") or DEFAULT_FRAMING,
            duration_share=1.0,
            path=beat.get("path"),
            face=beat.get("face"),
        )
        scenes.append(Scene(
            scene_id=scene_id,
            narration=beat.get("text", ""),
            shots=[shot],
            duration=beat.get("duration"),
        ))
    return FilmPlan(version="0", title=title, scenes=scenes)


def to_beats_v0(plan: FilmPlan) -> list[dict]:
    """The exact inverse of from_beats_v0() for Story.beats' real 3-field persisted
    shape — flattens ANY FilmPlan (v0 or a richer future version) back down to
    {text, visual_query, entity_type}, so anything still reading Story.beats directly
    (the API response, the frontend) keeps working unchanged regardless of which
    FilmPlan version actually produced the story. A multi-shot scene collapses to its
    primary_shot."""
    out = []
    for scene in plan.scenes:
        shot = scene.primary_shot
        out.append({
            "text": scene.narration,
            "visual_query": shot.visual_query if shot else "",
            "entity_type": shot.entity_type if shot else "scene",
        })
    return out


def to_beats_final(plan: FilmPlan) -> list[dict]:
    """The richer inverse projection matching run_pipeline.py's actual beats_final
    shape — what render.py's render() is really called with today. A multi-shot scene
    still collapses to its primary_shot for this projection; render.py doesn't
    understand multi-shot scenes yet (a later milestone's job, not this one's) — this
    function is what lets a FilmPlan-based pipeline call today's completely unchanged
    render() function during the transition, rather than needing render() rewritten
    before a FilmPlan can be used for anything at all."""
    out = []
    for scene in plan.scenes:
        shot = scene.primary_shot
        out.append({
            "path": shot.path if shot else None,
            "entity_type": shot.entity_type if shot else "scene",
            "face": shot.face if shot else None,
            "duration": scene.duration,
            "text": scene.narration,
            "visual_query": shot.visual_query if shot else "",
            "framing": shot.framing if shot else DEFAULT_FRAMING,
        })
    return out
