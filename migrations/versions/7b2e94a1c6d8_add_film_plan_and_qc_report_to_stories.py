"""add film_plan and qc_report to stories

Milestone 1 of Claude outputs/FILM_PLAN_ARCHITECTURE.md — the versioned FilmPlan
schema (pipeline/film_plan.py) needs somewhere to live once something starts writing
one; qc_report is bundled into the same migration since it's the same kind of additive,
nullable JSONB column and this project prefers fewer migrations over more when the
storage decision is already settled (see the architecture doc's own "smallest storage
change that carries the full schema" reasoning). Both columns are nullable and
unpopulated by anything today — this migration only adds the storage, no code writes
to either column yet.

Revision ID: 7b2e94a1c6d8
Revises: 3f8c1a9d2b47
Create Date: 2026-09-12 17:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7b2e94a1c6d8'
down_revision: Union[str, Sequence[str], None] = '3f8c1a9d2b47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("stories", sa.Column("film_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("stories", sa.Column("qc_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("stories", "qc_report")
    op.drop_column("stories", "film_plan")
