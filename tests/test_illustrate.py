"""Tests for pipeline/illustrate.py — GPU-based illustration generation (see Claude
outputs/OPEN_ISSUES.md #61). Most of this module can only be meaningfully exercised on
a real CUDA GPU (real model load, real generation) — that's covered separately by this
session's own real-hardware verification (a real RTX 3060 test run, images inspected).
These tests cover what's testable everywhere, on any machine including one with no GPU
at all: the pure prompt-construction logic, and — the actually load-bearing behavioral
guarantee this module exists to provide — that every failure mode (no torch installed,
no CUDA available, a load/generation exception) degrades cleanly to False/None rather
than raising, since fetch_visuals.py's entire fallback-to-animated-backdrop design
depends on that contract holding.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import illustrate  # noqa: E402


def test_illustration_prompt_includes_the_subject_and_style_suffix():
    prompt = illustrate.illustration_prompt("Roman general portrait", "person")
    assert "Roman general portrait" in prompt
    assert illustrate.STYLE_SUFFIX in prompt


def test_illustration_prompt_falls_back_to_entity_type_when_no_query():
    prompt = illustrate.illustration_prompt("", "place")
    assert "place" in prompt


def test_illustration_prompt_falls_back_to_generic_when_nothing_given():
    prompt = illustrate.illustration_prompt("", "")
    assert "historical scene" in prompt


def test_gpu_illustration_available_is_a_clean_bool(monkeypatch):
    # Whatever the real answer is on this machine, it must be a bool, not raise, and
    # not have any side effect (no model load) — a caller may check this many times
    # per generation run just to decide which branch to take.
    result = illustrate.gpu_illustration_available()
    assert isinstance(result, bool)
    assert illustrate._pipeline is None  # confirms no model load was triggered


def test_gpu_illustration_available_false_when_torch_not_importable(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "torch":
            raise ImportError("simulated: torch not installed")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(illustrate, "_load_failed", False)
    assert illustrate.gpu_illustration_available() is False


def test_gpu_illustration_available_false_after_a_sticky_load_failure(monkeypatch):
    monkeypatch.setattr(illustrate, "_load_failed", True)
    assert illustrate.gpu_illustration_available() is False


def test_generate_illustration_returns_false_when_pipeline_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(illustrate, "_get_pipeline", lambda: None)
    out = tmp_path / "out.png"
    assert illustrate.generate_illustration("a prompt", out) is False
    assert not out.exists()


def test_generate_illustration_returns_false_on_generation_exception(monkeypatch, tmp_path):
    class _BoomPipeline:
        def __call__(self, *a, **kw):
            raise RuntimeError("simulated CUDA OOM")

    monkeypatch.setattr(illustrate, "_get_pipeline", lambda: _BoomPipeline())
    out = tmp_path / "out.png"
    assert illustrate.generate_illustration("a prompt", out) is False
    assert not out.exists()


def test_get_pipeline_is_sticky_after_a_load_failure(monkeypatch):
    # Confirms the "don't retry every beat" contract from the module docstring: once
    # _load_failed is set, _get_pipeline must keep returning None without re-attempting
    # the (slow/expensive) load.
    monkeypatch.setattr(illustrate, "_pipeline", None)
    monkeypatch.setattr(illustrate, "_load_failed", True)
    assert illustrate._get_pipeline() is None
