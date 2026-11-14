"""user passwords, structured name/email/avatar, address coordinates

Adds password + richer profile fields to users (for phone+password login and
role-based registration) and GPS coordinates to saved addresses.

Revision ID: f1a2b3c4d5e6
Revises: d4e5f6a7b8c9
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("first_name", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("last_name", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("email", sa.String(length=160), nullable=True))
        batch.add_column(sa.Column("password_hash", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("avatar_object_key", sa.String(length=300), nullable=True))
        batch.create_index("ix_users_email", ["email"])

    with op.batch_alter_table("saved_addresses") as batch:
        batch.add_column(sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True))
        batch.add_column(sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("saved_addresses") as batch:
        batch.drop_column("longitude")
        batch.drop_column("latitude")

    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_email")
        batch.drop_column("avatar_object_key")
        batch.drop_column("password_hash")
        batch.drop_column("email")
        batch.drop_column("last_name")
        batch.drop_column("first_name")
