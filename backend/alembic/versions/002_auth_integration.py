"""auth service integration

Revision ID: 002_auth_integration
Revises: 001_initial
Create Date: 2026-05-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '002_auth_integration'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(20), nullable=True))
    op.create_index('ix_users_phone', 'users', ['phone'], unique=True)

    op.alter_column('users', 'email',
                    existing_type=sa.String(255),
                    nullable=True)

    op.drop_column('users', 'password_hash')


def downgrade() -> None:
    op.add_column('users', sa.Column('password_hash', sa.String(255), nullable=False))

    op.alter_column('users', 'email',
                    existing_type=sa.String(255),
                    nullable=False)

    op.drop_index('ix_users_phone', table_name='users')
    op.drop_column('users', 'phone')
