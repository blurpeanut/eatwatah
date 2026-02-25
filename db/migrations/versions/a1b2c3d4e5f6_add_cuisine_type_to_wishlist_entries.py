"""add cuisine_type to wishlist_entries

Revision ID: a1b2c3d4e5f6
Revises: 6bdbb6e90998
Create Date: 2026-02-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "6bdbb6e90998"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "wishlist_entries",
        sa.Column("cuisine_type", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wishlist_entries", "cuisine_type")
