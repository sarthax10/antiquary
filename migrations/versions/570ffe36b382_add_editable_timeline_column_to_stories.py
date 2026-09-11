"""add editable timeline column to stories

Foundation for the upcoming timeline editor — see docs/ARCHITECTURE.md. Additive and
inert: nothing reads this column yet (render.py still renders from beats/tts output
directly), so this cannot change any existing behavior. Existing rows default to {}.

Revision ID: 570ffe36b382
Revises: dd9d51938ffc
Create Date: 2026-09-11 23:11:26.935219

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '570ffe36b382'
down_revision: Union[str, Sequence[str], None] = 'dd9d51938ffc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("stories", sa.Column("timeline", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"))
    op.alter_column("stories", "timeline", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("stories", "timeline")
