#!/usr/bin/env python3
"""Run the full generation pipeline end-to-end and insert the result as a Story row.

Usage: run_pipeline.py "<topic seed, or blank for a free pick>"
Prints the new story id.

Spawned as a subprocess by app.generation.job_manager.start() when triggered from the
API, or runnable standalone for local testing (export GENERATION_USER_ID=<a real user
id> first — every story now belongs to a user, see app/studio/service.py). Reports real
progress via job_manager.set_stage() at each genuine step — not a simulated timer.
Fully independent of Flask: only needs DATABASE_URL/S3_* env vars (see .env.example),
not the web app running.

Beats (generate_script.py) are the spine everything else hangs off: fetch_visuals.py
sources one asset per beat (a named person's actual portrait for a "person" beat, not a
generic stock photo), tts.py synthesizes each beat's narration as its own clip so its
real duration is known exactly, and render.py cuts to a new visual exactly when that
beat's own audio starts — no more "images shown on a flat fraction of total runtime
unrelated to what's being said."
"""
import asyncio
import json
import shutil
import sys
import uuid
from pathlib import Path

import captions
import enqueue_story
import fetch_visuals
import generate_script
import render
import timeline as timeline_module
import tts

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.generation import job_manager  # noqa: E402

BASE_DIR = REPO_ROOT


def _cap_parallel(beats: list[dict], assets: list[dict], beat_audio: list[dict], max_clips: int):
    """Caps all three beat-indexed lists together, the same way render.py's own
    _cap_beats() folds overflow duration into the last kept clip — done here too (not
    just inside render()) so pipeline/timeline.py builds its visual/narration tracks
    from the exact same beat set that actually ends up on screen. Before this, a >8-beat
    script (the writer prompt only asks for 4-6, but doesn't hard-cap it) would silently
    diverge: render() capped internally, but the timeline (and the player's chapter
    markers built from it) still reflected every uncapped beat — found via code review,
    not observed in practice, since scripts rarely exceed 8 beats today."""
    if len(beats) <= max_clips:
        return beats, assets, beat_audio
    overflow = sum(b["duration"] for b in beat_audio[max_clips:])
    kept_audio = [dict(b) for b in beat_audio[:max_clips]]
    kept_audio[-1]["duration"] += overflow
    return beats[:max_clips], assets[:max_clips], kept_audio


def run(topic: str) -> str:
    run_id = uuid.uuid4().hex[:10]
    work_dir = BASE_DIR / "media" / "tmp" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        script = generate_script.generate(topic, on_stage=job_manager.set_stage)
        script_path = work_dir / "script.json"
        script_path.write_text(json.dumps(script, indent=2, ensure_ascii=False))

        job_manager.set_stage("sourcing_visuals")
        visuals_dir = work_dir / "visuals"
        assets = fetch_visuals.fetch_all(str(visuals_dir), script["beats"])

        job_manager.set_stage("recording_narration")
        voice = tts.pick_voice()
        audio_dir = work_dir / "audio"
        beat_audio = asyncio.run(tts.synthesize_beats(script["beats"], audio_dir, voice=voice))
        narration_path = work_dir / "narration.mp3"
        tts.concat_audio([b["path"] for b in beat_audio], str(narration_path))

        beats, assets, beat_audio = _cap_parallel(script["beats"], assets, beat_audio, render.MAX_CLIPS)

        job_manager.set_stage("generating_captions")
        font = captions.pick_font()
        words = captions.transcribe_words(str(narration_path))
        ass_path = work_dir / "captions.ass"
        captions.build_ass(words, str(ass_path), font=font)

        job_manager.set_stage("rendering")
        video_path = work_dir / "final.mp4"
        beats_final = [
            {
                "path": asset["path"],
                "entity_type": asset["entity_type"],
                "face": asset["face"],
                "duration": audio["duration"],
            }
            for asset, audio in zip(assets, beat_audio)
        ]
        render.render(str(narration_path), str(ass_path), str(video_path), beats_final)

        story_timeline = timeline_module.build_timeline(
            beats=beats,
            assets=assets,
            beat_audio=beat_audio,
            caption_track=captions.build_caption_track(words, font),
            font=font,
            voice=voice,
            music_volume=render.MUSIC_VOLUME if render.music_available() else None,
        )

        return enqueue_story.enqueue(str(video_path), str(script_path), topic, timeline=story_timeline)
    finally:
        # Every generation's work dir (source images/clips, per-beat audio, the .ass
        # file, a duplicate final.mp4 alongside the one already uploaded to MinIO)
        # otherwise accumulates forever — a real disk-fill risk on the single small
        # self-hosted server this project targets. ignore_errors: cleanup failing is
        # never worse than the run itself failing, and shouldn't mask the real error.
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else ""
    print(run(topic))
