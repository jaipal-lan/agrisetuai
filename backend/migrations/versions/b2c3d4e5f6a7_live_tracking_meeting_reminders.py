"""courier live location + meeting reminder flag

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-11 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('shipments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_lat', sa.Numeric(precision=9, scale=6), nullable=True))
        batch_op.add_column(sa.Column('last_lng', sa.Numeric(precision=9, scale=6), nullable=True))
        batch_op.add_column(sa.Column('last_location_at', sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table('team_meetings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reminded', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('team_meetings', schema=None) as batch_op:
        batch_op.drop_column('reminded')

    with op.batch_alter_table('shipments', schema=None) as batch_op:
        batch_op.drop_column('last_location_at')
        batch_op.drop_column('last_lng')
        batch_op.drop_column('last_lat')
