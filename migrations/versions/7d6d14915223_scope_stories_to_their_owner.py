"""scope stories to their owner

created_by_id becomes the real ownership field (every story a user creates already
belongs to them in spirit — this just makes it non-null and indexed instead of adding a
redundant user_id column). Legacy rows with no creator (pre-multi-user or a standalone
pipeline run with no GENERATION_USER_ID set) are backfilled to the earliest-created
admin, since some owner has to exist for the new ownership checks in app/studio/service.py.

Revision ID: 7d6d14915223
Revises: be566ae7971b
Create Date: 2026-09-11 21:20:18.949193

"""
import sys
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d6d14915223'
down_revision: Union[str, Sequence[str], None] = 'be566ae7971b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        UPDATE stories
        SET created_by_id = (SELECT id FROM users WHERE role = 'admin' ORDER BY created_at ASC LIMIT 1)
        WHERE created_by_id IS NULL
        """
    )
    # The backfill above only succeeds if an admin already exists. On a database state
    # where `stories` has rows but `users` has none yet (reproduced in testing: possible on
    # a partial restore, or migration history replayed against a fresh/emptied DB), it's a
    # silent no-op and created_by_id stays NULL — the unconditional `SET NOT NULL` below
    # would then crash the upgrade outright (IntegrityError) with no automatic recovery,
    # since docker-compose's app command retries the same failing startup forever. Guard it:
    # only enforce NOT NULL once the backfill has actually left no NULLs behind.
    bind = op.get_bind()
    remaining_null = bind.execute(
        sa.text("SELECT count(*) FROM stories WHERE created_by_id IS NULL")
    ).scalar()
    if remaining_null:
        print(
            f"WARNING: {remaining_null} story row(s) still have no owner (no admin user "
            "exists to backfill to) — leaving created_by_id nullable for now. Create an "
            "admin (seed-admin) and re-run this backfill by hand before relying on "
            "ownership scoping for these rows.",
            file=sys.stderr,
        )
    else:
        op.alter_column("stories", "created_by_id", existing_type=sa.Integer(), nullable=False)
    op.create_index(op.f("ix_stories_created_by_id"), "stories", ["created_by_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_stories_created_by_id"), table_name="stories")
    op.alter_column("stories", "created_by_id", existing_type=sa.Integer(), nullable=True)
