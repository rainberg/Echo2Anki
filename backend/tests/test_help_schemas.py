import pytest
from pydantic import ValidationError


def test_help_article_create_valid():
    """HelpArticleCreate 接受合法数据"""
    from app.schemas_help import HelpArticleCreate
    data = HelpArticleCreate(
        slug="test-guide",
        title="Test Guide",
        content="# Hello",
        category="tasks",
        sort_order=1,
        is_published=True,
    )
    assert data.slug == "test-guide"
    assert data.title == "Test Guide"
    assert data.category == "tasks"
    assert data.sort_order == 1
    assert data.is_published is True


def test_help_article_create_defaults():
    """HelpArticleCreate 默认值：content='', sort_order=0, is_published=False"""
    from app.schemas_help import HelpArticleCreate
    data = HelpArticleCreate(slug="guide", title="Guide", category="anki")
    assert data.content == ""
    assert data.sort_order == 0
    assert data.is_published is False


def test_help_article_create_invalid_slug():
    """HelpArticleCreate 拒绝无效 slug（大写、空格、特殊字符）"""
    from app.schemas_help import HelpArticleCreate
    with pytest.raises(ValidationError):
        HelpArticleCreate(slug="Invalid Slug!", title="Bad", category="tasks")
    with pytest.raises(ValidationError):
        HelpArticleCreate(slug="UPPER", title="Bad", category="tasks")


def test_help_article_create_invalid_category():
    """HelpArticleCreate 拒绝无效分类"""
    from app.schemas_help import HelpArticleCreate
    with pytest.raises(ValidationError):
        HelpArticleCreate(slug="guide", title="Guide", category="invalid")


def test_help_article_update_partial():
    """HelpArticleUpdate 允许部分更新"""
    from app.schemas_help import HelpArticleUpdate
    data = HelpArticleUpdate(title="New Title")
    assert data.title == "New Title"
    assert data.slug is None
    assert data.content is None


def test_help_category_response():
    """HelpCategoryResponse 结构正确"""
    from app.schemas_help import HelpCategoryResponse, HelpArticleSummary
    data = HelpCategoryResponse(
        category="tasks",
        label="任务与音频处理",
        articles=[HelpArticleSummary(slug="guide", title="Guide")],
    )
    assert data.category == "tasks"
    assert len(data.articles) == 1


def test_help_article_public_response():
    """HelpArticlePublicResponse 不包含 is_published 等管理字段"""
    from app.schemas_help import HelpArticlePublicResponse
    data = HelpArticlePublicResponse(
        slug="guide",
        title="Guide",
        content="# Hello",
        category="tasks",
        updated_at="2026-06-03T00:00:00Z",
    )
    assert not hasattr(data, "is_published")
    assert not hasattr(data, "sort_order")
