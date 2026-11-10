"""advisory logs: offline client_draft_id

Revision ID: d4a7c2e9f1b8
Revises: c3f9e1a2b4d6
Create Date: 2026-11-10 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a7c2e9f1b8'
down_revision: Union[str, None] = 'c3f9e1a2b4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('advisory_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('client_draft_id', sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint('uq_advisory_logs_client_draft_id', ['client_draft_id'])


def downgrade() -> None:
    with op.batch_alter_table('advisory_logs', schema=None) as batch_op:
        batch_op.drop_constraint('uq_advisory_logs_client_draft_id', type_='unique')
        batch_op.drop_column('client_draft_id')
