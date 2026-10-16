"""Add reserve_reference_id to tasks

Revision ID: 004_reserve_reference_id
Revises: 003_push_tracking_and_public
Create Date: 2026-05-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '004_reserve_reference_id'
down_revision: Union[str, None] = '003_push_tracking_and_public'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('reserve_reference_id', sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'reserve_reference_id')
