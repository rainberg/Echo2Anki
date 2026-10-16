from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_admin_user
from app.models import HelpArticle, User
from app.schemas_help import (
    HelpArticleCreate,
    HelpArticlePublicResponse,
    HelpArticleResponse,
    HelpArticleSummary,
    HelpArticleUpdate,
    HelpCategoryResponse,
)

CATEGORY_LABELS = {
    "tasks": "任务与音频处理",
    "collections": "收藏与公共库",
    "anki": "Anki 推送",
}

router = APIRouter(prefix="/help", tags=["help"])
admin_help_router = APIRouter(prefix="/admin/help", tags=["admin-help"])


# ─── Public endpoints ──────────────────────────────────────────────────


@router.get("/categories", response_model=list[HelpCategoryResponse])
async def list_help_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(HelpArticle)
        .where(HelpArticle.is_published == True)
        .order_by(HelpArticle.category, HelpArticle.sort_order, HelpArticle.title)
    )
    articles = result.scalars().all()

    grouped: dict[str, list[HelpArticleSummary]] = {}
    for a in articles:
        grouped.setdefault(a.category, []).append(HelpArticleSummary(slug=a.slug, title=a.title))

    response = []
    for cat_key, label in CATEGORY_LABELS.items():
        if cat_key in grouped:
            response.append(HelpCategoryResponse(category=cat_key, label=label, articles=grouped[cat_key]))
    return response


@router.get("/articles/{slug}", response_model=HelpArticlePublicResponse)
async def get_help_article(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(HelpArticle).where(HelpArticle.slug == slug, HelpArticle.is_published == True)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return article


# ─── Admin endpoints ───────────────────────────────────────────────────


@admin_help_router.get("/articles", response_model=list[HelpArticleResponse])
async def admin_list_articles(
    category: str = None,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(HelpArticle).order_by(HelpArticle.category, HelpArticle.sort_order, HelpArticle.title)
    if category:
        query = query.where(HelpArticle.category == category)
    result = await db.execute(query)
    return result.scalars().all()


@admin_help_router.post("/articles", response_model=HelpArticleResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_article(
    body: HelpArticleCreate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(HelpArticle).where(HelpArticle.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")
    article = HelpArticle(**body.model_dump())
    db.add(article)
    await db.commit()
    await db.refresh(article)
    return article


@admin_help_router.put("/articles/{article_id}", response_model=HelpArticleResponse)
async def admin_update_article(
    article_id: UUID,
    body: HelpArticleUpdate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(HelpArticle).where(HelpArticle.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    if body.slug is not None and body.slug != article.slug:
        existing = await db.execute(select(HelpArticle).where(HelpArticle.slug == body.slug))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(article, key, value)
    await db.commit()
    await db.refresh(article)
    return article


@admin_help_router.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_article(
    article_id: UUID,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(HelpArticle).where(HelpArticle.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    await db.delete(article)
    await db.commit()
