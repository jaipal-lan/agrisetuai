"""RFQ needed-by date

Adds a "needed by" delivery date (calendar-picked) to buyer requests.

Revision ID: c3d4e5f6a9b0
Revises: b2c3d4e5f6a8
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a9b0"
down_revision = "b2c3d4e5f6a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("rfqs") as batch:
        batch.add_column(sa.Column("needed_by", sa.String(length=10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("rfqs") as batch:
        batch.drop_column("needed_by")
