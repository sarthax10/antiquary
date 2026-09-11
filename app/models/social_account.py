"""A user's connected third-party publishing account (YouTube channel, Instagram
Business account) — one row per (user, platform); v1 supports a single connected
account per platform per user, not multiple channels each.

access_token/refresh_token are stored encrypted (see app/crypto.py) — real credentials
to a user's external account, not something to leave in plaintext like the rest of this
schema. Encryption itself happens in app/social/service.py, not here — this is ORM
schema only, per docs/ARCHITECTURE.md."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from .base import Base, utcnow

VALID_SOCIAL_PLATFORMS = ("youtube", "instagram")


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    __table_args__ = (UniqueConstraint("user_id", "platform", name="uq_social_account_user_platform"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    platform = Column(String(16), nullable=False)
    external_account_id = Column(String(128), nullable=False)
    external_account_name = Column(String(300), nullable=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(String(500), nullable=True)
    connected_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    user = relationship("User")
