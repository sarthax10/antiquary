"""add visual_style (genre-strategy choice) to generation_jobs and stories

The genre-strategy fork (Claude outputs/PROFESSIONAL_QUALITY_ROADMAP.md #7 item 12):
keep the original photorealistic-documentary sourcing approach ("photographic") AND add
a motion-graphics-forward register ("illustrated", see pipeline/fetch_visuals.py's
_fetch_illustrated) that never attempts photographic stock sourcing at all — the user's
explicit answer was to keep both and let whoever is generating a video choose, not to
pick one direction for everyone. Stored on generation_jobs (so the pipeline subprocess
knows which to render) and, durably, on stories (so a future editor re-render stays
visually consistent with how the video was originally generated).

Revision ID: 3f8c1a9d2b47
Revises: 7a9e7dcd6ef9
Create Date: 2026-09-12 16:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3f8c1a9d2b47'
down_revision: Union[str, Sequence[str], None] = '7a9e7dcd6ef9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("generation_jobs", sa.Column("visual_style", sa.String(length=20), nullable=False, server_default="photographic"))
    op.alter_column("generation_jobs", "visual_style", server_default=None)
    op.add_column("stories", sa.Column("visual_style", sa.String(length=20), nullable=False, server_default="photographic"))
    op.alter_column("stories", "visual_style", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("stories", "visual_style")
    op.drop_column("generation_jobs", "visual_style")
