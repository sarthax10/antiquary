#!/usr/bin/env python3
"""Add a rendered video + its script/fact-check data to the local review queue.

Usage: enqueue_for_review.py <video.mp4> <script.json> [topic]
Prints the queue item id.

Called as the last step of the generation pipeline (by hand, or from an n8n
Execute Command node). The review dashboard (review_app.py) reads this same
queue directory.
"""
import json
import shutil
import sys
import time
import uuid
from pathlib import Path

QUEUE_DIR = Path(__file__).resolve().parent.parent / "media" / "queue"


def enqueue(video_path: str, script_json_path: str, topic: str = "") -> str:
    item_id = uuid.uuid4().hex[:12]
    item_dir = QUEUE_DIR / item_id
    item_dir.mkdir(parents=True, exist_ok=False)

    shutil.copy2(video_path, item_dir / "video.mp4")
    shutil.copy2(script_json_path, item_dir / "script.json")

    meta = {
        "id": item_id,
        "topic": topic,
        "status": "pending",
        "created_at": time.time(),
        "decided_at": None,
    }
    (item_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return item_id


if __name__ == "__main__":
    video_path = sys.argv[1]
    script_json_path = sys.argv[2]
    topic = sys.argv[3] if len(sys.argv) > 3 else ""
    print(enqueue(video_path, script_json_path, topic))
