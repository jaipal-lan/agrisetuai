"""team agent targets and meetings

Revision ID: a1b2c3d4e5f6
Revises: 5d7b86f0372e
Create Date: 2026-11-11 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '5d7b86f0372e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_targets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('set_by_id', sa.Integer(), nullable=False),
        sa.Column('metric', sa.String(length=32), nullable=False),
        sa.Column('target_value', sa.Integer(), nullable=False),
        sa.Column('period_start', sa.String(length=10), nullable=False),
        sa.Column('period_end', sa.String(length=10), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['set_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('agent_targets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_targets_agent_id'), ['agent_id'], unique=False)

    op.create_table(
        'team_meetings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organizer_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('scheduled_at', sa.String(length=32), nullable=False),
        sa.Column('location', sa.String(length=160), nullable=True),
        sa.Column('agenda', sa.Text(), nullable=True),
        sa.Column('attendee_ids', sa.JSON(), nullable=True),
        sa.Column('attended_ids', sa.JSON(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('mandal_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['organizer_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['mandal_id'], ['mandals.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('team_meetings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_team_meetings_organizer_id'), ['organizer_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('team_meetings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_team_meetings_organizer_id'))
    op.drop_table('team_meetings')
    with op.batch_alter_table('agent_targets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agent_targets_agent_id'))
    op.drop_table('agent_targets')
