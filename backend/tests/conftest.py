import os
import re
import sys
import tempfile
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from sqlalchemy import event as sa_event
from sqlalchemy.types import TypeDecorator, Text, String


class ArrayAsJSON(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, list):
            return value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value


class UUIDAsString(TypeDecorator):
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(value)
        except (ValueError, TypeError):
            return value

    def _cached_bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            return str(value)
        return process


from app.database import Base, get_db
from app.config import settings
from app.models import (
    AnkiPushConfig,
    BillingRecord,
    Collection,
    CollectionItem,
    EnginePricing,
    HelpArticle,
    PushRecord,
    PushRecordItem,
    Segment,
    SegmentRating,
    Tag,
    Task,
    User,
)

from sqlalchemy import Uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

for table in Base.metadata.tables.values():
    for col in table.columns:
        if isinstance(col.type, (Uuid, PG_UUID)):
            col.type = UUIDAsString()

User.__table__.c.allowed_engines.type = ArrayAsJSON()
from app.deps import bearer_scheme


@pytest.fixture
def override_bearer_scheme(test_app):
    from fastapi.security import HTTPAuthorizationCredentials

    mock_cred = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=TEST_ACCESS_TOKEN,
    )

    async def _bearer_override():
        return mock_cred

    from app.routers import auth as auth_router_module
    from app.routers import tasks as tasks_router_module

    test_app.dependency_overrides[bearer_scheme] = _bearer_override
    test_app.dependency_overrides[auth_router_module.bearer_scheme] = _bearer_override
    test_app.dependency_overrides[tasks_router_module.bearer_scheme] = _bearer_override
    yield
    test_app.dependency_overrides.pop(bearer_scheme, None)
    test_app.dependency_overrides.pop(auth_router_module.bearer_scheme, None)
    test_app.dependency_overrides.pop(tasks_router_module.bearer_scheme, None)


TEST_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID2 = UUID("22222222-2222-2222-2222-222222222222")
TEST_TASK_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEST_COLLECTION_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TEST_SEGMENT_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
TEST_ADMIN_ID = UUID("99999999-9999-9999-9999-999999999999")

TEST_ACCESS_TOKEN = "test-access-token-12345"


@pytest.fixture(scope="function")
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture(scope="function")
def db_engine(db_path):
    from sqlalchemy import event as sa_event
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa_event.listens_for(engine, "connect")
    def _enable_regex(dbapi_connection, connection_record):
        dbapi_connection.enable_load_extension(True)
        import sqlite3

        def regexp(pattern, value):
            if value is None:
                return False
            return bool(re.search(pattern, str(value)))

        dbapi_connection.create_function("regexp", 2, regexp)

    @sa_event.listens_for(engine, "before_cursor_execute", retval=True)
    def _fix_params(conn, cursor, statement, parameters, context, executemany):
        if parameters is None:
            return statement, parameters
        import uuid as _uuid

        def _convert(val):
            if isinstance(val, _uuid.UUID):
                return str(val)
            if isinstance(val, Decimal):
                return float(val)
            return val

        if isinstance(parameters, (list, tuple)):
            if parameters and isinstance(parameters[0], (list, tuple)):
                return statement, [tuple(_convert(v) for v in row) for row in parameters]
            return statement, tuple(_convert(v) for v in parameters)
        if isinstance(parameters, dict):
            return statement, {k: _convert(v) for k, v in parameters.items()}
        return statement, parameters

    @sa_event.listens_for(engine, "before_execute", retval=True)
    def _fix_orm_params(conn, clauseelement, multiparams, params, execution_options):
        import uuid as _uuid
        def _cv(val):
            if isinstance(val, _uuid.UUID):
                return str(val)
            if isinstance(val, Decimal):
                return float(val)
            return val
        if params:
            params = {k: _cv(v) for k, v in params.items()}
        if multiparams:
            multiparams = [{k: _cv(v) for k, v in d.items()} for d in multiparams]
        return clauseelement, multiparams, params

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="function")
async def async_db_engine(db_path):
    from sqlalchemy.ext.asyncio import create_async_engine

    async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return async_engine


@pytest.fixture(scope="function")
def db_session(db_engine):
    SessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def sample_user(db_session):
    user = User(
        id=TEST_USER_ID,
        email="test@example.com",
        display_name="Test User",
        role="user",
        credits=Decimal("100.00"),
        credits_reserved=Decimal("0.00"),
        allowed_engines=["local_whisper"],
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_user2(db_session):
    user = User(
        id=TEST_USER_ID2,
        email="test2@example.com",
        display_name="Test User 2",
        role="user",
        credits=Decimal("50.00"),
        credits_reserved=Decimal("0.00"),
        allowed_engines=["local_whisper"],
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_admin(db_session):
    admin = User(
        id=TEST_ADMIN_ID,
        email="admin@example.com",
        display_name="Admin",
        role="admin",
        credits=Decimal("999.00"),
        credits_reserved=Decimal("0.00"),
        allowed_engines=["local_whisper", "openai_whisper", "cohere"],
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    return admin


@pytest.fixture
def sample_task(db_session, sample_user):
    task = Task(
        id=TEST_TASK_ID,
        user_id=TEST_USER_ID,
        upload_name="test.mp3",
        file_hash="abc123",
        file_duration_sec=Decimal("60.00"),
        file_size_bytes=100000,
        engine="local_whisper",
        model_size="small",
        stage="done",
        progress=Decimal("1.0"),
        segment_count=3,
        credits_charged=Decimal("1.00"),
        credits_reserved=Decimal("0.00"),
        reserve_reference_id=None,
        is_public=False,
    )
    db_session.add(task)
    db_session.commit()
    return task


@pytest.fixture
def sample_task_with_reserve(db_session, sample_user):
    task = Task(
        id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab"),
        user_id=TEST_USER_ID,
        upload_name="test_reserved.mp3",
        file_hash="def456",
        file_duration_sec=Decimal("120.00"),
        file_size_bytes=200000,
        engine="local_whisper",
        model_size="small",
        stage="pending",
        progress=Decimal("0.0"),
        segment_count=0,
        credits_charged=Decimal("0.00"),
        credits_reserved=Decimal("2.00"),
        reserve_reference_id="task:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab:1234567890",
        is_public=False,
    )
    db_session.add(task)
    db_session.commit()
    return task


@pytest.fixture
def sample_segments(db_session, sample_task):
    segs = []
    for i in range(3):
        seg = Segment(
            id=UUID(f"cccccccc-cccc-cccc-cccc-ccccccccccc{i}"),
            task_id=TEST_TASK_ID,
            seq_index=i,
            start_time=Decimal(str(i * 10.0)),
            end_time=Decimal(str((i + 1) * 10.0)),
            german_text=f"German text {i}",
            chinese_text=f"中文文本 {i}",
            clip_path=f"clips/clip_{i:03d}.mp3",
        )
        db_session.add(seg)
        segs.append(seg)
    db_session.commit()
    return segs


@pytest.fixture
def sample_collection(db_session, sample_user):
    coll = Collection(
        id=TEST_COLLECTION_ID,
        user_id=TEST_USER_ID,
        name="Test Collection",
        description="A test collection",
    )
    db_session.add(coll)
    db_session.commit()
    return coll


@pytest.fixture
def sample_collection_item(db_session, sample_collection, sample_segments):
    item = CollectionItem(
        collection_id=TEST_COLLECTION_ID,
        segment_id=sample_segments[0].id,
        push_enabled=True,
    )
    db_session.add(item)
    db_session.commit()
    return item


@pytest.fixture
def sample_tag(db_session, sample_user):
    tag = Tag(
        user_id=TEST_USER_ID,
        name="test-tag",
        color="#FF0000",
        is_system=False,
        tag_type="custom",
    )
    db_session.add(tag)
    db_session.commit()
    return tag


@pytest.fixture
def sample_pricing(db_session):
    pricing = EnginePricing(
        engine_key="local_whisper",
        model_size="small",
        engine_name="Local Whisper",
        credits_per_minute=Decimal("1.0"),
        is_active=True,
        sort_order=1,
    )
    db_session.add(pricing)

    pricing2 = EnginePricing(
        engine_key="openai_whisper",
        model_size="whisper-1",
        engine_name="OpenAI Whisper",
        credits_per_minute=Decimal("3.0"),
        is_active=True,
        sort_order=2,
    )
    db_session.add(pricing2)
    db_session.commit()
    return pricing


@pytest.fixture
def sample_billing_record(db_session, sample_user, sample_task):
    record = BillingRecord(
        user_id=TEST_USER_ID,
        task_id=TEST_TASK_ID,
        action="reserve",
        amount=Decimal("-1.00"),
        balance_after=Decimal("99.00"),
        duration_sec=Decimal("60.00"),
        description="预扣: local_whisper/small, 60s",
    )
    db_session.add(record)
    db_session.commit()
    return record


@pytest.fixture
def mock_auth_service():
    with patch("app.auth_client.verify_token") as mock_verify, \
         patch("app.auth_client.get_user_info") as mock_get_info:
        mock_verify.return_value = {
            "user_id": str(TEST_USER_ID),
            "role": "user",
            "is_active": True,
            "credits": "100.00",
            "credits_reserved": "0.00",
        }
        mock_get_info.return_value = {
            "user_id": str(TEST_USER_ID),
            "email": "test@example.com",
            "phone": None,
            "display_name": "Test User",
            "role": "user",
            "is_active": True,
            "credits": "100.00",
            "credits_reserved": "0.00",
        }
        yield


@pytest.fixture
def mock_admin_auth_service():
    with patch("app.auth_client.verify_token") as mock_verify, \
         patch("app.auth_client.get_user_info") as mock_get_info, \
         patch("app.routers.auth.admin_toggle_active") as mock_toggle:
        mock_verify.return_value = {
            "user_id": str(TEST_ADMIN_ID),
            "role": "admin",
            "is_active": True,
            "credits": "999.00",
            "credits_reserved": "0.00",
        }
        mock_get_info.return_value = {
            "user_id": str(TEST_ADMIN_ID),
            "email": "admin@example.com",
            "phone": None,
            "display_name": "Admin",
            "role": "admin",
            "is_active": True,
            "registry_time": "2025-01-01T00:00:00Z",
            "credits": "999.00",
            "credits_reserved": "0.00",
        }
        mock_toggle.return_value = {"success": True}
        yield mock_verify, mock_get_info, mock_toggle


@pytest.fixture
def mock_auth_reserve():
    with patch("app.auth_client.reserve_credits") as mock:
        mock.return_value = {"success": True, "credits": "98.00", "credits_reserved": "2.00"}
        yield mock


@pytest.fixture
def mock_auth_settle():
    with patch("app.auth_client.settle_credits") as mock:
        mock.return_value = {"success": True, "credits": "98.00", "refund": "0.00"}
        yield mock


@pytest.fixture
def mock_auth_settle_with_refund():
    with patch("app.auth_client.settle_credits") as mock:
        mock.return_value = {"success": True, "credits": "99.00", "refund": "1.00"}
        yield mock


@pytest.fixture
def mock_auth_refund():
    with patch("app.auth_client.refund_credits") as mock:
        mock.return_value = {"success": True, "credits": "100.00"}
        yield mock


@pytest.fixture
def override_get_db(db_session, test_app):
    async def _get_db_override():
        yield db_session

    test_app.dependency_overrides[get_db] = _get_db_override
    yield
    test_app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def override_get_async_db(async_db_engine, test_app):
    from sqlalchemy.ext.asyncio import AsyncSession

    async_session = AsyncSession(bind=async_db_engine, expire_on_commit=False)

    async def _get_db_override():
        yield async_session

    test_app.dependency_overrides[get_db] = _get_db_override
    yield
    await async_session.close()
    test_app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def override_get_current_user(db_session, sample_user, mock_auth_service, test_app, override_get_async_db, override_bearer_scheme):
    async def _get_current_user_override():
        return sample_user

    from app.deps import get_current_user
    test_app.dependency_overrides[get_current_user] = _get_current_user_override
    yield
    test_app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_get_admin_user(db_session, sample_admin, mock_admin_auth_service, test_app, override_get_async_db, override_bearer_scheme):
    async def _get_admin_user_override():
        return sample_admin

    from app.deps import get_admin_user
    test_app.dependency_overrides[get_admin_user] = _get_admin_user_override
    yield
    test_app.dependency_overrides.pop(get_admin_user, None)


@pytest.fixture
def test_app(tmp_path):
    from app.routers.auth import admin_router, router as auth_router
    from app.routers.anki import router as anki_router
    from app.routers.billing import router as billing_router
    from app.routers.collections import router as collections_router
    from app.routers.email import router as email_router
    from app.routers.public import router as public_router
    from app.routers.segments import router as segments_router
    from app.routers.system import router as system_router
    from app.routers.tags import router as tags_router
    from app.routers.tasks import router as tasks_router
    from app.routers.ws import router as ws_router
    from fastapi.middleware.cors import CORSMiddleware

    task_dir = tmp_path / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def _test_lifespan(app: FastAPI):
        yield

    test_app = FastAPI(
        title="Anki Audio Processing API",
        version="2.0.0",
        lifespan=_test_lifespan,
    )

    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    test_app.include_router(auth_router, prefix="/api")
    test_app.include_router(admin_router, prefix="/api")
    test_app.include_router(email_router, prefix="/api")
    test_app.include_router(system_router, prefix="/api")
    test_app.include_router(tasks_router, prefix="/api")
    test_app.include_router(segments_router, prefix="/api")
    test_app.include_router(collections_router, prefix="/api")
    test_app.include_router(tags_router, prefix="/api")
    test_app.include_router(billing_router, prefix="/api")
    test_app.include_router(public_router, prefix="/api")
    test_app.include_router(anki_router, prefix="/api")
    test_app.include_router(ws_router)

    from fastapi.staticfiles import StaticFiles
    test_app.mount("/api/audio", StaticFiles(directory=str(task_dir)), name="audio")

    @test_app.get("/api/health")
    async def _health():
        return {"status": "ok", "version": "2.0.0"}

    return test_app


@pytest.fixture
def async_client(test_app):
    transport = ASGITransport(app=test_app)
    client = AsyncClient(transport=transport, base_url="http://test")
    return client