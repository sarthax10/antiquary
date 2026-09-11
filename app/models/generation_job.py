"""One row per generation run, replacing media/generation_status.json. Written by
three different execution contexts (a Flask request, a background watcher thread, and
the pipeline subprocess itself) — see app/db.py for why that means plain SQLAlchemy,
not Flask-SQLAlchemy."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import Base, utcnow

VALID_JOB_STATUSES = ("queued", "running", "done", "error", "cancelled")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    topic = Column(String(500), nullable=False, default="")
    status = Column(String(16), nullable=False, default="running", index=True)
    stage = Column(String(50), nullable=True)
    pid = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    resulting_story_id = Column(String(32), ForeignKey("stories.id"), nullable=True)

    user = relationship("User")
    resulting_story = relationship("Story")
