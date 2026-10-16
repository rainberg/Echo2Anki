from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.schemas import (
    AdminTopup,
    AdminUpdateEngines,
    AdminUpdateStatus,
    AdminUserListResponse,
    AdminUserResponse,
    BillingBalance,
    BillingRecordListResponse,
    BillingRecordResponse,
    CollectionCreate,
    CollectionItemAdd,
    CollectionItemToggle,
    CollectionResponse,
    CollectionUpdate,
    EngineInfo,
    PublicShareCreate,
    PublicShareResponse,
    PublicShareUpdate,
    SegmentResponse,
    SegmentUpdate,
    SystemHealth,
    TagCreate,
    TagResponse,
    TaskCreate,
    TaskDetailResponse,
    TaskListResponse,
    TaskResponse,
    TaskRetry,
    TaskUpdate,
    UserResponse,
)


class TestUserResponse:
    def test_valid_user(self):
        data = {
            "id": str(uuid4()),
            "email": "test@example.com",
            "display_name": "Test User",
            "role": "user",
            "credits": "100.00",
            "allowed_engines": ["local_whisper"],
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        user = UserResponse(**data)
        assert user.email == "test@example.com"
        assert user.credits == Decimal("100.00")

    def test_optional_email(self):
        data = {
            "id": str(uuid4()),
            "email": None,
            "display_name": "Test User",
            "role": "user",
            "credits": "100.00",
            "allowed_engines": ["local_whisper"],
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        user = UserResponse(**data)
        assert user.email is None

    def test_optional_phone(self):
        data = {
            "id": str(uuid4()),
            "email": "test@example.com",
            "phone": None,
            "display_name": "Test User",
            "role": "user",
            "credits": "100.00",
            "allowed_engines": ["local_whisper"],
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        user = UserResponse(**data)
        assert user.phone is None


class TestAdminTopup:
    def test_valid_topup(self):
        topup = AdminTopup(amount=Decimal("50.00"))
        assert topup.amount == Decimal("50.00")

    def test_zero_amount_rejected(self):
        with pytest.raises(ValidationError):
            AdminTopup(amount=Decimal("0.00"))

    def test_negative_amount_rejected(self):
        with pytest.raises(ValidationError):
            AdminTopup(amount=Decimal("-10.00"))

    def test_optional_description(self):
        topup = AdminTopup(amount=Decimal("50.00"), description="充值")
        assert topup.description == "充值"

    def test_no_description(self):
        topup = AdminTopup(amount=Decimal("50.00"))
        assert topup.description is None


class TestAdminUpdateEngines:
    def test_valid_engines(self):
        update = AdminUpdateEngines(allowed_engines=["local_whisper", "openai_whisper"])
        assert len(update.allowed_engines) == 2

    def test_empty_engines(self):
        update = AdminUpdateEngines(allowed_engines=[])
        assert update.allowed_engines == []

    def test_missing_engines(self):
        with pytest.raises(ValidationError):
            AdminUpdateEngines()


class TestAdminUpdateStatus:
    def test_active(self):
        update = AdminUpdateStatus(is_active=True)
        assert update.is_active is True

    def test_inactive(self):
        update = AdminUpdateStatus(is_active=False)
        assert update.is_active is False


class TestTaskCreate:
    def test_default_values(self):
        task = TaskCreate()
        assert task.engine == "local_whisper"
        assert task.model_size == "small"
        assert task.api_key is None

    def test_custom_values(self):
        task = TaskCreate(engine="openai_whisper", model_size="whisper-1", api_key="sk-123")
        assert task.engine == "openai_whisper"
        assert task.model_size == "whisper-1"
        assert task.api_key == "sk-123"


class TestTaskRetry:
    def test_empty(self):
        retry = TaskRetry()
        assert retry.engine is None
        assert retry.model_size is None
        assert retry.api_key is None

    def test_with_values(self):
        retry = TaskRetry(engine="openai_whisper", model_size="whisper-1", api_key="sk-abc")
        assert retry.engine == "openai_whisper"
        assert retry.model_size == "whisper-1"


class TestTaskResponse:
    def test_valid_response(self):
        data = {
            "id": str(uuid4()),
            "user_id": str(uuid4()),
            "upload_name": "test.mp3",
            "file_hash": "abc123",
            "file_duration_sec": "60.00",
            "file_size_bytes": 100000,
            "engine": "local_whisper",
            "model_size": "small",
            "stage": "done",
            "progress": "1.0",
            "stage_message": "",
            "error": "",
            "segment_count": 3,
            "credits_charged": "1.00",
            "credits_reserved": "0.00",
            "is_public": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "finished_at": None,
        }
        task = TaskResponse(**data)
        assert task.stage == "done"
        assert task.credits_charged == Decimal("1.00")

    def test_optional_datetime_fields(self):
        data = {
            "id": str(uuid4()),
            "user_id": str(uuid4()),
            "upload_name": "test.mp3",
            "file_hash": "abc123",
            "file_duration_sec": None,
            "file_size_bytes": None,
            "engine": "local_whisper",
            "model_size": "small",
            "stage": "pending",
            "progress": "0.0",
            "stage_message": "",
            "error": "",
            "segment_count": 0,
            "credits_charged": "0.00",
            "credits_reserved": "0.00",
            "is_public": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "finished_at": None,
        }
        task = TaskResponse(**data)
        assert task.file_duration_sec is None
        assert task.file_size_bytes is None


class TestSegmentResponse:
    def test_valid_response(self):
        data = {
            "id": str(uuid4()),
            "task_id": str(uuid4()),
            "seq_index": 0,
            "start_time": "0.0",
            "end_time": "10.0",
            "german_text": "Hallo Welt",
            "chinese_text": "你好世界",
            "clip_path": "clips/clip_001.mp3",
            "collected": False,
            "pushed": False,
            "last_pushed_at": None,
        }
        seg = SegmentResponse(**data)
        assert seg.german_text == "Hallo Welt"
        assert seg.collected is False


class TestSegmentUpdate:
    def test_update_chinese(self):
        update = SegmentUpdate(chinese_text="新翻译")
        assert update.chinese_text == "新翻译"
        assert update.german_text is None

    def test_update_german(self):
        update = SegmentUpdate(german_text="Neuer Text")
        assert update.german_text == "Neuer Text"
        assert update.chinese_text is None

    def test_update_both(self):
        update = SegmentUpdate(chinese_text="新翻译", german_text="Neuer Text")
        assert update.chinese_text == "新翻译"
        assert update.german_text == "Neuer Text"

    def test_empty_update(self):
        update = SegmentUpdate()
        assert update.chinese_text is None
        assert update.german_text is None


class TestCollectionCreate:
    def test_valid(self):
        coll = CollectionCreate(name="My Collection", description="Test")
        assert coll.name == "My Collection"

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            CollectionCreate(name="")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            CollectionCreate(name="A" * 201)

    def test_name_exactly_min_length(self):
        coll = CollectionCreate(name="A")
        assert coll.name == "A"

    def test_name_exactly_max_length(self):
        coll = CollectionCreate(name="A" * 200)
        assert len(coll.name) == 200


class TestCollectionUpdate:
    def test_update_name(self):
        update = CollectionUpdate(name="New Name")
        assert update.name == "New Name"

    def test_update_description(self):
        update = CollectionUpdate(description="New desc")
        assert update.description == "New desc"

    def test_empty_update(self):
        update = CollectionUpdate()
        assert update.name is None
        assert update.description is None


class TestCollectionItemAdd:
    def test_valid(self):
        seg_ids = [uuid4(), uuid4()]
        add = CollectionItemAdd(segment_ids=seg_ids)
        assert len(add.segment_ids) == 2

    def test_empty_list(self):
        add = CollectionItemAdd(segment_ids=[])
        assert add.segment_ids == []


class TestCollectionItemToggle:
    def test_enable(self):
        toggle = CollectionItemToggle(push_enabled=True)
        assert toggle.push_enabled is True

    def test_disable(self):
        toggle = CollectionItemToggle(push_enabled=False)
        assert toggle.push_enabled is False


class TestTagCreate:
    def test_valid(self):
        tag = TagCreate(name="my-tag", color="#FF0000")
        assert tag.name == "my-tag"
        assert tag.color == "#FF0000"

    def test_default_color(self):
        tag = TagCreate(name="my-tag")
        assert tag.color == "#4A90D9"

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            TagCreate(name="")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            TagCreate(name="A" * 101)


class TestPublicShareCreate:
    def test_valid(self):
        share = PublicShareCreate(
            task_id=uuid4(),
            title="My Share",
            description="A public share",
            difficulty="B1",
            category="podcast",
            tag_ids=[],
        )
        assert share.title == "My Share"

    def test_defaults(self):
        share = PublicShareCreate(task_id=uuid4())
        assert share.title is None
        assert share.description == ""
        assert share.tag_ids == []


class TestPublicShareUpdate:
    def test_all_fields(self):
        update = PublicShareUpdate(
            title="New Title",
            description="New desc",
            difficulty="B2",
            category="news",
            tag_ids=[uuid4()],
        )
        assert update.title == "New Title"
        assert update.difficulty == "B2"

    def test_partial_update(self):
        update = PublicShareUpdate(title="New Title")
        assert update.title == "New Title"
        assert update.description is None

    def test_empty_update(self):
        update = PublicShareUpdate()
        assert update.title is None


class TestBillingBalance:
    def test_valid(self):
        balance = BillingBalance(
            credits=Decimal("100.00"),
            total_used=Decimal("50.00"),
            total_tasks=10,
            total_duration_sec=Decimal("600.00"),
        )
        assert balance.credits == Decimal("100.00")

    def test_zero_values(self):
        balance = BillingBalance(
            credits=Decimal("0.00"),
            total_used=Decimal("0.00"),
            total_tasks=0,
            total_duration_sec=Decimal("0.00"),
        )
        assert balance.total_tasks == 0


class TestBillingRecordResponse:
    def test_valid(self):
        record = BillingRecordResponse(
            id=uuid4(),
            action="reserve",
            amount=Decimal("-1.00"),
            balance_after=Decimal("99.00"),
            duration_sec=Decimal("60.00"),
            description="预扣",
            created_at=datetime.now(timezone.utc),
        )
        assert record.action == "reserve"

    def test_optional_duration(self):
        record = BillingRecordResponse(
            id=uuid4(),
            action="topup",
            amount=Decimal("100.00"),
            balance_after=Decimal("200.00"),
            duration_sec=None,
            description="充值",
            created_at=datetime.now(timezone.utc),
        )
        assert record.duration_sec is None


class TestSystemHealth:
    def test_valid(self):
        health = SystemHealth(status="ok", version="2.0.0")
        assert health.status == "ok"
        assert health.version == "2.0.0"


class TestEngineInfo:
    def test_valid(self):
        engine = EngineInfo(
            engine_key="local_whisper",
            engine_name="Local Whisper",
            credits_per_minute=Decimal("1.0"),
            model_sizes=["tiny", "small"],
        )
        assert engine.engine_key == "local_whisper"

    def test_optional_model_sizes(self):
        engine = EngineInfo(
            engine_key="local_whisper",
            engine_name="Local Whisper",
            credits_per_minute=Decimal("1.0"),
        )
        assert engine.model_sizes is None


class TestTaskUpdate:
    def test_set_public(self):
        update = TaskUpdate(is_public=True)
        assert update.is_public is True

    def test_set_private(self):
        update = TaskUpdate(is_public=False)
        assert update.is_public is False

    def test_no_change(self):
        update = TaskUpdate()
        assert update.is_public is None


class TestAdminUserResponse:
    def test_valid(self):
        data = {
            "id": str(uuid4()),
            "email": "admin@example.com",
            "display_name": "Admin",
            "role": "admin",
            "credits": "999.00",
            "allowed_engines": ["local_whisper", "openai_whisper"],
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        user = AdminUserResponse(**data)
        assert user.role == "admin"
        assert user.updated_at is not None


class TestAdminUserListResponse:
    def test_valid(self):
        user = AdminUserResponse(
            id=uuid4(),
            email="test@example.com",
            display_name="Test",
            role="user",
            credits="50.00",
            allowed_engines=["local_whisper"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        response = AdminUserListResponse(items=[user], total=1, page=1, per_page=20)
        assert response.total == 1
        assert len(response.items) == 1


class TestBillingRecordListResponse:
    def test_valid(self):
        record = BillingRecordResponse(
            id=uuid4(),
            action="reserve",
            amount=Decimal("-1.00"),
            balance_after=Decimal("99.00"),
            duration_sec=Decimal("60.00"),
            description="预扣",
            created_at=datetime.now(timezone.utc),
        )
        response = BillingRecordListResponse(items=[record], total=1, page=1, per_page=20)
        assert response.total == 1


class TestTaskListResponse:
    def test_valid(self):
        task = TaskResponse(
            id=uuid4(),
            user_id=uuid4(),
            upload_name="test.mp3",
            file_hash="abc",
            file_duration_sec=None,
            file_size_bytes=None,
            engine="local_whisper",
            model_size="small",
            stage="done",
            progress="1.0",
            stage_message="",
            error="",
            segment_count=3,
            credits_charged="1.00",
            credits_reserved="0.00",
            is_public=False,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            finished_at=None,
        )
        response = TaskListResponse(items=[task], total=1, page=1, per_page=20)
        assert response.total == 1


class TestTaskDetailResponse:
    def test_valid(self):
        task = TaskDetailResponse(
            id=uuid4(),
            user_id=uuid4(),
            upload_name="test.mp3",
            file_hash="abc",
            file_duration_sec=None,
            file_size_bytes=None,
            engine="local_whisper",
            model_size="small",
            stage="done",
            progress="1.0",
            stage_message="",
            error="",
            segment_count=3,
            credits_charged="1.00",
            credits_reserved="0.00",
            is_public=False,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            finished_at=None,
            segments=[],
        )
        assert task.segments == []


class TestPublicShareResponse:
    def test_valid(self):
        share = PublicShareResponse(
            id=uuid4(),
            task_id=uuid4(),
            user_id=uuid4(),
            title="My Share",
            description="A public share",
            difficulty="B1",
            category="podcast",
            duration_tier="short",
            cover_url="",
            play_count=0,
            like_count=0,
            collect_count=0,
            is_featured=False,
            shared_at=datetime.now(timezone.utc),
            is_liked=False,
            is_collected=False,
            upload_name="test.mp3",
            segment_count=3,
            file_duration_sec=Decimal("60.00"),
            tags=[],
        )
        assert share.title == "My Share"
        assert share.is_liked is False


class TestCollectionResponse:
    def test_valid(self):
        coll = CollectionResponse(
            id=uuid4(),
            name="My Collection",
            description="Test",
            item_count=5,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert coll.item_count == 5


class TestTagResponse:
    def test_valid(self):
        tag = TagResponse(
            id=uuid4(),
            name="my-tag",
            color="#FF0000",
            is_system=False,
            tag_type="custom",
            created_at=datetime.now(timezone.utc),
        )
        assert tag.tag_type == "custom"
        assert tag.is_system is False