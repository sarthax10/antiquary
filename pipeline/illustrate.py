#!/usr/bin/env python3
"""GPU-based illustration generation — a real, locally-generated flat-vector
illustration per beat, ranked as one candidate among a beat's real sourced imagery
rather than a separate fixed "style" (see Claude outputs/OPEN_ISSUES.md #61 and #66,
which merged the old "photographic"/"illustrated" fork into pipeline/asset_ranking.py).

As of #66, this module only runs inside pipeline/gpu_worker.py — a process that polls a
DIFFERENT machine than the one running the web app/pipeline for illustration_jobs (see
app/gpu_worker/routes.py) and generates on whichever machine actually has a GPU. This
app's own deploy hosts don't need one; `gpu_illustration_available()` is the single gate
the worker checks before calling in here at all, and every import/generation call is
wrapped so a missing dependency, a missing GPU, an OOM, or any other failure returns a
clean False/None rather than crashing the worker loop — the requesting side (pipeline/
illustration_jobs.py) always times out and falls through to real sourcing only. This
mirrors this project's other "generate, don't assume" precedents (motion_graphics.py,
pipeline/generate_sfx.py) but is the first one that needs real GPU compute rather than
pure ffmpeg — see requirements-gpu.txt/Dockerfile for how the optional dependency stack
is kept out of a non-GPU deploy's image entirely.

Model: stabilityai/sd-turbo — chosen specifically for speed (1-4 step generation, no
classifier-free-guidance pass needed) over standard 20-50 step Stable Diffusion.
Confirmed on the actual deployment host (RTX 3060, 6GB VRAM): model load ~10-30s (once
per worker process, not per beat — see _get_pipeline's caching), then well under a
second per image once warm, ~3.25GB peak VRAM. Generates at the model's native
512x512 — a real experiment this session (see OPEN_ISSUES.md #66) confirmed requesting
768x768 directly produces a DUPLICATED-SUBJECT artifact (two heads instead of one) on
this exact model, a known failure mode of pushing a model above its trained resolution,
so 512 is a deliberate choice, not a shortcut. The resulting image is handed to
render.py exactly like any other sourced still image, so the existing Ken Burns pan/
zoom/framing-intent machinery (see render.py's _zoompan_expr/_resolve_zoom_in) crops and
animates it the same way it would a photograph — no new rendering path needed.

Content-safety note, stated plainly: this does not add its own moderation layer beyond
whatever safety-checker component (if any) the model repository itself bundles —
building real content moderation was out of scope for this pass. The practical risk is
low (prompts are short, controlled `visual_query` phrases about historical subjects,
not open user input), but it is a real, known limitation, not a solved one.
"""
import re
from pathlib import Path

STYLE_SUFFIX = (
    "flat vector illustration, minimalist geometric shapes, muted earthy documentary "
    "color palette, editorial infographic style, clean background, no text, no watermark"
)
IMAGE_SIZE = 512
NUM_STEPS = 4  # bumped from 2 (#61) to 4 for #66's "polished, not half-baked" bar — the
# top of SD-Turbo's own supported 1-4 step range (it's distilled specifically for this
# range; more steps than 4 isn't meaningfully better since the model was never trained
# for standard many-step guided sampling). Real timing measured this session: ~0.5-0.7s
# per image once warm at 4 steps vs ~0.4s at 2 — a real but small cost, easily affordable
# now that generation happens asynchronously in a remote worker (see module docstring)
# rather than blocking a person's live request as it did before #66.
GUIDANCE_SCALE = 0.0  # SD-Turbo is trained for guidance-free (distilled) sampling; a
# nonzero value here re-adds a second forward pass per step for no quality benefit.

# A real, reproduced failure mode (#61, re-confirmed this session, see OPEN_ISSUES.md
# #66): multi-subject/crowd prompts come out as a degenerate, repetitive pattern of
# malformed tiny figures — visibly broken, not a borderline case, and NOT something
# sharpness/resolution scoring can detect (pipeline/image_quality.py's own docstring has
# the measured numbers proving that). Real archival photos/footage of crowds and groups
# are also usually easy to source (event/crowd scenes are exactly what stock and archive
# photography covers well), so the honest fix is to not attempt illustration for these
# prompts at all rather than ship a known-broken generation — see
# is_multi_subject_prompt(), checked by pipeline/fetch_visuals.py before it ever creates
# a job.
_MULTI_SUBJECT_WORDS = frozenset({
    "crowd", "crowds", "soldiers", "army", "armies", "legion", "legions", "troops",
    "marching", "people", "gathering", "mob", "audience", "spectators", "workers",
    "villagers", "citizens", "population", "masses", "protesters", "rally", "parade",
    "regiment", "battalion", "team", "group", "families", "refugees", "crew",
})
_WORD_RE = re.compile(r"[a-z']+")


def is_multi_subject_prompt(visual_query: str) -> bool:
    """Whole-word match only (same discipline as render.py's _classify_mood) — "team"
    must fire on "the team celebrated" but nothing should fire on an unrelated
    substring."""
    words = set(_WORD_RE.findall((visual_query or "").lower()))
    return bool(words & _MULTI_SUBJECT_WORDS)

_pipeline = None  # lazy-loaded once per process, reused across every beat in a run —
# loading it per-beat would add the ~10-30s load cost to every single image.
_load_failed = False  # sticky: if loading ever fails in this process (OOM, corrupt
# cache, no network for the first-ever download...), don't retry on every subsequent
# beat — fall back to the animated-backdrop path for the rest of this run instead of
# repeatedly eating the load attempt's latency/log noise.


def gpu_illustration_available() -> bool:
    """Cheap, side-effect-free check — does NOT load the model. Callers use this to
    decide which code path to take at all; _get_pipeline() (triggered only by an actual
    generate_illustration() call) does the real, slower work."""
    if _load_failed:
        return False
    try:
        import torch
    except ImportError:
        return False
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        # A real, if rare, failure mode: torch installed but the CUDA driver/runtime is
        # broken/mismatched in a way that raises rather than cleanly returning False.
        return False


def _get_pipeline():
    global _pipeline, _load_failed
    if _pipeline is not None:
        return _pipeline
    if _load_failed:
        return None
    try:
        import torch
        from diffusers import AutoPipelineForText2Image

        pipe = AutoPipelineForText2Image.from_pretrained(
            "stabilityai/sd-turbo", dtype=torch.float16, variant="fp16",
        )
        pipe.to("cuda")
        _pipeline = pipe
        return _pipeline
    except Exception as e:
        import sys
        print(f"[illustrate] model load failed, falling back to animated backdrop for "
              f"this run: {type(e).__name__}: {e}", file=sys.stderr)
        _load_failed = True
        return None


def illustration_prompt(visual_query: str, entity_type: str) -> str:
    """A short, on-topic phrase plus a fixed style suffix — deliberately not
    entity_type-branching the style itself (a consistent visual language across a video
    matters more than per-beat style variety here, unlike the placeholder backdrop's
    warm/cool palette split, which exists precisely because it has no other content to
    differentiate beats with)."""
    subject = (visual_query or entity_type or "a historical scene").strip()
    return f"{subject}, {STYLE_SUFFIX}"


def generate_illustration(prompt: str, out_path: Path, seed: int | None = None) -> bool:
    """Returns True and writes a real PNG to out_path on success; False (out_path
    untouched) on any failure — a caller checks the return value and falls back, never
    assumes success from the call not raising."""
    pipe = _get_pipeline()
    if pipe is None:
        return False
    try:
        import torch
        generator = torch.Generator(device="cuda")
        if seed is not None:
            generator = generator.manual_seed(seed)
        image = pipe(
            prompt=prompt,
            num_inference_steps=NUM_STEPS,
            guidance_scale=GUIDANCE_SCALE,
            height=IMAGE_SIZE,
            width=IMAGE_SIZE,
            generator=generator,
        ).images[0]
        image.save(out_path)
        return True
    except Exception as e:
        import sys
        print(f"[illustrate] generation failed for prompt {prompt!r}, falling back to "
              f"animated backdrop for this beat: {type(e).__name__}: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    import sys
    prompt = sys.argv[1] if len(sys.argv) > 1 else "a Roman general"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/illustration_test.png")
    ok = generate_illustration(illustration_prompt(prompt, "person"), out)
    print(f"{'OK' if ok else 'FAILED'}: {out}")
