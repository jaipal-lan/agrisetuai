"""advisory logs: follow-up done/notified tracking

Revision ID: e5b8d3c6a2f1
Revises: d4a7c2e9f1b8
Create Date: 2026-11-10 01:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b8d3c6a2f1'
down_revision: Union[str, None] = 'd4a7c2e9f1b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('advisory_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('follow_up_done', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('follow_up_notified', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('advisory_logs', schema=None) as batch_op:
        batch_op.drop_column('follow_up_notified')
        batch_op.drop_column('follow_up_done')
