"""add session_version to users for password-change session invalidation

Found via code review: neither self-service change-password nor admin reset-password
invalidated any *existing* session cookie — a session opened before the change (a
stolen cookie, a shared/old device) kept working indefinitely after, undercutting the
actual point of a reset. User.get_id() now encodes this version; a mismatch logs the
session out (see app/auth/__init__.py's load_user).

Revision ID: 7a9e7dcd6ef9
Revises: 570ffe36b382
Create Date: 2026-09-12 01:07:08.121206

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7a9e7dcd6ef9'
down_revision: Union[str, Sequence[str], None] = '570ffe36b382'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("users", "session_version", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "session_version")
