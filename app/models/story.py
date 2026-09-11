"""A generated video + its script and fact-check, replacing the old
media/queue/<id>/{meta,script}.json pair with real rows."""
import uuid

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer,
                         String, Text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base, utcnow

VALID_STORY_STATUSES = ("pending", "approved", "rejected")


def new_story_id() -> str:
    return uuid.uuid4().hex[:12]


class Story(Base):
    __tablename__ = "stories"

    id = Column(String(32), primary_key=True, default=new_story_id)
    title = Column(String(300), nullable=False, default="")
    hook = Column(Text, nullable=False, default="")
    narration = Column(Text, nullable=False, default="")
    # Ordered {"text","visual_query","entity_type"} segments the narration was split
    # into for visual sourcing/render timing — see pipeline/generate_script.py. Kept for
    # provenance (why THIS image was chosen for THIS beat); not surfaced via the API.
    beats = Column(JSONB, nullable=False, default=list)
    fact_check = Column(JSONB, nullable=False, default=dict)
    needs_human_review = Column(Boolean, nullable=False, default=True)
    status = Column(String(16), nullable=False, default="pending", index=True)
    topic = Column(String(500), nullable=False, default="")
    duration_seconds = Column(Float, nullable=True)
    video_object_key = Column(String(300), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    decided_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_by = relationship("User", foreign_keys=[created_by_id])
    decided_by = relationship("User", foreign_keys=[decided_by_id])

    @property
    def claim_counts(self) -> dict:
        counts = {"verified": 0, "uncertain": 0, "false": 0}
        for claim in (self.fact_check or {}).get("claims", []):
            verdict = claim.get("verdict")
            if verdict in counts:
                counts[verdict] += 1
        return counts
