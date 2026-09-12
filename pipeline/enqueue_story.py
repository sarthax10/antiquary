#!/usr/bin/env python3
"""Insert a rendered video + its script/fact-check data as a Story row, and upload the
video to MinIO. Replaces the old JSON-file queue entirely — this is the last step of
the generation pipeline, called from run_pipeline.py.

Usage: enqueue_story.py <video.mp4> <script.json> [topic]
Prints the new story id.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from app.db import get_session  # noqa: E402
from app.models import Story  # noqa: E402
from app.storage import upload_asset, upload_video  # noqa: E402

# Per-clip visual content types worth naming explicitly; anything else (a video clip
# extension) falls back to a generic octet-stream — MinIO doesn't need an exact type to
# store/serve the bytes back correctly for our own download_asset() round-trip.
_VISUAL_CONTENT_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".m4v": "video/mp4",
}


def _upload_clip_assets(timeline: dict, clip_files: list[dict], user_id: int, story_id: str) -> dict:
    """Durably uploads each beat's local visual/audio clip to MinIO under the story's own
    namespace and records the resulting object key on the matching timeline track entry.
    Without this, the timeline has no asset to ever re-render from (see pipeline/
    timeline.py) — run_pipeline.py's temp work dir is deleted right after enqueue()
    returns (its own `finally` block), so this is the only chance to keep them.

    clip_files must be the same length, same order as timeline["tracks"]["visual"]/
    ["narration"] — guaranteed by run_pipeline.py building all three from the same
    (already beat-capped) assets/beat_audio lists."""
    visual_track = timeline["tracks"]["visual"]
    narration_track = timeline["tracks"]["narration"]
    base = f"stories/{user_id}/{story_id}/clips"
    for i, clip in enumerate(clip_files):
        visual_ext = Path(clip["visual_path"]).suffix.lower() or ".jpg"
        visual_key = f"{base}/visual_{i:02d}{visual_ext}"
        upload_asset(clip["visual_path"], visual_key, _VISUAL_CONTENT_TYPES.get(visual_ext, "application/octet-stream"))
        visual_track[i]["object_key"] = visual_key

        audio_key = f"{base}/audio_{i:02d}.mp3"
        upload_asset(clip["audio_path"], audio_key, "audio/mpeg")
        narration_track[i]["object_key"] = audio_key
    return timeline


def _probe_duration(video_path: str) -> float | None:
    """Real duration read from the actual file via ffprobe — never fabricate this."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, check=True, timeout=15,
        )
        return round(float(out.stdout.strip()), 1)
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def enqueue(
    video_path: str,
    script_json_path: str,
    topic: str = "",
    timeline: dict | None = None,
    clip_files: list[dict] | None = None,
    visual_style: str = "documentary",
) -> str:
    script = json.loads(open(script_json_path).read())
    duration = _probe_duration(video_path)

    # Every story belongs to a user now (app/studio/service.py scopes the review desk
    # to created_by_id), so this can no longer be optional the way it was pre-Phase-2.
    # job_manager.start() always sets this when a generation is triggered through the
    # app; for a standalone/manual pipeline run, export it yourself first.
    user_id_env = os.environ.get("GENERATION_USER_ID")
    if not user_id_env:
        raise RuntimeError(
            "GENERATION_USER_ID must be set (job_manager.start() sets this "
            "automatically; for a standalone run export GENERATION_USER_ID=<user id>)."
        )
    user_id = int(user_id_env)

    session = get_session()
    story = Story(
        title=script.get("title", ""),
        hook=script.get("hook", ""),
        narration=script.get("narration", ""),
        beats=[{k: b[k] for k in ("text", "visual_query", "entity_type")} for b in script.get("beats", [])],
        timeline=timeline or {},
        fact_check=script.get("fact_check", {}),
        needs_human_review=script.get("needs_human_review", True),
        status="pending",
        topic=topic,
        visual_style=visual_style,
        duration_seconds=duration,
        created_by_id=user_id,
    )
    session.add(story)
    session.commit()  # need story.id before naming the MinIO object

    object_key = f"stories/{user_id}/{story.id}/video.mp4"
    upload_video(video_path, object_key)
    story.video_object_key = object_key

    if clip_files and timeline:
        # flag_modified is required here, not just a reassignment — SQLAlchemy's flush
        # uses the JSONB column's own before/after `==` history to decide whether to
        # include it in the UPDATE, and since _upload_clip_assets mutates the same dict
        # object in place, before and after are literally identical by reference and
        # compare equal, so a plain reassignment alone is silently dropped from the
        # UPDATE (confirmed live — see Claude outputs/OPEN_ISSUES.md). This particular
        # call happened to still work because it runs in the same flush as this Story's
        # own initial INSERT, but relying on that would be fragile/version-dependent;
        # flag_modified makes it correct unconditionally.
        story.timeline = _upload_clip_assets(timeline, clip_files, user_id, story.id)
        flag_modified(story, "timeline")

    session.commit()

    return story.id


if __name__ == "__main__":
    video_path = sys.argv[1]
    script_json_path = sys.argv[2]
    topic = sys.argv[3] if len(sys.argv) > 3 else ""
    print(enqueue(video_path, script_json_path, topic))
