#!/usr/bin/env python3
"""GPU-based illustration generation for "illustrated" visual style (see
Claude outputs/OPEN_ISSUES.md #61 and the genre-strategy resolution, #57) — a real,
locally-generated flat-vector illustration per beat, in place of the animated gradient
backdrop, when a CUDA GPU is actually present.

Why this exists as a separate, optional module rather than a hard dependency: the
deployed host's GPU status isn't a given (this project runs on modest self-hosted
hardware by design — see CLAUDE.md), and torch/diffusers are large (~2.5GB+) downloads
with real VRAM requirements. `gpu_illustration_available()` is the single gate
everything else in this pipeline checks before calling in here at all; every import and
every generation call is wrapped so a missing dependency, a missing GPU, an OOM, or any
other failure returns a clean False/None instead of crashing the run — fetch_visuals.py
always has the existing animated-backdrop path (`_placeholder_clip`, see #16) to fall
back to. This mirrors this project's other "generate, don't assume" precedents
(motion_graphics.py, pipeline/generate_sfx.py) but is the first one that needs real GPU
compute rather than pure ffmpeg — see requirements-gpu.txt/Dockerfile for how the
optional dependency stack is kept out of a non-GPU deploy's image entirely.

Model: stabilityai/sd-turbo — chosen specifically for speed (1-4 step generation, no
classifier-free-guidance pass needed) over standard 20-50 step Stable Diffusion, since
this runs synchronously inside a real generation pipeline that a person is waiting on,
not as a batch job. Confirmed on the actual deployment host (RTX 3060, 6GB VRAM): model
load ~10-30s (once per generation run, not per beat — see _get_pipeline's caching),
then ~0.4-2s per image, ~3.25GB peak VRAM. Generates at the model's native 512x512 —
deliberately NOT stretched to the app's 1080x1920 output frame here; the resulting
image is handed to render.py exactly like any other sourced still image, so the
existing Ken Burns pan/zoom/framing-intent machinery (see render.py's
_zoompan_expr/_resolve_zoom_in) crops and animates it the same way it would a
photograph — no new rendering path needed.

Content-safety note, stated plainly: this does not add its own moderation layer beyond
whatever safety-checker component (if any) the model repository itself bundles —
building real content moderation was out of scope for this pass. The practical risk is
low (prompts are short, controlled `visual_query` phrases about historical subjects,
not open user input), but it is a real, known limitation, not a solved one.
"""
from pathlib import Path

STYLE_SUFFIX = (
    "flat vector illustration, minimalist geometric shapes, muted earthy documentary "
    "color palette, editorial infographic style, clean background, no text, no watermark"
)
IMAGE_SIZE = 512
NUM_STEPS = 2  # see module docstring's measured timings; 1 step is visibly rougher, 2 is
# a good speed/quality tradeoff at essentially the same wall-clock cost once warm.
GUIDANCE_SCALE = 0.0  # SD-Turbo is trained for guidance-free (distilled) sampling; a
# nonzero value here re-adds a second forward pass per step for no quality benefit.

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
