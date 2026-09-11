"""One row per (story, platform) publish attempt — mirrors GenerationJob's shape
(separate row from Story, own status/stage, survives a retry) rather than cramming
publish state onto Story itself.

`platform` is denormalized from SocialAccount rather than only reachable via
social_account_id: social_account_id is nullable/ON DELETE SET NULL specifically so
disconnecting an account (app/social/) never has to cascade-delete — or block deleting —
a user's publish history. platform + external_id/external_url stay legible even after
the account that published them is gone.

`updated_at` (auto-touched on every row update via onupdate=) is how
app/publishing/manager.py detects an orphaned pending/uploading row — e.g. the app
restarted mid-upload — by staleness, not by tracking which OS thread owns it. That
in-memory tracking would be wrong under gunicorn's multiple worker processes anyway:
a thread started in one worker is invisible to a request handled by another."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import Base, utcnow

VALID_PUBLICATION_STATUSES = ("pending", "uploading", "published", "failed")


class Publication(Base):
    __tablename__ = "publications"

    id = Column(Integer, primary_key=True)
    story_id = Column(String(32), ForeignKey("stories.id"), nullable=False)
    platform = Column(String(16), nullable=False)
    social_account_id = Column(Integer, ForeignKey("social_accounts.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(16), nullable=False, default="pending", index=True)
    stage = Column(String(50), nullable=True)
    external_id = Column(String(128), nullable=True)
    external_url = Column(String(500), nullable=True)
    error = Column(Text, nullable=True)
    requested_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    published_at = Column(DateTime(timezone=True), nullable=True)

    story = relationship("Story")
    social_account = relationship("SocialAccount")
    requested_by = relationship("User")
