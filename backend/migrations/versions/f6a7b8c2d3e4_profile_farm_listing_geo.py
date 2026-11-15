"""user address+KYC fields, farmer profile fields, listing geo pin

Revision ID: f6a7b8c2d3e4
Revises: e5f6a7b8c2d3
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = "f6a7b8c2d3e4"
down_revision = "e5f6a7b8c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("district", sa.String(length=80), nullable=True))
        b.add_column(sa.Column("state", sa.String(length=80), nullable=True))
        b.add_column(sa.Column("pincode", sa.String(length=10), nullable=True))
        b.add_column(sa.Column("aadhaar", sa.String(length=20), nullable=True))
        b.add_column(sa.Column("pan", sa.String(length=20), nullable=True))
    with op.batch_alter_table("farmer_profiles") as b:
        b.add_column(sa.Column("farm_size", sa.Numeric(precision=10, scale=2), nullable=True))
        b.add_column(sa.Column("crops_grown", sa.JSON(), nullable=True))
        b.add_column(sa.Column("soil_type", sa.String(length=40), nullable=True))
        b.add_column(sa.Column("irrigation_type", sa.String(length=40), nullable=True))
        b.add_column(sa.Column("experience_years", sa.Integer(), nullable=True))
    with op.batch_alter_table("listings") as b:
        b.add_column(sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True))
        b.add_column(sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("listings") as b:
        b.drop_column("longitude")
        b.drop_column("latitude")
    with op.batch_alter_table("farmer_profiles") as b:
        b.drop_column("experience_years")
        b.drop_column("irrigation_type")
        b.drop_column("soil_type")
        b.drop_column("crops_grown")
        b.drop_column("farm_size")
    with op.batch_alter_table("users") as b:
        b.drop_column("pan")
        b.drop_column("aadhaar")
        b.drop_column("pincode")
        b.drop_column("state")
        b.drop_column("district")
