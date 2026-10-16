import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from uuid import UUID
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import get_db, Base
from app.deps import get_admin_user, get_current_user
from app.models import HelpArticle
from app.routers.help import admin_help_router, router as help_router


@pytest.fixture
async def help_env(db_path):
    """测试环境: (async_client, session_factory)"""
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
    test_app.include_router(help_router, prefix="/api")
    test_app.include_router(admin_help_router, prefix="/api")

    async def _get_db_override():
        async with session_factory() as session:
            yield session

    test_app.dependency_overrides[get_db] = _get_db_override
    test_app.dependency_overrides[get_admin_user] = lambda: type(
        "User", (), {"id": UUID("00000000-0000-0000-0000-000000000001"), "role": "admin"}
    )()
    test_app.dependency_overrides[get_current_user] = lambda: type(
        "User", (), {"id": UUID("00000000-0000-0000-0000-000000000001"), "role": "admin"}
    )()

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, session_factory

    test_app.dependency_overrides.clear()
    await async_engine.dispose()


async def _seed_articles(session_factory):
    """创建测试数据"""
    async with session_factory() as session:
        articles = [
            HelpArticle(slug="task-guide", title="任务指南", content="# 任务指南\n\n内容", category="tasks", sort_order=1, is_published=True),
            HelpArticle(slug="task-tips", title="任务技巧", content="技巧内容", category="tasks", sort_order=2, is_published=True),
            HelpArticle(slug="collection-guide", title="收藏指南", content="# 收藏指南", category="collections", sort_order=1, is_published=True),
            HelpArticle(slug="anki-draft", title="Anki草稿", content="草稿内容", category="anki", sort_order=1, is_published=False),
        ]
        for a in articles:
            session.add(a)
        await session.commit()


# ─── Public API tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_categories_returns_published_only(help_env):
    """公开分类列表只返回已发布的文章"""
    client, sf = help_env
    await _seed_articles(sf)
    resp = await client.get("/api/help/categories")
    assert resp.status_code == 200
    data = resp.json()
    # 应该有 tasks 和 collections 两个分类（anki 只有草稿）
    categories = [c["category"] for c in data]
    assert "tasks" in categories
    assert "collections" in categories
    # anki 分类只有草稿文章，不应出现（或出现但 articles 为空）
    anki_cat = next((c for c in data if c["category"] == "anki"), None)
    assert anki_cat is None or len(anki_cat["articles"]) == 0
    # tasks 分类应该有 2 篇文章
    tasks_cat = next(c for c in data if c["category"] == "tasks")
    assert len(tasks_cat["articles"]) == 2


@pytest.mark.asyncio
async def test_list_categories_has_labels(help_env):
    """分类列表包含中文标签"""
    client, sf = help_env
    await _seed_articles(sf)
    resp = await client.get("/api/help/categories")
    data = resp.json()
    tasks_cat = next(c for c in data if c["category"] == "tasks")
    assert tasks_cat["label"] == "任务与音频处理"


@pytest.mark.asyncio
async def test_get_article_by_slug(help_env):
    """通过 slug 获取已发布文章"""
    client, sf = help_env
    await _seed_articles(sf)
    resp = await client.get("/api/help/articles/task-guide")
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "task-guide"
    assert data["title"] == "任务指南"
    assert "任务指南" in data["content"]


@pytest.mark.asyncio
async def test_get_article_unpublished_returns_404(help_env):
    """获取未发布文章返回 404"""
    client, sf = help_env
    await _seed_articles(sf)
    resp = await client.get("/api/help/articles/anki-draft")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_article_nonexistent_returns_404(help_env):
    """获取不存在的文章返回 404"""
    client, _ = help_env
    resp = await client.get("/api/help/articles/nonexistent")
    assert resp.status_code == 404


# ─── Admin API tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_list_articles(help_env):
    """管理员可以列出所有文章（含未发布）"""
    client, sf = help_env
    await _seed_articles(sf)
    resp = await client.get("/api/admin/help/articles")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4  # 包括草稿


@pytest.mark.asyncio
async def test_admin_list_articles_filter_by_category(help_env):
    """管理员可以按分类筛选文章"""
    client, sf = help_env
    await _seed_articles(sf)
    resp = await client.get("/api/admin/help/articles", params={"category": "tasks"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all(a["category"] == "tasks" for a in data)


@pytest.mark.asyncio
async def test_admin_create_article(help_env):
    """管理员可以创建文章"""
    client, sf = help_env
    resp = await client.post("/api/admin/help/articles", json={
        "slug": "new-article",
        "title": "新文章",
        "content": "# 新文章\n\n内容",
        "category": "anki",
        "sort_order": 0,
        "is_published": True,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "new-article"
    assert data["title"] == "新文章"
    assert data["is_published"] is True

    # 验证数据库中确实存在
    async with sf() as session:
        result = await session.execute(select(HelpArticle).where(HelpArticle.slug == "new-article"))
        assert result.scalar_one() is not None


@pytest.mark.asyncio
async def test_admin_create_duplicate_slug_returns_409(help_env):
    """创建重复 slug 返回 409"""
    client, sf = help_env
    await _seed_articles(sf)
    resp = await client.post("/api/admin/help/articles", json={
        "slug": "task-guide",
        "title": "重复",
        "category": "tasks",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_admin_update_article(help_env):
    """管理员可以更新文章"""
    client, sf = help_env
    await _seed_articles(sf)
    async with sf() as session:
        result = await session.execute(select(HelpArticle).where(HelpArticle.slug == "task-guide"))
        article = result.scalar_one()
    resp = await client.put(f"/api/admin/help/articles/{article.id}", json={
        "title": "更新后的标题",
        "is_published": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "更新后的标题"
    assert data["is_published"] is False


@pytest.mark.asyncio
async def test_admin_delete_article(help_env):
    """管理员可以删除文章"""
    client, sf = help_env
    await _seed_articles(sf)
    async with sf() as session:
        result = await session.execute(select(HelpArticle).where(HelpArticle.slug == "task-guide"))
        article = result.scalar_one()
    resp = await client.delete(f"/api/admin/help/articles/{article.id}")
    assert resp.status_code == 204

    # 验证数据库中已删除
    async with sf() as session:
        result = await session.execute(select(HelpArticle).where(HelpArticle.slug == "task-guide"))
        assert result.scalar_one_or_none() is None
