#!/usr/bin/env python3
"""Run the full generation pipeline end-to-end and drop the result in the review queue.

Usage: run_pipeline.py "<topic seed, or blank for a free pick>"
Prints the review queue item id.

This is what an n8n "Generate" workflow's Execute Command node should call.
"""
import asyncio
import json
import sys
import uuid
from pathlib import Path

import captions
import enqueue_for_review
import fetch_visuals
import generate_script
import render
import tts

BASE_DIR = Path(__file__).resolve().parent.parent


def run(topic: str) -> str:
    run_id = uuid.uuid4().hex[:10]
    work_dir = BASE_DIR / "media" / "tmp" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)

    script = generate_script.generate(topic)
    script_path = work_dir / "script.json"
    script_path.write_text(json.dumps(script, indent=2, ensure_ascii=False))

    visuals_dir = work_dir / "visuals"
    fetch_visuals.fetch_all(str(visuals_dir), script["visual_queries"])
    media = sorted(str(p) for p in visuals_dir.glob("img_*"))

    narration_path = work_dir / "narration.mp3"
    asyncio.run(tts.synthesize(script["narration"], str(narration_path), tts.DEFAULT_VOICE))

    words = captions.transcribe_words(str(narration_path))
    ass_path = work_dir / "captions.ass"
    captions.build_ass(words, str(ass_path))

    video_path = work_dir / "final.mp4"
    render.render(str(narration_path), str(ass_path), str(video_path), media)

    return enqueue_for_review.enqueue(str(video_path), str(script_path), topic)


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else ""
    print(run(topic))
