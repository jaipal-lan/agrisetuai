"""partner payout accounts + buyer saved addresses

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-12 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payout_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('method', sa.String(length=8), nullable=False),
        sa.Column('upi_id', sa.String(length=80), nullable=True),
        sa.Column('account_name', sa.String(length=120), nullable=True),
        sa.Column('account_number', sa.String(length=40), nullable=True),
        sa.Column('ifsc', sa.String(length=16), nullable=True),
        sa.Column('verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('payout_accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payout_accounts_user_id'), ['user_id'], unique=True)

    op.create_table(
        'saved_addresses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=60), nullable=False),
        sa.Column('mandal_id', sa.Integer(), nullable=False),
        sa.Column('address_line', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['mandal_id'], ['mandals.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('saved_addresses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_saved_addresses_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('saved_addresses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_saved_addresses_user_id'))
    op.drop_table('saved_addresses')
    with op.batch_alter_table('payout_accounts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_payout_accounts_user_id'))
    op.drop_table('payout_accounts')
