#!/usr/bin/env python3
"""Builds the editable "timeline" saved on Story.timeline — see app/models/story.py's
column comment and docs/ARCHITECTURE.md. This is the future video editor's foundation:
one addressable, structured representation of what the auto-generate pipeline already
produces, instead of three separate ad-hoc outputs (beats, audio clips, an .ass file)
that only render.py knows how to combine.

Nothing renders from this yet — render.py still consumes beats/audio/captions directly,
byte-for-byte the same as before this module existed. Building it is purely additive.

Deliberately carries no asset URLs: individual beat visual/audio clips only exist as
local temp files during a run (media/tmp/<run_id>/...) and aren't durably uploaded
anywhere per-clip today (only the final rendered video is, to MinIO) — that's real,
separate follow-up work for whenever the editor actually needs to re-fetch/re-render an
individual clip, not something to fake a path for now.
"""
VIDEO_EXTS = (".mp4", ".mov", ".webm", ".m4v")


def build_timeline(
    beats: list[dict],
    assets: list[dict],
    beat_audio: list[dict],
    caption_track: list[dict],
    font: dict,
    voice: str,
    music_volume: float | None,
) -> dict:
    visual_track = []
    narration_track = []
    t = 0.0
    for i, (beat, asset, audio) in enumerate(zip(beats, assets, beat_audio)):
        duration = audio["duration"]
        kind = "video" if asset["path"].lower().endswith(VIDEO_EXTS) else "image"
        visual_track.append({
            "id": f"clip_{i:02d}",
            "kind": kind,
            "start": round(t, 3),
            "duration": round(duration, 3),
            "entity_type": asset["entity_type"],
            "visual_query": beat["visual_query"],
            "face": asset["face"],
            "source": asset["source"],
        })
        narration_track.append({
            "id": f"beat_{i:02d}",
            "start": round(t, 3),
            "duration": round(duration, 3),
            "text": beat["text"],
        })
        t += duration

    return {
        "version": 1,
        "duration": round(t, 3),
        "tracks": {
            "visual": visual_track,
            "narration": narration_track,
            "captions": caption_track,
            "music": {"volume": music_volume} if music_volume is not None else None,
        },
        "style": {
            "caption_font": font["name"],
            "caption_uppercase": bool(font.get("uppercase")),
            "voice": voice,
        },
    }
