"""push_record_items + public_shares + public_likes + public_collects + tags extension

Revision ID: 003_push_tracking_and_public
Revises: 002_auth_integration
Create Date: 2026-05-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '003_push_tracking_and_public'
down_revision: Union[str, None] = '002_auth_integration'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'push_record_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('push_record_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('push_records.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('segment_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('segments.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pushed'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('push_record_id', 'segment_id'),
    )

    op.create_table(
        'public_shares',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, server_default=''),
        sa.Column('difficulty', sa.String(5)),
        sa.Column('category', sa.String(50)),
        sa.Column('duration_tier', sa.String(20)),
        sa.Column('cover_url', sa.String(500), server_default=''),
        sa.Column('play_count', sa.Integer, server_default='0'),
        sa.Column('like_count', sa.Integer, server_default='0'),
        sa.Column('collect_count', sa.Integer, server_default='0'),
        sa.Column('is_featured', sa.Boolean, server_default='false'),
        sa.Column('shared_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_public_shares_difficulty', 'public_shares', ['difficulty'])
    op.create_index('idx_public_shares_category', 'public_shares', ['category'])
    op.create_index('idx_public_shares_duration', 'public_shares', ['duration_tier'])
    op.create_index('idx_public_shares_featured', 'public_shares', ['is_featured'], postgresql_where=sa.text('is_featured = TRUE'))
    op.create_index('idx_public_shares_shared_at', 'public_shares', ['shared_at'])

    op.create_table(
        'public_likes',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('share_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('public_shares.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        'public_collects',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('share_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('public_shares.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('collection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('collections.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'share_id', 'collection_id'),
    )

    op.add_column('tags', sa.Column('is_system', sa.Boolean, server_default='false'))
    op.add_column('tags', sa.Column('tag_type', sa.String(20), server_default='custom'))


def downgrade() -> None:
    op.drop_column('tags', 'tag_type')
    op.drop_column('tags', 'is_system')

    op.drop_table('public_collects')
    op.drop_table('public_likes')
    op.drop_index('idx_public_shares_shared_at', table_name='public_shares')
    op.drop_index('idx_public_shares_featured', table_name='public_shares')
    op.drop_index('idx_public_shares_duration', table_name='public_shares')
    op.drop_index('idx_public_shares_category', table_name='public_shares')
    op.drop_index('idx_public_shares_difficulty', table_name='public_shares')
    op.drop_table('public_shares')
    op.drop_table('push_record_items')
