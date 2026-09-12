#!/usr/bin/env python3
"""Builds the editable "timeline" saved on Story.timeline — see app/models/story.py's
column comment and docs/ARCHITECTURE.md. This is the future video editor's foundation:
one addressable, structured representation of what the auto-generate pipeline already
produces, instead of three separate ad-hoc outputs (beats, audio clips, an .ass file)
that only render.py knows how to combine.

The auto-generate pipeline (run_pipeline.py) still renders straight from beats/audio/
captions directly, byte-for-byte the same as before this module existed — building the
timeline here doesn't touch that path or its output. It's render_timeline.py that renders
*from* a timeline (durably-stored per-clip assets + the caption track's own text/timing),
which is what a future editor's "save + re-render" action will call once a human has
actually changed something on the timeline.

build_timeline() itself doesn't set each visual/narration entry's "object_key" — it can't,
since a clip's durable MinIO location is namespaced by the story's own id
(stories/<user_id>/<story_id>/clips/...), which doesn't exist until enqueue_story.enqueue()
creates the Story row. enqueue_story._upload_clip_assets() fills object_key in on every
entry right after, before the timeline is ever committed — so by the time a Story row is
readable, its timeline is already self-contained (except for stories rendered before this
existed, whose entries simply have no "object_key").
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
