#!/usr/bin/env python3
"""Run the full generation pipeline end-to-end and insert the result as a Story row.

Usage: run_pipeline.py "<topic seed, or blank for a free pick>"
Prints the new story id.

Spawned as a subprocess by app.generation.job_manager.start() when triggered from the
API, or runnable standalone for local testing. Reports real progress via
job_manager.set_stage() at each genuine step — not a simulated timer. Fully independent
of Flask: only needs DATABASE_URL/S3_* env vars (see .env.example), not the web app
running.
"""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import captions
import enqueue_story
import fetch_visuals
import generate_script
import render
import tts

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.generation import job_manager  # noqa: E402

BASE_DIR = REPO_ROOT


def run(topic: str) -> str:
    run_id = uuid.uuid4().hex[:10]
    work_dir = BASE_DIR / "media" / "tmp" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)

    script = generate_script.generate(topic, on_stage=job_manager.set_stage)
    script_path = work_dir / "script.json"
    script_path.write_text(json.dumps(script, indent=2, ensure_ascii=False))

    job_manager.set_stage("sourcing_visuals")
    visuals_dir = work_dir / "visuals"
    fetch_visuals.fetch_all(str(visuals_dir), script["visual_queries"])
    media = sorted(str(p) for p in visuals_dir.glob("img_*"))

    job_manager.set_stage("recording_narration")
    narration_path = work_dir / "narration.mp3"
    asyncio.run(tts.synthesize(script["narration"], str(narration_path), tts.DEFAULT_VOICE))

    job_manager.set_stage("generating_captions")
    words = captions.transcribe_words(str(narration_path))
    ass_path = work_dir / "captions.ass"
    captions.build_ass(words, str(ass_path))

    job_manager.set_stage("rendering")
    video_path = work_dir / "final.mp4"
    render.render(str(narration_path), str(ass_path), str(video_path), media)

    return enqueue_story.enqueue(str(video_path), str(script_path), topic)


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else ""
    print(run(topic))
