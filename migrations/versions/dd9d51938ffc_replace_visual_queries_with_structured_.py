"""replace visual_queries with structured beats

visual_queries was a flat list of search-query strings, never surfaced via the API —
purely pipeline provenance. It's replaced by "beats" ({"text","visual_query",
"entity_type"} per segment, see pipeline/generate_script.py) which isn't
shape-compatible, so this drops the old column and adds the new one fresh rather than
attempting a data migration between two structurally different JSON shapes; existing
stories simply have an empty beats list (they already have a rendered video — beats data
only matters at generation time).

Revision ID: dd9d51938ffc
Revises: 24759f5939e5
Create Date: 2026-09-11 21:45:56.319343

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'dd9d51938ffc'
down_revision: Union[str, Sequence[str], None] = '24759f5939e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("stories", sa.Column("beats", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"))
    op.alter_column("stories", "beats", server_default=None)
    op.drop_column("stories", "visual_queries")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("stories", sa.Column("visual_queries", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"))
    op.alter_column("stories", "visual_queries", server_default=None)
    op.drop_column("stories", "beats")
