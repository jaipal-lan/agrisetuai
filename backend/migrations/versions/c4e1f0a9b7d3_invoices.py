"""invoices + invoice number counter

Revision ID: c4e1f0a9b7d3
Revises: d7e9f1a3b5c2
Create Date: 2026-11-22 14:12:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e1f0a9b7d3'
down_revision: Union[str, None] = 'd7e9f1a3b5c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('invoice_counters',
    sa.Column('key', sa.String(length=16), nullable=False),
    sa.Column('last_seq', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )

    op.create_table('invoices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('number', sa.String(length=40), nullable=False),
    sa.Column('seq', sa.BigInteger(), nullable=False),
    sa.Column('fy', sa.String(length=9), nullable=False),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('buyer_id', sa.Integer(), nullable=True),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('meta', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['buyer_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_invoices_number'), ['number'], unique=True)
        batch_op.create_index(batch_op.f('ix_invoices_seq'), ['seq'], unique=False)
        batch_op.create_index(batch_op.f('ix_invoices_order_id'), ['order_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_invoices_buyer_id'), ['buyer_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invoices_buyer_id'))
        batch_op.drop_index(batch_op.f('ix_invoices_order_id'))
        batch_op.drop_index(batch_op.f('ix_invoices_seq'))
        batch_op.drop_index(batch_op.f('ix_invoices_number'))
    op.drop_table('invoices')
    op.drop_table('invoice_counters')
