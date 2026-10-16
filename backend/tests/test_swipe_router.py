"""Swipe router TDD tests — written BEFORE implementation."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from contextlib import asynccontextmanager
from uuid import UUID, uuid4
from decimal import Decimal

from fastapi import FastAPI

from app.database import get_db, Base
from app.deps import get_optional_user, get_current_user
from app.models import User, Task, Segment, PublicShare, SegmentRating
from app.routers.swipe import router as swipe_router


# ── Fixed test IDs ──────────────────────────────────────────────────────

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_USER_ID = UUID("22222222-2222-2222-2222-222222222222")

TASK_A1_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TASK_A2_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaab")
TASK_B1_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaac")

SHARE_A1_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1")
SHARE_A2_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2")
SHARE_B1_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb3")

SEG_A1_0 = UUID("cccccccc-cccc-cccc-cccc-ccccccccccc0")
SEG_A1_1 = UUID("cccccccc-cccc-cccc-cccc-ccccccccccc1")
SEG_A2_0 = UUID("cccccccc-cccc-cccc-cccc-ccccccccccc2")
SEG_A2_1 = UUID("cccccccc-cccc-cccc-cccc-ccccccccccc3")
SEG_B1_0 = UUID("cccccccc-cccc-cccc-cccc-ccccccccccc4")
SEG_B1_1 = UUID("cccccccc-cccc-cccc-cccc-ccccccccccc5")


# ── Fixture ─────────────────────────────────────────────────────────────


@pytest.fixture
async def swipe_env(db_path):
    """搭建测试环境: (async_client, session_factory)"""
    async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )

    @asynccontextmanager
    async def _test_lifespan(app: FastAPI):
        yield

    test_app = FastAPI(lifespan=_test_lifespan)
    test_app.include_router(swipe_router, prefix="/api")

    async def _get_db_override():
        async with session_factory() as session:
            yield session

    test_app.dependency_overrides[get_db] = _get_db_override
    # 默认未登录：get_optional_user 返回 None
    test_app.dependency_overrides[get_optional_user] = lambda: None
    # get_current_user 不覆盖，未提供 Bearer token 时会自动返回 401

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, session_factory

    test_app.dependency_overrides.clear()
    await async_engine.dispose()


async def _seed_data(session_factory):
    """创建种子数据: User + Tasks + PublicShares + Segments"""
    async with session_factory() as session:
        # 用户
        user = User(
            id=USER_ID,
            email="test@example.com",
            display_name="Test User",
            role="user",
            credits=Decimal("100.00"),
            credits_reserved=Decimal("0.00"),
            allowed_engines=["local_whisper"],
            is_active=True,
        )
        other_user = User(
            id=OTHER_USER_ID,
            email="other@example.com",
            display_name="Other User",
            role="user",
            credits=Decimal("50.00"),
            credits_reserved=Decimal("0.00"),
            allowed_engines=["local_whisper"],
            is_active=True,
        )
        session.add_all([user, other_user])

        # 3 个 Task（不同难度）
        task_a1 = Task(
            id=TASK_A1_ID,
            user_id=OTHER_USER_ID,
            upload_name="a1_audio.mp3",
            file_hash="hash_a1",
            file_duration_sec=Decimal("30.00"),
            stage="completed",
            is_public=True,
            segment_count=2,
        )
        task_a2 = Task(
            id=TASK_A2_ID,
            user_id=OTHER_USER_ID,
            upload_name="a2_audio.mp3",
            file_hash="hash_a2",
            file_duration_sec=Decimal("60.00"),
            stage="completed",
            is_public=True,
            segment_count=2,
        )
        task_b1 = Task(
            id=TASK_B1_ID,
            user_id=OTHER_USER_ID,
            upload_name="b1_audio.mp3",
            file_hash="hash_b1",
            file_duration_sec=Decimal("90.00"),
            stage="completed",
            is_public=True,
            segment_count=2,
        )
        session.add_all([task_a1, task_a2, task_b1])

        # 3 个 PublicShare
        share_a1 = PublicShare(
            id=SHARE_A1_ID,
            task_id=TASK_A1_ID,
            user_id=OTHER_USER_ID,
            title="A1 日常对话",
            difficulty="A1",
            category="daily",
        )
        share_a2 = PublicShare(
            id=SHARE_A2_ID,
            task_id=TASK_A2_ID,
            user_id=OTHER_USER_ID,
            title="A2 旅行德语",
            difficulty="A2",
            category="travel",
        )
        share_b1 = PublicShare(
            id=SHARE_B1_ID,
            task_id=TASK_B1_ID,
            user_id=OTHER_USER_ID,
            title="B1 新闻听力",
            difficulty="B1",
            category="news",
        )
        session.add_all([share_a1, share_a2, share_b1])

        # 6 个 Segment（每个 task 2 个）
        segments = [
            Segment(
                id=SEG_A1_0, task_id=TASK_A1_ID, seq_index=0,
                start_time=Decimal("0.0"), end_time=Decimal("5.0"),
                german_text="Guten Morgen!", chinese_text="早上好！",
                clip_path="clips/a1_0.mp3",
            ),
            Segment(
                id=SEG_A1_1, task_id=TASK_A1_ID, seq_index=1,
                start_time=Decimal("5.0"), end_time=Decimal("10.0"),
                german_text="Wie geht es dir?", chinese_text="你好吗？",
                clip_path="clips/a1_1.mp3",
            ),
            Segment(
                id=SEG_A2_0, task_id=TASK_A2_ID, seq_index=0,
                start_time=Decimal("0.0"), end_time=Decimal("6.0"),
                german_text="Ich möchte einen Kaffee bestellen.", chinese_text="我想点一杯咖啡。",
                clip_path="clips/a2_0.mp3",
            ),
            Segment(
                id=SEG_A2_1, task_id=TASK_A2_ID, seq_index=1,
                start_time=Decimal("6.0"), end_time=Decimal("12.0"),
                german_text="Können Sie das wiederholen?", chinese_text="您能重复一下吗？",
                clip_path="clips/a2_1.mp3",
            ),
            Segment(
                id=SEG_B1_0, task_id=TASK_B1_ID, seq_index=0,
                start_time=Decimal("0.0"), end_time=Decimal("8.0"),
                german_text="Die Wirtschaftslage hat sich verbessert.", chinese_text="经济形势有所改善。",
                clip_path="clips/b1_0.mp3",
            ),
            Segment(
                id=SEG_B1_1, task_id=TASK_B1_ID, seq_index=1,
                start_time=Decimal("8.0"), end_time=Decimal("16.0"),
                german_text="Umweltschutz ist ein wichtiges Thema.", chinese_text="环保是一个重要话题。",
                clip_path="clips/b1_1.mp3",
            ),
        ]
        session.add_all(segments)
        await session.commit()


# ── Helper: create swipe_env with logged-in user ───────────────────────


@pytest.fixture
async def swipe_env_logged_in(swipe_env):
    """返回 (client, session_factory)，且 get_optional_user / get_current_user 返回已登录用户"""
    client, sf = swipe_env
    # 获取 test_app 来覆盖依赖
    # 由于 swipe_env 已关闭了 app 引用，我们通过重新设置方式处理
    # 这里直接在测试中用不同方式处理
    return client, sf


# ── Tests ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_feed_returns_segments(swipe_env):
    """GET /api/swipe/feed?source=public&limit=5 返回片段列表"""
    client, sf = swipe_env
    await _seed_data(sf)

    resp = await client.get("/api/swipe/feed", params={"source": "public", "limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert "segments" in data
    assert "current_level" in data
    assert "total_rated" in data
    assert isinstance(data["segments"], list)
    assert len(data["segments"]) <= 5
    # 有种子数据，应该至少返回一些片段
    assert len(data["segments"]) > 0


@pytest.mark.asyncio
async def test_feed_segment_structure(swipe_env):
    """Feed 返回的片段包含必要字段"""
    client, sf = swipe_env
    await _seed_data(sf)

    resp = await client.get("/api/swipe/feed", params={"source": "public", "limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    if data["segments"]:
        seg = data["segments"][0]
        assert "id" in seg
        assert "german_text" in seg
        assert "chinese_text" in seg
        assert "audio_url" in seg
        assert "difficulty" in seg
        assert "source_title" in seg
        assert "duration" in seg


@pytest.mark.asyncio
async def test_feed_filter_by_difficulty(swipe_env):
    """GET /api/swipe/feed?level=A1 指定难度级别过滤"""
    client, sf = swipe_env
    await _seed_data(sf)

    resp = await client.get("/api/swipe/feed", params={"source": "public", "level": "A1"})
    assert resp.status_code == 200
    data = resp.json()
    # A1 级别应该只返回 A1 的片段
    for seg in data["segments"]:
        assert seg["difficulty"] == "A1"


@pytest.mark.asyncio
async def test_rate_creates_rating(swipe_env):
    """POST /api/swipe/rate 标注片段难度"""
    client, sf = swipe_env
    await _seed_data(sf)

    # 需要登录用户 — 覆盖依赖
    # 我们通过直接在数据库中操作来模拟登录用户的标注
    # 但实际上需要测试 API，所以需要覆盖 get_optional_user
    # 这里用匿名用户（user_id=None）也可以标注
    resp = await client.post("/api/swipe/rate", json={
        "segment_id": str(SEG_A1_0),
        "rating": "easy",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["rating"] == "easy"

    # 验证数据库中存在标注
    async with sf() as session:
        result = await session.execute(
            select(SegmentRating).where(SegmentRating.segment_id == SEG_A1_0)
        )
        rating = result.scalar_one_or_none()
        assert rating is not None
        assert rating.rating == "easy"


@pytest.mark.asyncio
async def test_rate_updates_existing(swipe_env):
    """POST /api/swipe/rate 重复标注同一片段 — 更新已有标注"""
    client, sf = swipe_env
    await _seed_data(sf)

    # 第一次标注
    resp1 = await client.post("/api/swipe/rate", json={
        "segment_id": str(SEG_A1_0),
        "rating": "easy",
    })
    assert resp1.status_code == 200

    # 第二次标注同一片段（更新）
    resp2 = await client.post("/api/swipe/rate", json={
        "segment_id": str(SEG_A1_0),
        "rating": "hard",
    })
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["rating"] == "hard"

    # 验证数据库中只有一条记录
    async with sf() as session:
        result = await session.execute(
            select(SegmentRating).where(SegmentRating.segment_id == SEG_A1_0)
        )
        ratings = result.scalars().all()
        assert len(ratings) == 1
        assert ratings[0].rating == "hard"


@pytest.mark.asyncio
async def test_stats_default_values(swipe_env):
    """GET /api/swipe/stats 无标注时返回默认值"""
    client, sf = swipe_env
    await _seed_data(sf)

    resp = await client.get("/api/swipe/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_level"] == "A1"
    assert data["total_rated"] == 0
    assert data["easy_count"] == 0
    assert data["hard_count"] == 0
    assert data["consecutive_easy"] == 0
    assert data["consecutive_hard"] == 0


@pytest.mark.asyncio
async def test_stats_with_ratings(swipe_env):
    """GET /api/swipe/stats 有标注时返回统计"""
    client, sf = swipe_env
    await _seed_data(sf)

    # 标注几个片段
    await client.post("/api/swipe/rate", json={
        "segment_id": str(SEG_A1_0), "rating": "easy",
    })
    await client.post("/api/swipe/rate", json={
        "segment_id": str(SEG_A1_1), "rating": "easy",
    })
    await client.post("/api/swipe/rate", json={
        "segment_id": str(SEG_A2_0), "rating": "hard",
    })

    resp = await client.get("/api/swipe/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rated"] == 3
    assert data["easy_count"] == 2
    assert data["hard_count"] == 1
    # 最后一个是 hard，所以 consecutive_hard >= 1
    assert data["consecutive_hard"] >= 1


@pytest.mark.asyncio
async def test_feed_excludes_rated_segments(swipe_env):
    """已标注的片段不应出现在 feed 中（匿名用户场景）"""
    client, sf = swipe_env
    await _seed_data(sf)

    # 先获取 feed，确认有片段
    resp1 = await client.get("/api/swipe/feed", params={"source": "public", "limit": 10})
    assert resp1.status_code == 200
    seg_ids_before = {s["id"] for s in resp1.json()["segments"]}

    # 标注一个片段
    await client.post("/api/swipe/rate", json={
        "segment_id": str(SEG_A1_0), "rating": "easy",
    })

    # 再次获取 feed，该片段不应出现
    resp2 = await client.get("/api/swipe/feed", params={"source": "public", "limit": 10})
    assert resp2.status_code == 200
    seg_ids_after = {s["id"] for s in resp2.json()["segments"]}
    assert str(SEG_A1_0) not in seg_ids_after


@pytest.mark.asyncio
async def test_collect_requires_login(swipe_env):
    """POST /api/swipe/collect 需要登录"""
    client, sf = swipe_env
    await _seed_data(sf)

    resp = await client.post("/api/swipe/collect", json={
        "segment_id": str(SEG_A1_0),
        "collection_id": str(uuid4()),
    })
    # 未登录应返回 403（HTTPBearer 无 token 时返回 403）
    assert resp.status_code == 403
