"""User account — auth identity plus the admin-approval gate.

status starts "pending" at signup; only an admin flipping it to "approved" (via the
admin dashboard) lets the account sign in and use the app. is_active (Flask-Login's own
gate) is tied directly to status, so a user who is later suspended stops being treated
as logged-in on their very next request — see the docstring on is_active below.
"""
from flask_login import UserMixin
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .base import Base, utcnow

VALID_ROLES = ("admin", "user")
VALID_USER_STATUSES = ("pending", "approved", "rejected", "suspended")


class User(Base, UserMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default="user")
    status = Column(String(16), nullable=False, default="pending", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    approved_by = relationship("User", remote_side=[id])

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_approved(self) -> bool:
        return self.status == "approved"

    @property
    def is_active(self) -> bool:
        """Flask-Login checks this on every request via the user_loader's fresh DB
        fetch (no caching) — so revoking approval takes effect immediately, not just
        on next login."""
        return self.status == "approved"

    def get_id(self) -> str:
        return str(self.id)
