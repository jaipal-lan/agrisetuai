"""composite indexes for discovery hot paths

Single-column indexes already exist on listings.status, .mandal_id, .commodity_id
and on orders.status/.buyer_id/.seller_id. These composites speed the two hottest
discovery reads before volume grows: open listings within a mandal, and open
listings grouped by commodity (the product grid).

Revision ID: b2d4f6a8c0e1
Revises: c4e1f0a9b7d3
Create Date: 2026-11-22 15:10:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b2d4f6a8c0e1'
down_revision: Union[str, None] = 'c4e1f0a9b7d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.create_index('ix_listings_status_mandal', ['status', 'mandal_id'], unique=False)
        batch_op.create_index('ix_listings_status_commodity', ['status', 'commodity_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('listings', schema=None) as batch_op:
        batch_op.drop_index('ix_listings_status_commodity')
        batch_op.drop_index('ix_listings_status_mandal')
