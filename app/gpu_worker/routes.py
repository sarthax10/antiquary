"""HTTP surface a remote GPU-having machine polls to fulfill illustration_jobs (see
Claude outputs/OPEN_ISSUES.md #66) — NOT part of the browser-facing JSON API: no
Flask-Login session, no CSRF token (there's no cookie to forge in the first place), just
a single shared bearer token both sides read from GPU_WORKER_TOKEN. Every route 503s
when that env var is unset, matching every other optional-integration's graceful-
absence pattern in this project (see PEXELS_API_KEY etc. in .env.example) rather than
crashing or silently accepting unauthenticated requests."""
import hmac
import os
import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, request

from app.extensions import csrf

from . import service

bp = Blueprint("gpu_worker", __name__, url_prefix="/api/gpu-worker")
csrf.exempt(bp)


def _authorized() -> bool:
    token = os.environ.get("GPU_WORKER_TOKEN", "")
    if not token:
        return False
    sent = request.headers.get("X-Worker-Token", "")
    return hmac.compare_digest(sent, token)


@bp.before_request
def _check_token():
    if not os.environ.get("GPU_WORKER_TOKEN", ""):
        return jsonify(error="gpu worker disabled"), 503
    if not _authorized():
        return jsonify(error="unauthorized"), 401


@bp.route("/jobs/next")
def next_job():
    job = service.claim_next_job()
    if job is None:
        return jsonify(job=None)
    return jsonify(job={"id": job.id, "prompt": job.prompt, "width": job.width,
                         "height": job.height, "seed": job.seed})


@bp.route("/jobs/<job_id>/result", methods=["POST"])
def submit_result(job_id):
    image = request.files.get("image")
    if image is None:
        return jsonify(error="image file required"), 400
    with tempfile.TemporaryDirectory() as tmp:
        local_path = Path(tmp) / "result.png"
        image.save(local_path)
        job = service.complete_job(job_id, str(local_path), content_type=image.mimetype or "image/png")
    if job is None:
        return jsonify(error="job not found or not claimed"), 409
    return jsonify(ok=True)


@bp.route("/jobs/<job_id>/fail", methods=["POST"])
def submit_failure(job_id):
    data = request.get_json(silent=True) or {}
    job = service.fail_job(job_id, data.get("error", ""))
    if job is None:
        return jsonify(error="job not found or not claimed"), 409
    return jsonify(ok=True)
