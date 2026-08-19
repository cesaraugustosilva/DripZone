"""add admin session version

Revision ID: 20260819_0008
Revises: 20260819_0007
Create Date: 2026-08-19 17:59:31.777126
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260819_0008"
down_revision: Union[str, None] = "20260819_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("admin_users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("admin_users", "session_version")
