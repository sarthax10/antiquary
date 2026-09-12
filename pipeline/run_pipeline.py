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

# A beat whose real synthesized narration comes out shorter than this reads as a glitch
# cut, not a deliberate quick one — nothing previously merged it into a neighbor (see
# Claude outputs/OPEN_ISSUES.md audit #38 / PROFESSIONAL_QUALITY_ROADMAP.md §7 Tier 1 #4).
MIN_BEAT_DURATION = 0.9


def _merge_short_beats(
    beats: list[dict], assets: list[dict], beat_audio: list[dict]
) -> tuple[list[dict], list[dict], list[dict]]:
    """Merges any beat whose real synthesized-audio duration comes out under
    MIN_BEAT_DURATION into an adjacent beat (forward into the next beat where one exists,
    otherwise backward into the last kept beat) — so a single short exclamatory sentence
    grouped as its own beat can't produce a sub-second visual clip. Concatenates the two
    beats' narration audio (tts.concat_audio — same-voice/codec clips, so this is a
    lossless demuxer-level join, not a re-encode) and their text (in narration order);
    keeps the *surviving* beat's own visual asset rather than trying to pick a "better"
    one between two, since a stock visual can't represent two merged beats' content any
    more precisely than either alone. Safe to do before anything downstream sees these
    lists: captions.py transcribes the final concatenated narration.mp3 directly (word-
    level, not beat-boundary-based), so it's indifferent to how many beats the audio was
    assembled from — only render.py's/timeline.py's *visual* cut points depend on this."""
    if len(beats) <= 1:
        return beats, assets, beat_audio
    merged_beats: list[dict] = []
    merged_assets: list[dict] = []
    merged_audio: list[dict] = []
    i = 0
    while i < len(beats):
        duration = beat_audio[i]["duration"]
        if duration < MIN_BEAT_DURATION and len(beats) > 1:
            if i + 1 < len(beats):
                # Merge forward: fold this beat's audio/text into the NEXT beat in place,
                # then let the loop process that (now-combined) next beat normally —
                # keeps the next beat's own asset, matching "surviving beat keeps its
                # visual" above.
                combined_path = str(Path(beat_audio[i]["path"]).with_name(f"merged_{i:02d}.mp3"))
                tts.concat_audio([beat_audio[i]["path"], beat_audio[i + 1]["path"]], combined_path)
                merged_text = f"{beats[i]['text']} {beats[i + 1]['text']}"
                beats[i + 1] = {**beats[i + 1], "text": merged_text}
                beat_audio[i + 1] = {
                    **beat_audio[i + 1],
                    "path": combined_path,
                    "duration": duration + beat_audio[i + 1]["duration"],
                    "text": merged_text,
                }
                i += 1
                continue
            if merged_beats:
                # Last beat, too short, nothing after it to merge forward into — fold it
                # backward into the last beat already kept instead.
                prev_beat, prev_audio = merged_beats[-1], merged_audio[-1]
                combined_path = str(Path(prev_audio["path"]).with_name(f"merged_{i:02d}.mp3"))
                tts.concat_audio([prev_audio["path"], beat_audio[i]["path"]], combined_path)
                merged_text = f"{prev_beat['text']} {beats[i]['text']}"
                merged_beats[-1] = {**prev_beat, "text": merged_text}
                merged_audio[-1] = {
                    **prev_audio,
                    "path": combined_path,
                    "duration": prev_audio["duration"] + duration,
                    "text": merged_text,
                }
                i += 1
                continue
            # Only one beat total and it's short — nothing to merge into; keep it as is
            # rather than producing an empty beat list.
        merged_beats.append(beats[i])
        merged_assets.append(assets[i])
        merged_audio.append(beat_audio[i])
        i += 1
    return merged_beats, merged_assets, merged_audio


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


def run(topic: str, visual_style: str = "photographic") -> str:
    run_id = uuid.uuid4().hex[:10]
    work_dir = BASE_DIR / "media" / "tmp" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        script = generate_script.generate(topic, on_stage=job_manager.set_stage)
        script_path = work_dir / "script.json"
        script_path.write_text(json.dumps(script, indent=2, ensure_ascii=False))

        job_manager.set_stage("sourcing_visuals")
        visuals_dir = work_dir / "visuals"
        assets = fetch_visuals.fetch_all(str(visuals_dir), script["beats"], style=visual_style)

        job_manager.set_stage("recording_narration")
        voice = tts.pick_voice()
        audio_dir = work_dir / "audio"
        beat_audio = asyncio.run(tts.synthesize_beats(script["beats"], audio_dir, voice=voice))

        merged_beats, assets, beat_audio = _merge_short_beats(script["beats"], assets, beat_audio)

        narration_path = work_dir / "narration.mp3"
        tts.concat_audio([b["path"] for b in beat_audio], str(narration_path))

        beats, assets, beat_audio = _cap_parallel(merged_beats, assets, beat_audio, render.MAX_CLIPS)

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
                "text": audio["text"],
                "visual_query": audio.get("visual_query", ""),
            }
            for asset, audio in zip(assets, beat_audio)
        ]
        render.render(str(narration_path), str(ass_path), str(video_path), beats_final, font=font, style=visual_style)

        story_timeline = timeline_module.build_timeline(
            beats=beats,
            assets=assets,
            beat_audio=beat_audio,
            caption_track=captions.build_caption_track(words, font),
            font=font,
            voice=voice,
            music_volume=render.MUSIC_VOLUME if render.music_available() else None,
        )
        clip_files = [
            {"visual_path": asset["path"], "audio_path": audio["path"]}
            for asset, audio in zip(assets, beat_audio)
        ]

        return enqueue_story.enqueue(
            str(video_path), str(script_path), topic, timeline=story_timeline,
            clip_files=clip_files, visual_style=visual_style,
        )
    finally:
        # Every generation's work dir (source images/clips, per-beat audio, the .ass
        # file, a duplicate final.mp4 alongside the one already uploaded to MinIO)
        # otherwise accumulates forever — a real disk-fill risk on the single small
        # self-hosted server this project targets. ignore_errors: cleanup failing is
        # never worse than the run itself failing, and shouldn't mask the real error.
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else ""
    visual_style = sys.argv[2] if len(sys.argv) > 2 else "photographic"
    print(run(topic, visual_style))
