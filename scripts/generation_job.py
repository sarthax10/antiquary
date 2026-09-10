#!/usr/bin/env python3
"""Runs run_pipeline.py as a fully separate OS process (not a thread inside the Flask
process) so a crash or hang in generation can never take the dashboard down with it, and
tracks its state in a small JSON file so status survives a Flask restart and is visible
to every request (not just the one that started the job).

Only one generation is ever allowed to run at a time — starting a second one while the
first is still going wastes the CPU-bound local model's time twice over and was the
direct cause of real failures earlier in this project (concurrent Ollama requests
truncating each other's output). `start()` refuses if a live job is already running.
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
STATUS_PATH = BASE_DIR / "media" / "generation_status.json"
LOG_PATH = BASE_DIR / "media" / "generation_log.txt"

_lock = threading.Lock()


def _read_status() -> dict:
    if not STATUS_PATH.exists():
        return {"status": "idle"}
    try:
        return json.loads(STATUS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {"status": "idle"}


def _write_status(data: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(data, indent=2))


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _log_tail(n_chars: int = 800) -> str:
    if not LOG_PATH.exists():
        return ""
    text = LOG_PATH.read_text(errors="replace")
    return text[-n_chars:]


def get_status() -> dict:
    """Read current status, self-healing if a tracked process died without the watcher
    thread updating it (e.g. the Flask app itself was restarted mid-generation)."""
    status = _read_status()
    if status.get("status") == "running":
        pid = status.get("pid")
        if not pid or not _pid_alive(pid):
            status = {
                **status,
                "status": "error",
                "error": "Generation process ended unexpectedly (was the app restarted mid-run?).",
                "finished_at": time.time(),
            }
            _write_status(status)
    return status


def _watch(proc: subprocess.Popen, topic: str, started_at: float) -> None:
    returncode = proc.wait()
    if returncode == 0:
        tail = _log_tail(200).strip()
        item_id = tail.splitlines()[-1].strip() if tail else None
        _write_status({
            "status": "done",
            "topic": topic,
            "pid": proc.pid,
            "started_at": started_at,
            "finished_at": time.time(),
            "item_id": item_id,
            "error": None,
        })
    else:
        _write_status({
            "status": "error",
            "topic": topic,
            "pid": proc.pid,
            "started_at": started_at,
            "finished_at": time.time(),
            "item_id": None,
            "error": _log_tail(800).strip() or f"exited with code {returncode}",
        })


def start(topic: str) -> tuple[bool, str]:
    """Returns (started, message). Refuses if a generation is already running."""
    with _lock:
        current = get_status()
        if current.get("status") == "running":
            return False, "A generation is already running."

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(LOG_PATH, "w")
        proc = subprocess.Popen(
            [sys.executable, "run_pipeline.py", topic],
            cwd=str(SCRIPTS_DIR),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )
        started_at = time.time()
        _write_status({
            "status": "running",
            "topic": topic,
            "pid": proc.pid,
            "started_at": started_at,
            "finished_at": None,
            "item_id": None,
            "error": None,
        })
        threading.Thread(target=_watch, args=(proc, topic, started_at), daemon=True).start()
        return True, "started"
