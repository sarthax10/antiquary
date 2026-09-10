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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import get_session  # noqa: E402
from app.models import Story  # noqa: E402
from app.storage import upload_video  # noqa: E402


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


def enqueue(video_path: str, script_json_path: str, topic: str = "") -> str:
    script = json.loads(open(script_json_path).read())
    duration = _probe_duration(video_path)

    session = get_session()
    story = Story(
        title=script.get("title", ""),
        hook=script.get("hook", ""),
        narration=script.get("narration", ""),
        visual_queries=script.get("visual_queries", []),
        fact_check=script.get("fact_check", {}),
        needs_human_review=script.get("needs_human_review", True),
        status="pending",
        topic=topic,
        duration_seconds=duration,
    )
    user_id = os.environ.get("GENERATION_USER_ID")
    if user_id:
        story.created_by_id = int(user_id)
    session.add(story)
    session.commit()  # need story.id before naming the MinIO object

    object_key = f"stories/{story.id}/video.mp4"
    upload_video(video_path, object_key)
    story.video_object_key = object_key
    session.commit()

    return story.id


if __name__ == "__main__":
    video_path = sys.argv[1]
    script_json_path = sys.argv[2]
    topic = sys.argv[3] if len(sys.argv) > 3 else ""
    print(enqueue(video_path, script_json_path, topic))
