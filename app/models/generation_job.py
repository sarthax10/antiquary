"""One row per generation run, replacing media/generation_status.json. Written by
three different execution contexts (a Flask request, a background watcher thread, and
the pipeline subprocess itself) — see app/db.py for why that means plain SQLAlchemy,
not Flask-SQLAlchemy."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import Base, utcnow

VALID_JOB_STATUSES = ("queued", "running", "done", "error", "cancelled")

# The genre-strategy fork (Claude outputs/PROFESSIONAL_QUALITY_ROADMAP.md §7 item 12):
# "photographic" is the original photorealistic-documentary approach (real sourced
# imagery via Wikidata/Commons/Pexels); "illustrated" is the motion-graphics-forward
# register (see pipeline/fetch_visuals.py's _fetch_illustrated) that never attempts
# photographic sourcing at all. The user's explicit answer was to keep both and let
# whoever is generating a video choose, not to pick one direction for everyone.
VALID_VISUAL_STYLES = ("photographic", "illustrated")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    topic = Column(String(500), nullable=False, default="")
    visual_style = Column(String(20), nullable=False, default="photographic")
    status = Column(String(16), nullable=False, default="running", index=True)
    stage = Column(String(50), nullable=True)
    pid = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    resulting_story_id = Column(String(32), ForeignKey("stories.id"), nullable=True)

    user = relationship("User")
    resulting_story = relationship("Story")
