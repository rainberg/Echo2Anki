"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-05-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(100)),
        sa.Column('role', sa.String(20), nullable=False, server_default='user'),
        sa.Column('credits', sa.Numeric(10, 2), nullable=False, server_default='0'),
        sa.Column('credits_reserved', sa.Numeric(10, 2), nullable=False, server_default='0'),
        sa.Column('allowed_engines', postgresql.ARRAY(sa.Text), server_default="ARRAY['local_whisper']::text[]"),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        'engine_pricing',
        sa.Column('engine_key', sa.String(30), primary_key=True),
        sa.Column('model_size', sa.String(30), primary_key=True, server_default='default'),
        sa.Column('engine_name', sa.String(100), nullable=False),
        sa.Column('credits_per_minute', sa.Numeric(10, 4), nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('sort_order', sa.Integer, nullable=False, server_default='0'),
        sa.Column('description', sa.Text, server_default=''),
    )

    op.create_table(
        'tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('upload_name', sa.String(500), nullable=False),
        sa.Column('file_hash', sa.String(64), nullable=False),
        sa.Column('file_duration_sec', sa.Numeric(10, 2)),
        sa.Column('file_size_bytes', sa.BigInteger),
        sa.Column('engine', sa.String(30), nullable=False, server_default='local_whisper'),
        sa.Column('model_size', sa.String(20), server_default='small'),
        sa.Column('stage', sa.String(20), nullable=False, server_default='pending', index=True),
        sa.Column('progress', sa.Numeric(5, 4), nullable=False, server_default='0'),
        sa.Column('stage_message', sa.Text, server_default=''),
        sa.Column('error', sa.Text, server_default=''),
        sa.Column('source_path', sa.String(500)),
        sa.Column('normalized_path', sa.String(500)),
        sa.Column('clips_dir', sa.String(500)),
        sa.Column('segment_count', sa.Integer, server_default='0'),
        sa.Column('credits_charged', sa.Numeric(10, 2), server_default='0'),
        sa.Column('credits_reserved', sa.Numeric(10, 2), server_default='0'),
        sa.Column('is_public', sa.Boolean, nullable=False, server_default='false', index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('user_id', 'file_hash'),
    )

    op.create_table(
        'segments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('seq_index', sa.Integer, nullable=False),
        sa.Column('start_time', sa.Numeric(8, 3), nullable=False),
        sa.Column('end_time', sa.Numeric(8, 3), nullable=False),
        sa.Column('german_text', sa.Text, nullable=False),
        sa.Column('chinese_text', sa.Text, server_default=''),
        sa.Column('clip_path', sa.String(500)),
        sa.UniqueConstraint('task_id', 'seq_index'),
    )

    op.create_index('idx_segments_german_trgm', 'segments', ['german_text'], postgresql_using='gin', postgresql_ops={'german_text': 'gin_trgm_ops'})
    op.create_index('idx_segments_chinese_trgm', 'segments', ['chinese_text'], postgresql_using='gin', postgresql_ops={'chinese_text': 'gin_trgm_ops'})

    op.create_table(
        'collections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        'collection_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('collection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('collections.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('segment_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('segments.id'), nullable=False, index=True),
        sa.Column('push_enabled', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('added_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('collection_id', 'segment_id'),
    )

    op.create_table(
        'tags',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('color', sa.String(7), server_default='#4A90D9'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'name'),
    )

    op.create_table(
        'task_tags',
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('tag_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
    )

    op.create_table(
        'billing_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id'), index=True),
        sa.Column('action', sa.String(30), nullable=False),
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('balance_after', sa.Numeric(10, 2), nullable=False),
        sa.Column('duration_sec', sa.Numeric(10, 2)),
        sa.Column('description', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
    )

    op.create_table(
        'anki_push_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('push_mode', sa.String(20), nullable=False),
        sa.Column('is_default', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('sync_endpoint', sa.String(500)),
        sa.Column('sync_username', sa.String(200)),
        sa.Column('sync_password_enc', sa.String(500)),
        sa.Column('ankiweb_username', sa.String(200)),
        sa.Column('ankiweb_password_enc', sa.String(500)),
        sa.Column('deck_name', sa.String(200), server_default='Deutsch Listening'),
        sa.Column('note_type', sa.String(100), server_default='Basic'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'push_mode'),
    )

    op.create_table(
        'push_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id'), nullable=False, index=True),
        sa.Column('collection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('collections.id')),
        sa.Column('config_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('anki_push_configs.id')),
        sa.Column('push_mode', sa.String(20), nullable=False),
        sa.Column('deck_name', sa.String(200)),
        sa.Column('card_count', sa.Integer),
        sa.Column('skipped_count', sa.Integer, server_default='0'),
        sa.Column('status', sa.String(20), nullable=False, server_default='success'),
        sa.Column('error_message', sa.Text, server_default=''),
        sa.Column('duration_ms', sa.Integer),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('push_records')
    op.drop_table('anki_push_configs')
    op.drop_table('billing_records')
    op.drop_table('task_tags')
    op.drop_table('tags')
    op.drop_table('collection_items')
    op.drop_table('collections')
    op.drop_index('idx_segments_chinese_trgm', table_name='segments')
    op.drop_index('idx_segments_german_trgm', table_name='segments')
    op.drop_table('segments')
    op.drop_table('tasks')
    op.drop_table('engine_pricing')
    op.drop_table('users')
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
