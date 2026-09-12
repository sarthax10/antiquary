"""One row per generation run, replacing media/generation_status.json. Written by
three different execution contexts (a Flask request, a background watcher thread, and
the pipeline subprocess itself) — see app/db.py for why that means plain SQLAlchemy,
not Flask-SQLAlchemy."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import Base, utcnow

VALID_JOB_STATUSES = ("queued", "running", "done", "error", "cancelled")

# Formerly a real fork: "photographic" (real sourced imagery only) vs. "illustrated"
# (GPU-generated/motion-graphics only, never attempting real sourcing) — see Claude
# outputs/OPEN_ISSUES.md #66. Merged into one unified flow: every beat now gathers real
# sourced candidates AND (when a remote GPU worker is available) a generated
# illustration, then ranks whichever real candidates exist against it — see
# pipeline/asset_ranking.py. "documentary" is the only value a NEW row can be created
# with; the column (and this name) are kept only so existing rows retain an honest
# historical record of which of the two old fixed modes actually produced them — no
# validation ever re-checks an old row against this tuple.
VALID_VISUAL_STYLES = ("documentary",)


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    topic = Column(String(500), nullable=False, default="")
    visual_style = Column(String(20), nullable=False, default="documentary")
    status = Column(String(16), nullable=False, default="running", index=True)
    stage = Column(String(50), nullable=True)
    pid = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    resulting_story_id = Column(String(32), ForeignKey("stories.id"), nullable=True)

    user = relationship("User")
    resulting_story = relationship("Story")
