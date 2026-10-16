import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=True, index=True)
    phone = Column(String(20), unique=True, nullable=True, index=True)
    display_name = Column(String(100))
    role = Column(String(20), default="user", nullable=False)
    credits = Column(Numeric(10, 2), default=0, nullable=False)
    credits_reserved = Column(Numeric(10, 2), default=0, nullable=False)
    allowed_engines = Column(ARRAY(Text), default=["local_whisper"])
    max_push_configs = Column(Integer, default=4, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tasks = relationship("Task", back_populates="user", lazy="selectin")
    collections = relationship("Collection", back_populates="user", lazy="selectin")
    tags = relationship("Tag", back_populates="user", lazy="selectin")
    billing_records = relationship("BillingRecord", back_populates="user", lazy="selectin")
    push_configs = relationship("AnkiPushConfig", back_populates="user", lazy="selectin")


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, default="")
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class EnginePricing(Base):
    __tablename__ = "engine_pricing"

    engine_key = Column(String(30), primary_key=True)
    model_size = Column(String(30), primary_key=True, default="default")
    engine_name = Column(String(100), nullable=False)
    credits_per_minute = Column(Numeric(10, 4), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    description = Column(Text, default="")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    upload_name = Column(String(500), nullable=False)
    title = Column(String(200), default="")
    difficulty = Column(String(5), default="")
    category = Column(String(20), default="")
    file_hash = Column(String(64), nullable=False)
    file_duration_sec = Column(Numeric(10, 2))
    file_size_bytes = Column(BigInteger)
    engine = Column(String(30), default="local_whisper", nullable=False)
    model_size = Column(String(20), default="small")
    stage = Column(String(20), default="pending", nullable=False, index=True)
    progress = Column(Numeric(5, 4), default=0, nullable=False)
    stage_message = Column(Text, default="")
    error = Column(Text, default="")
    source_path = Column(String(500))
    normalized_path = Column(String(500))
    clips_dir = Column(String(500))
    segment_count = Column(Integer, default=0)
    transcription_text = Column(Text, default="")
    credits_charged = Column(Numeric(10, 2), default=0)
    credits_reserved = Column(Numeric(10, 2), default=0)
    reserve_reference_id = Column(String(200))
    is_public = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))

    user = relationship("User", back_populates="tasks")
    segments = relationship("Segment", back_populates="task", cascade="all, delete-orphan", lazy="selectin")
    task_tags = relationship("TaskTag", back_populates="task", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (UniqueConstraint("user_id", "file_hash", "engine"),)


class Segment(Base):
    __tablename__ = "segments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    seq_index = Column(Integer, nullable=False)
    start_time = Column(Numeric(8, 3), nullable=False)
    end_time = Column(Numeric(8, 3), nullable=False)
    german_text = Column(Text, nullable=False)
    chinese_text = Column(Text, default="")
    clip_path = Column(String(500))

    task = relationship("Task", back_populates="segments")

    __table_args__ = (UniqueConstraint("task_id", "seq_index"),)


class Collection(Base):
    __tablename__ = "collections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="collections")
    items = relationship("CollectionItem", back_populates="collection", cascade="all, delete-orphan", lazy="selectin")


class CollectionItem(Base):
    __tablename__ = "collection_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id = Column(UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_id = Column(UUID(as_uuid=True), ForeignKey("segments.id"), nullable=False, index=True)
    push_enabled = Column(Boolean, default=True, nullable=False)
    added_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    collection = relationship("Collection", back_populates="items")
    segment = relationship("Segment", lazy="selectin")

    __table_args__ = (UniqueConstraint("collection_id", "segment_id"),)


class Tag(Base):
    __tablename__ = "tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    color = Column(String(7), default="#4A90D9")
    is_system = Column(Boolean, default=False)
    tag_type = Column(String(20), default="custom")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="tags")

    __table_args__ = (UniqueConstraint("user_id", "name"),)


class TaskTag(Base):
    __tablename__ = "task_tags"

    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

    task = relationship("Task", back_populates="task_tags")
    tag = relationship("Tag", lazy="selectin")


class BillingRecord(Base):
    __tablename__ = "billing_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), index=True)
    action = Column(String(30), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    balance_after = Column(Numeric(10, 2), nullable=False)
    duration_sec = Column(Numeric(10, 2))
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="billing_records")


class AnkiPushConfig(Base):
    __tablename__ = "anki_push_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), default="")
    push_mode = Column(String(20), nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    sync_endpoint = Column(String(500))
    sync_username = Column(String(200))
    sync_password_enc = Column(String(500))
    ankiweb_username = Column(String(200))
    ankiweb_password_enc = Column(String(500))
    deck_name = Column(String(200), default="Deutsch Listening")
    note_type = Column(String(100), default="Basic")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="push_configs")


class PushRecord(Base):
    __tablename__ = "push_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), index=True)
    collection_id = Column(UUID(as_uuid=True), ForeignKey("collections.id"))
    config_id = Column(UUID(as_uuid=True), ForeignKey("anki_push_configs.id"))
    push_mode = Column(String(20), nullable=False)
    deck_name = Column(String(200))
    card_count = Column(Integer)
    skipped_count = Column(Integer, default=0)
    status = Column(String(20), default="success", nullable=False)
    error_message = Column(Text, default="")
    duration_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    items = relationship("PushRecordItem", back_populates="push_record", cascade="all, delete-orphan", lazy="selectin")


class PushRecordItem(Base):
    __tablename__ = "push_record_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    push_record_id = Column(UUID(as_uuid=True), ForeignKey("push_records.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_id = Column(UUID(as_uuid=True), ForeignKey("segments.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), default="pushed", nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    push_record = relationship("PushRecord", back_populates="items")
    segment = relationship("Segment", lazy="selectin")

    __table_args__ = (UniqueConstraint("push_record_id", "segment_id"),)


class PublicShare(Base):
    __tablename__ = "public_shares"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    difficulty = Column(String(5))
    category = Column(String(50))
    duration_tier = Column(String(20))
    cover_url = Column(String(500), default="")
    play_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    collect_count = Column(Integer, default=0)
    is_featured = Column(Boolean, default=False)
    shared_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    task = relationship("Task", lazy="selectin")
    user_rel = relationship("User", lazy="selectin")
    likes = relationship("PublicLike", back_populates="share", cascade="all, delete-orphan", lazy="selectin")
    collects = relationship("PublicCollect", back_populates="share", cascade="all, delete-orphan", lazy="selectin")


class PublicLike(Base):
    __tablename__ = "public_likes"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    share_id = Column(UUID(as_uuid=True), ForeignKey("public_shares.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    share = relationship("PublicShare", back_populates="likes")


class PublicCollect(Base):
    __tablename__ = "public_collects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    share_id = Column(UUID(as_uuid=True), ForeignKey("public_shares.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_id = Column(UUID(as_uuid=True), ForeignKey("collections.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    share = relationship("PublicShare", back_populates="collects")

    __table_args__ = (UniqueConstraint("user_id", "share_id", "collection_id"),)


class EmailVerificationCode(Base):
    __tablename__ = "email_verification_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, index=True)
    code = Column(String(6), nullable=False)
    purpose = Column(String(30), nullable=False, index=True)
    is_used = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("email", "purpose", "code"),)


class RechargeRequest(Base):
    __tablename__ = "recharge_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    credits_amount = Column(Numeric(10, 2), nullable=False)
    coefficient = Column(Numeric(10, 2), default=10, nullable=False)
    payment_image = Column(String(500), nullable=False)
    image_hash = Column(String(64))
    status = Column(String(20), default="pending", nullable=False, index=True)
    admin_note = Column(Text, default="")
    reviewed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", lazy="selectin")


class HelpArticle(Base):
    __tablename__ = "help_articles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(100), unique=True, nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False, default="")
    category = Column(String(50), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_published = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SegmentRating(Base):
    __tablename__ = "segment_ratings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    segment_id = Column(UUID(as_uuid=True), ForeignKey("segments.id", ondelete="CASCADE"), nullable=False, index=True)
    rating = Column(String(10), nullable=False)
    is_collected = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "segment_id"),)


class Transcription(Base):
    __tablename__ = "transcriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    language = Column(String(5), default="de", nullable=False)
    status = Column(String(20), default="pending", nullable=False, index=True)
    text = Column(Text, default="")
    error_message = Column(Text, default="")
    file_size = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", lazy="selectin")
