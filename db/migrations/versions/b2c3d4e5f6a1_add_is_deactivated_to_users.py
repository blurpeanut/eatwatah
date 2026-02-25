"""Add is_deactivated to users

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-02-25

Adds a reversible account-pause flag to the Users table.
Separate from is_deleted — do not combine or confuse.
"""
from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a1"
down_revision: str = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_deactivated",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_deactivated")
