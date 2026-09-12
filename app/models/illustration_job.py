"""A single GPU illustration generation request, claimed and fulfilled by a remote
worker over HTTP (see app/gpu_worker/routes.py and pipeline/gpu_worker.py) rather than
run in-process — this app's own hosts (reliquary in production) have no GPU; a
separate machine that does (see Claude outputs/OPEN_ISSUES.md #61/#66) polls for
pending rows here and uploads a result. Deliberately NOT tied to a Story/beat via a
foreign key: a job is a short-lived, disposable unit of work (see JOB_TTL_SECONDS in
pipeline/illustration_jobs.py) that the requesting pipeline process polls for by id and
throws away either way — no code ever looks a job up starting from a story."""
import uuid

from sqlalchemy import Column, DateTime, Integer, String, Text

from .base import Base, utcnow

VALID_ILLUSTRATION_JOB_STATUSES = ("pending", "claimed", "done", "failed", "expired")


def new_illustration_job_id() -> str:
    return uuid.uuid4().hex[:12]


class IllustrationJob(Base):
    __tablename__ = "illustration_jobs"

    id = Column(String(32), primary_key=True, default=new_illustration_job_id)
    prompt = Column(Text, nullable=False)
    width = Column(Integer, nullable=False, default=512)
    height = Column(Integer, nullable=False, default=512)
    seed = Column(Integer, nullable=True)
    status = Column(String(16), nullable=False, default="pending", index=True)
    image_object_key = Column(String(300), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
