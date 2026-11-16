"""daily digest: user digest categories + deferred notifications

Revision ID: c3f9e1a2b4d6
Revises: a8eb0851a62b
Create Date: 2026-11-09 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f9e1a2b4d6'
down_revision: Union[str, None] = 'a8eb0851a62b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('digest_notifications', sa.JSON(), nullable=True))
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'deferred', sa.Boolean(), nullable=False, server_default=sa.false()
        ))
        batch_op.create_index(batch_op.f('ix_notifications_deferred'), ['deferred'])


def downgrade() -> None:
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notifications_deferred'))
        batch_op.drop_column('deferred')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('digest_notifications')
