"""barcode bag tracking: bags + bag_scans

Revision ID: d4e5f6a7b8c1
Revises: c3d4e5f6a9b0
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c1"
down_revision = "c3d4e5f6a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bag_code", sa.String(length=40), nullable=False, unique=True, index=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False, index=True),
        sa.Column("farmer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("commodity_id", sa.Integer(), sa.ForeignKey("commodities.id"), nullable=True),
        sa.Column("bag_no", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="created", index=True),
        sa.Column("last_scan_at", sa.String(length=40), nullable=True),
        sa.Column("last_lat", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("last_lng", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_table(
        "bag_scans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bag_id", sa.Integer(), sa.ForeignKey("bags.id"), nullable=False, index=True),
        sa.Column("stage", sa.String(length=24), nullable=False),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("scanned_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("role", sa.String(length=24), nullable=True),
        sa.Column("lat", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("lng", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("corrected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("correction_reason", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("bag_scans")
    op.drop_table("bags")
