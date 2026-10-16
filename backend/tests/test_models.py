from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    AnkiPushConfig,
    BillingRecord,
    Collection,
    CollectionItem,
    EnginePricing,
    PublicCollect,
    PublicLike,
    PublicShare,
    PushRecord,
    PushRecordItem,
    Segment,
    Tag,
    Task,
    TaskTag,
    User,
)


class TestUserModel:
    def test_create_user(self, db_session):
        user = User(
            id=uuid4(),
            email="new@test.com",
            display_name="New User",
            role="user",
            credits=Decimal("50.00"),
            credits_reserved=Decimal("0.00"),
            allowed_engines=["local_whisper"],
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()

        result = db_session.execute(select(User).where(User.id == user.id))
        fetched = result.scalar_one()
        assert fetched.email == "new@test.com"
        assert fetched.credits == Decimal("50.00")

    def test_user_credits_default(self, db_session):
        user = User(id=uuid4(), email="default@test.com")
        db_session.add(user)
        db_session.commit()
        result = db_session.execute(select(User).where(User.id == user.id))
        fetched = result.scalar_one()
        assert fetched.credits == Decimal("0.00")
        assert fetched.credits_reserved == Decimal("0.00")

    def test_user_allowed_engines_default(self, db_session):
        user = User(id=uuid4(), email="engines@test.com")
        db_session.add(user)
        db_session.commit()
        result = db_session.execute(select(User).where(User.id == user.id))
        fetched = result.scalar_one()
        assert fetched.allowed_engines == ["local_whisper"]

    def test_user_role_default(self, db_session):
        user = User(id=uuid4(), email="role@test.com")
        db_session.add(user)
        db_session.commit()
        result = db_session.execute(select(User).where(User.id == user.id))
        fetched = result.scalar_one()
        assert fetched.role == "user"

    def test_user_is_active_default(self, db_session):
        user = User(id=uuid4(), email="active@test.com")
        db_session.add(user)
        db_session.commit()
        result = db_session.execute(select(User).where(User.id == user.id))
        fetched = result.scalar_one()
        assert fetched.is_active is True

    def test_user_relationships(self, db_session, sample_user, sample_task):
        user = db_session.execute(select(User).where(User.id == sample_user.id)).scalar_one()
        assert len(user.tasks) >= 1
        assert user.tasks[0].id == sample_task.id


class TestTaskModel:
    def test_create_task(self, db_session, sample_user):
        task = Task(
            user_id=sample_user.id,
            upload_name="new_task.mp3",
            file_hash="hash123",
            file_duration_sec=Decimal("120.00"),
            file_size_bytes=200000,
            engine="local_whisper",
            model_size="small",
            stage="pending",
            progress=Decimal("0.0"),
        )
        db_session.add(task)
        db_session.commit()

        result = db_session.execute(select(Task).where(Task.id == task.id))
        fetched = result.scalar_one()
        assert fetched.stage == "pending"
        assert fetched.is_public is False

    def test_task_defaults(self, db_session, sample_user):
        task = Task(user_id=sample_user.id, upload_name="defaults.mp3", file_hash="hash_default")
        db_session.add(task)
        db_session.commit()

        result = db_session.execute(select(Task).where(Task.id == task.id))
        fetched = result.scalar_one()
        assert fetched.engine == "local_whisper"
        assert fetched.model_size == "small"
        assert fetched.stage == "pending"
        assert fetched.progress == Decimal("0")
        assert fetched.credits_charged == Decimal("0")
        assert fetched.credits_reserved == Decimal("0")
        assert fetched.is_public is False

    def test_task_unique_user_file_hash(self, db_session, sample_user):
        task1 = Task(user_id=sample_user.id, upload_name="t1.mp3", file_hash="same_hash")
        db_session.add(task1)
        db_session.commit()

        task2 = Task(user_id=sample_user.id, upload_name="t2.mp3", file_hash="same_hash")
        db_session.add(task2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_task_different_users_same_hash(self, db_session, sample_user, sample_user2):
        task1 = Task(user_id=sample_user.id, upload_name="t1.mp3", file_hash="shared_hash")
        db_session.add(task1)
        db_session.commit()

        task2 = Task(user_id=sample_user2.id, upload_name="t2.mp3", file_hash="shared_hash")
        db_session.add(task2)
        db_session.commit()

    def test_reserve_reference_id_field(self, db_session, sample_user):
        task = Task(
            user_id=sample_user.id,
            upload_name="test.mp3",
            file_hash="ref_hash",
            reserve_reference_id="task:uuid:1234567890",
        )
        db_session.add(task)
        db_session.commit()

        result = db_session.execute(select(Task).where(Task.id == task.id))
        fetched = result.scalar_one()
        assert fetched.reserve_reference_id == "task:uuid:1234567890"

    def test_reserve_reference_id_nullable(self, db_session, sample_user):
        task = Task(
            user_id=sample_user.id,
            upload_name="test.mp3",
            file_hash="null_ref_hash",
            reserve_reference_id=None,
        )
        db_session.add(task)
        db_session.commit()

        result = db_session.execute(select(Task).where(Task.id == task.id))
        fetched = result.scalar_one()
        assert fetched.reserve_reference_id is None

    def test_task_relationships(self, db_session, sample_task, sample_segments):
        task = db_session.execute(select(Task).where(Task.id == sample_task.id)).scalar_one()
        assert len(task.segments) == 3
        assert task.user is not None


class TestSegmentModel:
    def test_create_segment(self, db_session, sample_task):
        seg = Segment(
            task_id=sample_task.id,
            seq_index=0,
            start_time=Decimal("0.0"),
            end_time=Decimal("10.0"),
            german_text="Hallo",
            chinese_text="你好",
            clip_path="clips/clip_001.mp3",
        )
        db_session.add(seg)
        db_session.commit()

        result = db_session.execute(select(Segment).where(Segment.id == seg.id))
        fetched = result.scalar_one()
        assert fetched.german_text == "Hallo"
        assert fetched.chinese_text == "你好"

    def test_segment_unique_task_seq(self, db_session, sample_task):
        seg1 = Segment(
            task_id=sample_task.id, seq_index=0,
            start_time=Decimal("0"), end_time=Decimal("10"),
            german_text="Text 1",
        )
        db_session.add(seg1)
        db_session.commit()

        seg2 = Segment(
            task_id=sample_task.id, seq_index=0,
            start_time=Decimal("10"), end_time=Decimal("20"),
            german_text="Text 2",
        )
        db_session.add(seg2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_segment_chinese_text_default(self, db_session, sample_task):
        seg = Segment(
            task_id=sample_task.id, seq_index=0,
            start_time=Decimal("0"), end_time=Decimal("10"),
            german_text="Text",
        )
        db_session.add(seg)
        db_session.commit()
        result = db_session.execute(select(Segment).where(Segment.id == seg.id))
        fetched = result.scalar_one()
        assert fetched.chinese_text == ""


class TestCollectionModel:
    def test_create_collection(self, db_session, sample_user):
        coll = Collection(
            user_id=sample_user.id,
            name="My Collection",
            description="Test desc",
        )
        db_session.add(coll)
        db_session.commit()

        result = db_session.execute(select(Collection).where(Collection.id == coll.id))
        fetched = result.scalar_one()
        assert fetched.name == "My Collection"
        assert fetched.description == "Test desc"

    def test_collection_default_description(self, db_session, sample_user):
        coll = Collection(user_id=sample_user.id, name="Minimal")
        db_session.add(coll)
        db_session.commit()
        result = db_session.execute(select(Collection).where(Collection.id == coll.id))
        fetched = result.scalar_one()
        assert fetched.description == ""


class TestCollectionItemModel:
    def test_create_item(self, db_session, sample_collection, sample_segments):
        item = CollectionItem(
            collection_id=sample_collection.id,
            segment_id=sample_segments[0].id,
            push_enabled=True,
        )
        db_session.add(item)
        db_session.commit()

        result = db_session.execute(select(CollectionItem).where(CollectionItem.id == item.id))
        fetched = result.scalar_one()
        assert fetched.push_enabled is True

    def test_item_default_push_enabled(self, db_session, sample_collection, sample_segments):
        item = CollectionItem(
            collection_id=sample_collection.id,
            segment_id=sample_segments[1].id,
        )
        db_session.add(item)
        db_session.commit()
        result = db_session.execute(select(CollectionItem).where(CollectionItem.id == item.id))
        fetched = result.scalar_one()
        assert fetched.push_enabled is True

    def test_item_unique_collection_segment(self, db_session, sample_collection, sample_segments):
        item1 = CollectionItem(
            collection_id=sample_collection.id,
            segment_id=sample_segments[0].id,
        )
        db_session.add(item1)
        db_session.commit()

        item2 = CollectionItem(
            collection_id=sample_collection.id,
            segment_id=sample_segments[0].id,
        )
        db_session.add(item2)
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestTagModel:
    def test_create_tag(self, db_session, sample_user):
        tag = Tag(
            user_id=sample_user.id,
            name="test-tag",
            color="#00FF00",
            is_system=False,
            tag_type="custom",
        )
        db_session.add(tag)
        db_session.commit()

        result = db_session.execute(select(Tag).where(Tag.id == tag.id))
        fetched = result.scalar_one()
        assert fetched.name == "test-tag"
        assert fetched.color == "#00FF00"

    def test_tag_unique_user_name(self, db_session, sample_user):
        tag1 = Tag(user_id=sample_user.id, name="duplicate")
        db_session.add(tag1)
        db_session.commit()

        tag2 = Tag(user_id=sample_user.id, name="duplicate")
        db_session.add(tag2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_tag_different_users_same_name(self, db_session, sample_user, sample_user2):
        tag1 = Tag(user_id=sample_user.id, name="shared_name")
        db_session.add(tag1)
        db_session.commit()

        tag2 = Tag(user_id=sample_user2.id, name="shared_name")
        db_session.add(tag2)
        db_session.commit()


class TestTaskTagModel:
    def test_create_task_tag(self, db_session, sample_task, sample_tag):
        tt = TaskTag(task_id=sample_task.id, tag_id=sample_tag.id)
        db_session.add(tt)
        db_session.commit()

        result = db_session.execute(select(TaskTag).where(
            TaskTag.task_id == sample_task.id, TaskTag.tag_id == sample_tag.id
        ))
        assert result.scalar_one() is not None


class TestBillingRecordModel:
    def test_create_record(self, db_session, sample_user):
        record = BillingRecord(
            user_id=sample_user.id,
            task_id=None,
            action="topup",
            amount=Decimal("100.00"),
            balance_after=Decimal("200.00"),
            description="充值",
        )
        db_session.add(record)
        db_session.commit()

        result = db_session.execute(select(BillingRecord).where(BillingRecord.id == record.id))
        fetched = result.scalar_one()
        assert fetched.action == "topup"
        assert fetched.amount == Decimal("100.00")


class TestEnginePricingModel:
    def test_create_pricing(self, db_session):
        pricing = EnginePricing(
            engine_key="test_engine",
            model_size="default",
            engine_name="Test Engine",
            credits_per_minute=Decimal("2.5"),
            is_active=True,
        )
        db_session.add(pricing)
        db_session.commit()

        result = db_session.execute(select(EnginePricing).where(
            EnginePricing.engine_key == "test_engine",
            EnginePricing.model_size == "default",
        ))
        fetched = result.scalar_one()
        assert fetched.credits_per_minute == Decimal("2.5")


class TestAnkiPushConfigModel:
    def test_create_config(self, db_session, sample_user):
        config = AnkiPushConfig(
            user_id=sample_user.id,
            push_mode="sync_client",
            is_default=True,
            sync_endpoint="http://localhost:8080",
            deck_name="Deutsch",
            note_type="Basic",
        )
        db_session.add(config)
        db_session.commit()

        result = db_session.execute(select(AnkiPushConfig).where(AnkiPushConfig.id == config.id))
        fetched = result.scalar_one()
        assert fetched.push_mode == "sync_client"
        assert fetched.deck_name == "Deutsch"


class TestPushRecordModel:
    def test_create_record(self, db_session, sample_user):
        record = PushRecord(
            user_id=sample_user.id,
            task_id=None,
            push_mode="sync_client",
            deck_name="Deutsch",
            card_count=5,
            status="success",
        )
        db_session.add(record)
        db_session.commit()

        result = db_session.execute(select(PushRecord).where(PushRecord.id == record.id))
        fetched = result.scalar_one()
        assert fetched.card_count == 5
        assert fetched.status == "success"

    def test_push_record_defaults(self, db_session, sample_user):
        record = PushRecord(
            user_id=sample_user.id,
            push_mode="sync_client",
            deck_name="Deutsch",
        )
        db_session.add(record)
        db_session.commit()

        result = db_session.execute(select(PushRecord).where(PushRecord.id == record.id))
        fetched = result.scalar_one()
        assert fetched.card_count is None
        assert fetched.skipped_count == 0
        assert fetched.status == "success"


class TestPushRecordItemModel:
    def test_create_item(self, db_session, sample_user, sample_segments):
        record = PushRecord(
            user_id=sample_user.id,
            push_mode="sync_client",
            deck_name="Deutsch",
        )
        db_session.add(record)
        db_session.commit()

        item = PushRecordItem(
            push_record_id=record.id,
            segment_id=sample_segments[0].id,
            status="pushed",
        )
        db_session.add(item)
        db_session.commit()

        result = db_session.execute(select(PushRecordItem).where(PushRecordItem.id == item.id))
        fetched = result.scalar_one()
        assert fetched.status == "pushed"


class TestPublicShareModel:
    def test_create_share(self, db_session, sample_user, sample_task):
        share = PublicShare(
            task_id=sample_task.id,
            user_id=sample_user.id,
            title="Public Share",
            description="A public share",
            difficulty="B1",
            category="podcast",
        )
        db_session.add(share)
        db_session.commit()

        result = db_session.execute(select(PublicShare).where(PublicShare.id == share.id))
        fetched = result.scalar_one()
        assert fetched.title == "Public Share"
        assert fetched.play_count == 0
        assert fetched.like_count == 0
        assert fetched.collect_count == 0
        assert fetched.is_featured is False


class TestPublicLikeModel:
    def test_create_like(self, db_session, sample_user, sample_task):
        share = PublicShare(
            task_id=sample_task.id,
            user_id=sample_user.id,
            title="Test Share",
        )
        db_session.add(share)
        db_session.commit()

        like = PublicLike(user_id=sample_user.id, share_id=share.id)
        db_session.add(like)
        db_session.commit()

        result = db_session.execute(select(PublicLike).where(
            PublicLike.user_id == sample_user.id,
            PublicLike.share_id == share.id,
        ))
        assert result.scalar_one() is not None


class TestPublicCollectModel:
    def test_create_collect(self, db_session, sample_user, sample_task, sample_collection):
        share = PublicShare(
            task_id=sample_task.id,
            user_id=sample_user.id,
            title="Test Share",
        )
        db_session.add(share)
        db_session.commit()

        collect = PublicCollect(
            user_id=sample_user.id,
            share_id=share.id,
            collection_id=sample_collection.id,
        )
        db_session.add(collect)
        db_session.commit()

        result = db_session.execute(select(PublicCollect).where(PublicCollect.id == collect.id))
        assert result.scalar_one() is not None