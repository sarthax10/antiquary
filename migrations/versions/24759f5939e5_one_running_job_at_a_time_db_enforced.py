"""one running job at a time, db-enforced

app/generation/job_manager.py already refuses to start a second job while one is
running, but that check-then-insert lived only in an in-process threading.Lock — with
gunicorn's 2 worker processes (fixed to 1 in this same change, but this index is cheap
defense-in-depth against a future re-scale reintroducing the race) two near-simultaneous
requests on different workers could both pass the "is anything running" check before
either committed. A partial unique index makes the invariant real at the DB level: a
second concurrent INSERT of a running row now fails outright instead of racing.

Revision ID: 24759f5939e5
Revises: 7d6d14915223
Create Date: 2026-09-11 21:22:08.692249

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '24759f5939e5'
down_revision: Union[str, Sequence[str], None] = '7d6d14915223'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # If more than one row is already 'running' — exactly the pre-fix race this index
    # exists to prevent, reproduced in testing — creating the index below raises
    # UniqueViolation and crashes the upgrade outright, with no automatic recovery (see
    # this migration's module docstring for why that's fatal, not just noisy). Defuse it:
    # keep the oldest running row as the real one and mark any others as errored — they
    # were never a valid state to begin with, and self-healing them here is strictly
    # better than leaving the app permanently unable to start.
    op.execute(
        """
        UPDATE generation_jobs
        SET status = 'error',
            error = 'Cleared by migration 24759f5939e5: found running concurrently with another job.'
        WHERE status = 'running'
          AND id NOT IN (
              SELECT id FROM generation_jobs WHERE status = 'running' ORDER BY started_at ASC LIMIT 1
          )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ix_generation_jobs_one_running
        ON generation_jobs ((1))
        WHERE status = 'running'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX ix_generation_jobs_one_running")
