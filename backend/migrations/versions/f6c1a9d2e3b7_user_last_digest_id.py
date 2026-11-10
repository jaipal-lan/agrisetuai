"""users: last_digest_id watermark for the digest scheduler

Revision ID: f6c1a9d2e3b7
Revises: e5b8d3c6a2f1
Create Date: 2026-11-10 02:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6c1a9d2e3b7'
down_revision: Union[str, None] = 'e5b8d3c6a2f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_digest_id', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('last_digest_id')
