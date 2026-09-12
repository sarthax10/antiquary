#!/usr/bin/env python3
"""Renders a Story's *timeline* (see pipeline/timeline.py) rather than driving render.py
directly from beats/audio/captions the way run_pipeline.py's auto-generation does — this
is the piece Phase A part 2 was blocked on: a future editor's "save + re-render" action
needs to turn a human's edit into an actual new video, and it can only do that by
re-rendering from the timeline's own durably-stored per-clip assets (pipeline/
enqueue_story.py uploads these to MinIO) and its own caption track, not from the original
run's local temp files, which are deleted the moment that run finishes.

Usage: render_timeline.py <story_id>   — re-renders and re-uploads over the same
video_object_key. Mainly for manual verification; the real caller will be a future
editor route once Phase B exists (there is no route wired to this yet — nothing in the
app calls it today).
"""
import sys
import tempfile
from pathlib import Path

import captions
import render
import tts

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app import storage  # noqa: E402
from app.db import get_session  # noqa: E402
from app.models import Story  # noqa: E402


def render_from_timeline(timeline: dict, out_path: str) -> None:
    """Downloads every clip a timeline's visual/narration tracks point at, rebuilds the
    concatenated narration track and the karaoke .ass from the timeline's own data (not
    re-transcribed — the caption track's stored word timestamps are the source of truth),
    and calls the same render.render() the auto-generate pipeline uses so a timeline
    re-render and an original generation share one ffmpeg filter graph implementation."""
    tracks = timeline.get("tracks") or {}
    visual_track, narration_track = tracks.get("visual") or [], tracks.get("narration") or []
    if not visual_track or not narration_track:
        raise ValueError("timeline has no visual/narration clips to render")
    if len(visual_track) != len(narration_track):
        raise ValueError("timeline's visual and narration tracks are out of sync (different lengths)")

    with tempfile.TemporaryDirectory(prefix="antiquary_render_") as tmp:
        tmp_dir = Path(tmp)
        beats_final = []
        audio_paths = []
        for i, (visual, audio) in enumerate(zip(visual_track, narration_track)):
            if not visual.get("object_key") or not audio.get("object_key"):
                raise ValueError(
                    f"clip {i} has no durably-stored asset (object_key) — this timeline "
                    "predates per-clip asset storage, or its upload never completed"
                )
            visual_path = tmp_dir / f"visual_{i:02d}{Path(visual['object_key']).suffix}"
            storage.download_asset(visual["object_key"], str(visual_path))
            audio_path = tmp_dir / f"audio_{i:02d}.mp3"
            storage.download_asset(audio["object_key"], str(audio_path))
            audio_paths.append(str(audio_path))
            beats_final.append({
                "path": str(visual_path),
                "entity_type": visual.get("entity_type"),
                "face": visual.get("face"),
                "duration": audio["duration"],
                "text": audio.get("text", ""),
            })

        narration_path = tmp_dir / "narration.mp3"
        tts.concat_audio(audio_paths, str(narration_path))

        style = timeline.get("style") or {}
        font = captions.font_by_name(style.get("caption_font", "")) or captions.pick_font()
        ass_path = tmp_dir / "captions.ass"
        captions.build_ass_from_track(tracks.get("captions") or [], font, str(ass_path))

        render.render(str(narration_path), str(ass_path), out_path, beats_final)


def render_story(story_id: str) -> str:
    """Re-renders a story from its current Story.timeline and re-uploads it over the same
    video_object_key. A manual/CLI entry point for now — verifies the round-trip actually
    reproduces a valid video without needing an editor UI in place yet."""
    session = get_session()
    story = session.get(Story, story_id)
    if story is None:
        raise ValueError(f"no story {story_id!r}")
    if not story.timeline or not story.timeline.get("tracks"):
        raise ValueError(f"story {story_id!r} has no timeline to render from")
    if not story.video_object_key:
        raise ValueError(f"story {story_id!r} has no video_object_key to re-upload over")

    with tempfile.TemporaryDirectory(prefix="antiquary_render_out_") as tmp:
        out_path = str(Path(tmp) / "final.mp4")
        render_from_timeline(story.timeline, out_path)
        storage.upload_video(out_path, story.video_object_key)
    return story.id


if __name__ == "__main__":
    print(render_story(sys.argv[1]))
