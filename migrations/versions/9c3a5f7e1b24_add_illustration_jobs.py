"""add illustration_jobs

New table backing the remote GPU illustration worker (Claude outputs/
OPEN_ISSUES.md #66): the old fixed "photographic"/"illustrated" visual_style fork is
merged into one flow where every beat's real sourced candidate is ranked against a
generated-illustration candidate fulfilled by a separate GPU-having machine polling
this table over HTTP (see app/gpu_worker/routes.py, pipeline/illustration_jobs.py,
pipeline/gpu_worker.py). A fresh, standalone table rather than reusing generation_jobs
— a job here is per-beat-image, not per-story, and is disposable (never read again once
its requester's poll loop picks up "done"/"failed"/"expired").

Revision ID: 9c3a5f7e1b24
Revises: 7b2e94a1c6d8
Create Date: 2026-09-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9c3a5f7e1b24'
down_revision: Union[str, Sequence[str], None] = '7b2e94a1c6d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "illustration_jobs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("image_object_key", sa.String(length=300), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_illustration_jobs_status"), "illustration_jobs", ["status"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_illustration_jobs_status"), table_name="illustration_jobs")
    op.drop_table("illustration_jobs")
