"""users: id_documents (government photo-ID proofs for identity verification)

Revision ID: d7e9f1a3b5c2
Revises: f6a7b8c2d3e4
Create Date: 2026-11-17 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e9f1a3b5c2'
down_revision: Union[str, None] = 'f6a7b8c2d3e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('id_documents', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('id_documents')
