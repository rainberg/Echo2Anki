import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import HelpArticle


def test_help_article_create(db_session):
    """HelpArticle 可以被创建并存储到数据库"""
    article = HelpArticle(
        slug="test-guide",
        title="Test Guide",
        content="# Hello\n\nWorld",
        category="tasks",
        sort_order=0,
        is_published=False,
    )
    db_session.add(article)
    db_session.commit()

    result = db_session.execute(select(HelpArticle).where(HelpArticle.slug == "test-guide"))
    found = result.scalar_one()
    assert found.title == "Test Guide"
    assert found.content == "# Hello\n\nWorld"
    assert found.category == "tasks"
    assert found.is_published is False
    assert found.sort_order == 0
    assert found.id is not None
    assert found.created_at is not None


def test_help_article_slug_unique(db_session):
    """slug 字段必须唯一"""
    article1 = HelpArticle(slug="same-slug", title="First", content="", category="tasks")
    db_session.add(article1)
    db_session.commit()

    article2 = HelpArticle(slug="same-slug", title="Second", content="", category="anki")
    db_session.add(article2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_help_article_default_values(db_session):
    """默认值正确：content='', sort_order=0, is_published=False"""
    article = HelpArticle(slug="defaults", title="Defaults", category="collections")
    db_session.add(article)
    db_session.commit()

    result = db_session.execute(select(HelpArticle).where(HelpArticle.slug == "defaults"))
    found = result.scalar_one()
    assert found.content == ""
    assert found.sort_order == 0
    assert found.is_published is False
