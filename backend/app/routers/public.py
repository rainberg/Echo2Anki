from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user, get_optional_user
from app.models import (
    Collection,
    CollectionItem,
    PublicCollect,
    PublicLike,
    PublicShare,
    Segment,
    Tag,
    Task,
    TaskTag,
    User,
)
from app.schemas import (
    PaginatedPublicShareResponse,
    PublicShareCreate,
    PublicShareDetailResponse,
    PublicShareResponse,
    PublicShareUpdate,
    SegmentResponse,
    TagResponse,
    TaskResponse,
)

router = APIRouter(prefix="/public", tags=["public"])

VALID_DIFFICULTIES = ["A1", "A2", "B1", "B2", "C1", "C2"]
VALID_CATEGORIES = ["news", "daily", "textbook", "exam", "podcast", "movie", "business", "culture", "other"]
CATEGORY_NAMES = {
    "news": "新闻", "daily": "日常对话", "textbook": "教材", "exam": "备考",
    "podcast": "播客", "movie": "影视", "business": "商务", "culture": "文化", "other": "其他",
}
DIFFICULTY_NAMES = {
    "A1": "入门", "A2": "初级", "B1": "中级", "B2": "中高级", "C1": "高级", "C2": "精通",
}


def _compute_duration_tier(duration_sec) -> str:
    if duration_sec is None:
        return None
    d = float(duration_sec)
    if d < 30:
        return "short"
    elif d <= 180:
        return "medium"
    return "long"


def _share_to_response(share: PublicShare, user: User = None) -> PublicShareResponse:
    task = share.task
    is_liked = False
    is_collected = False
    if user:
        for like in share.likes:
            if like.user_id == user.id:
                is_liked = True
                break
        for coll in share.collects:
            if coll.user_id == user.id:
                is_collected = True
                break

    tags = []
    if task:
        for tt in task.task_tags:
            tags.append(TagResponse.model_validate(tt.tag))

    return PublicShareResponse(
        id=share.id,
        task_id=share.task_id,
        user_id=share.user_id,
        title=share.title,
        description=share.description,
        difficulty=share.difficulty,
        category=share.category,
        duration_tier=share.duration_tier,
        cover_url=share.cover_url or "",
        play_count=share.play_count or 0,
        like_count=share.like_count or 0,
        collect_count=share.collect_count or 0,
        is_featured=share.is_featured or False,
        shared_at=share.shared_at,
        is_liked=is_liked,
        is_collected=is_collected,
        upload_name=task.upload_name if task else "",
        segment_count=task.segment_count if task else 0,
        file_duration_sec=task.file_duration_sec if task else None,
        tags=tags,
    )


@router.get("/tasks", response_model=list[TaskResponse])
async def list_public_tasks(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    q: str = Query(None, max_length=200),
    tag: str = Query(None),
    user: User = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Task).where(Task.is_public == True, Task.stage == "done")

    if q:
        task_ids_subq = select(Segment.task_id).where(
            or_(
                Segment.german_text.ilike(f"%{q}%"),
                Segment.chinese_text.ilike(f"%{q}%"),
            )
        )
        query = query.where(Task.id.in_(task_ids_subq))

    if tag:
        tag_subq = select(TaskTag.task_id).join(Tag, Tag.id == TaskTag.tag_id).where(Tag.name == tag)
        query = query.where(Task.id.in_(tag_subq))

    query = query.order_by(Task.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    return [TaskResponse.model_validate(t) for t in result.scalars().all()]


@router.get("/tasks/{task_id}/segments", response_model=list[SegmentResponse])
async def get_public_segments(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    task_result = await db.execute(select(Task).where(Task.id == task_id, Task.is_public == True))
    if not task_result.scalar_one_or_none():
        return []

    result = await db.execute(
        select(Segment).where(Segment.task_id == task_id).order_by(Segment.seq_index)
    )
    return [SegmentResponse.model_validate(s) for s in result.scalars().all()]


@router.get("/tags", response_model=list[TagResponse])
async def list_public_tags(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Tag)
        .join(TaskTag, TaskTag.tag_id == Tag.id)
        .join(Task, Task.id == TaskTag.task_id)
        .where(Task.is_public == True)
        .distinct()
    )
    return [TagResponse.model_validate(t) for t in result.scalars().all()]


@router.get("/search", response_model=list[SegmentResponse])
async def search_segments(
    q: str = Query(..., min_length=1, max_length=200),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: User = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Segment).join(Task, Segment.task_id == Task.id).where(
        Task.is_public == True,
        Task.stage == "done",
        or_(
            Segment.german_text.ilike(f"%{q}%"),
            Segment.chinese_text.ilike(f"%{q}%"),
        ),
    )

    if user:
        user_query = select(Segment).where(
            Segment.task_id.in_(select(Task.id).where(Task.user_id == user.id)),
            or_(
                Segment.german_text.ilike(f"%{q}%"),
                Segment.chinese_text.ilike(f"%{q}%"),
            ),
        )
        query = query.union(user_query)

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    return [SegmentResponse.model_validate(s) for s in result.scalars().all()]


@router.post("/shares", response_model=PublicShareResponse, status_code=status.HTTP_201_CREATED)
async def create_share(
    body: PublicShareCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task_result = await db.execute(
        select(Task).where(Task.id == body.task_id, Task.user_id == user.id)
    )
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.stage != "done":
        raise HTTPException(status_code=400, detail="Only completed tasks can be shared")

    existing = await db.execute(
        select(PublicShare).where(PublicShare.task_id == body.task_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Task already shared")

    title = body.title or task.upload_name
    difficulty = body.difficulty if body.difficulty in VALID_DIFFICULTIES else None
    category = body.category if body.category in VALID_CATEGORIES else None
    duration_tier = _compute_duration_tier(task.file_duration_sec)

    share = PublicShare(
        task_id=task.id,
        user_id=user.id,
        title=title,
        description=body.description,
        difficulty=difficulty,
        category=category,
        duration_tier=duration_tier,
        shared_at=datetime.now(timezone.utc),
    )
    db.add(share)

    task.is_public = True

    if body.tag_ids:
        for tag_id in body.tag_ids:
            tag_check = await db.execute(select(Tag).where(Tag.id == tag_id))
            if tag_check.scalar_one_or_none():
                existing_tt = await db.execute(
                    select(TaskTag).where(TaskTag.task_id == task.id, TaskTag.tag_id == tag_id)
                )
                if not existing_tt.scalar_one_or_none():
                    db.add(TaskTag(task_id=task.id, tag_id=tag_id))

    await db.commit()
    await db.refresh(share)

    result = await db.execute(select(PublicShare).where(PublicShare.id == share.id))
    share = result.scalar_one()
    return _share_to_response(share, user)


@router.get("/shares", response_model=PaginatedPublicShareResponse)
async def list_shares(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    difficulty: str = Query(None),
    category: str = Query(None),
    duration_tier: str = Query(None),
    tag: str = Query(None),
    q: str = Query(None, max_length=200),
    sort: str = Query("newest"),
    task_id: str = Query(None),
    user: User = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(PublicShare)
    count_query = select(func.count()).select_from(PublicShare)

    if task_id:
        query = query.where(PublicShare.task_id == task_id)
        count_query = count_query.where(PublicShare.task_id == task_id)

    if difficulty and difficulty in VALID_DIFFICULTIES:
        query = query.where(PublicShare.difficulty == difficulty)
        count_query = count_query.where(PublicShare.difficulty == difficulty)
    if category and category in VALID_CATEGORIES:
        query = query.where(PublicShare.category == category)
        count_query = count_query.where(PublicShare.category == category)
    if duration_tier and duration_tier in ("short", "medium", "long"):
        query = query.where(PublicShare.duration_tier == duration_tier)
        count_query = count_query.where(PublicShare.duration_tier == duration_tier)

    if tag:
        tag_subq = select(TaskTag.task_id).join(Tag, Tag.id == TaskTag.tag_id).where(Tag.name == tag)
        share_subq = select(PublicShare.id).where(PublicShare.task_id.in_(tag_subq))
        query = query.where(PublicShare.id.in_(share_subq))
        count_query = count_query.where(PublicShare.id.in_(share_subq))

    if q:
        task_subq = select(Task.id).where(
            Task.id.in_(select(Segment.task_id).where(
                or_(Segment.german_text.ilike(f"%{q}%"), Segment.chinese_text.ilike(f"%{q}%"))
            ))
        )
        q_filter = PublicShare.task_id.in_(task_subq) | PublicShare.title.ilike(f"%{q}%")
        query = query.where(q_filter)
        count_query = count_query.where(q_filter)

    if sort == "popular":
        query = query.order_by(PublicShare.like_count.desc(), PublicShare.shared_at.desc())
    elif sort == "most_collected":
        query = query.order_by(PublicShare.collect_count.desc(), PublicShare.shared_at.desc())
    else:
        query = query.order_by(PublicShare.shared_at.desc())

    total = (await db.execute(count_query)).scalar()
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    shares = result.scalars().all()

    items = [_share_to_response(s, user) for s in shares]
    return PaginatedPublicShareResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/shares/{share_id}", response_model=PublicShareDetailResponse)
async def get_share(
    share_id: UUID,
    user: User = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PublicShare).where(PublicShare.id == share_id))
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    seg_result = await db.execute(
        select(Segment).where(Segment.task_id == share.task_id).order_by(Segment.seq_index)
    )
    segments = [SegmentResponse.model_validate(s) for s in seg_result.scalars().all()]

    resp = PublicShareDetailResponse(
        id=share.id,
        task_id=share.task_id,
        user_id=share.user_id,
        title=share.title,
        description=share.description,
        difficulty=share.difficulty,
        category=share.category,
        duration_tier=share.duration_tier,
        cover_url=share.cover_url or "",
        play_count=share.play_count or 0,
        like_count=share.like_count or 0,
        collect_count=share.collect_count or 0,
        is_featured=share.is_featured or False,
        shared_at=share.shared_at,
        is_liked=False,
        is_collected=False,
        upload_name=share.task.upload_name if share.task else "",
        segment_count=share.task.segment_count if share.task else 0,
        file_duration_sec=share.task.file_duration_sec if share.task else None,
        tags=[],
        segments=segments,
        sharer_name=share.user_rel.display_name if share.user_rel else None,
    )

    if user:
        for like in share.likes:
            if like.user_id == user.id:
                resp.is_liked = True
                break
        for coll in share.collects:
            if coll.user_id == user.id:
                resp.is_collected = True
                break

    if share.task:
        for tt in share.task.task_tags:
            resp.tags.append(TagResponse.model_validate(tt.tag))

    return resp


@router.patch("/shares/{share_id}", response_model=PublicShareResponse)
async def update_share(
    share_id: UUID,
    body: PublicShareUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PublicShare).where(PublicShare.id == share_id, PublicShare.user_id == user.id)
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    if body.title is not None:
        share.title = body.title
    if body.description is not None:
        share.description = body.description
    if body.difficulty is not None:
        if body.difficulty in VALID_DIFFICULTIES or body.difficulty == "":
            share.difficulty = body.difficulty if body.difficulty else None
    if body.category is not None:
        if body.category in VALID_CATEGORIES or body.category == "":
            share.category = body.category if body.category else None
    if body.tag_ids is not None:
        task = share.task
        if task:
            existing_tt = await db.execute(
                select(TaskTag).where(TaskTag.task_id == task.id)
            )
            for tt in existing_tt.scalars().all():
                await db.delete(tt)
            for tag_id in body.tag_ids:
                tag_check = await db.execute(select(Tag).where(Tag.id == tag_id))
                if tag_check.scalar_one_or_none():
                    db.add(TaskTag(task_id=task.id, tag_id=tag_id))

    share.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(share)

    result = await db.execute(select(PublicShare).where(PublicShare.id == share.id))
    share = result.scalar_one()
    return _share_to_response(share, user)


@router.delete("/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_share(
    share_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PublicShare).where(PublicShare.id == share_id, PublicShare.user_id == user.id)
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    task_result = await db.execute(select(Task).where(Task.id == share.task_id))
    task = task_result.scalar_one_or_none()
    if task:
        task.is_public = False

    await db.delete(share)
    await db.commit()


@router.post("/shares/{share_id}/like")
async def like_share(
    share_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PublicShare).where(PublicShare.id == share_id))
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    existing = await db.execute(
        select(PublicLike).where(PublicLike.user_id == user.id, PublicLike.share_id == share_id)
    )
    if existing.scalar_one_or_none():
        return {"liked": True, "like_count": share.like_count}

    db.add(PublicLike(user_id=user.id, share_id=share_id))
    share.like_count = (share.like_count or 0) + 1
    await db.commit()
    return {"liked": True, "like_count": share.like_count}


@router.delete("/shares/{share_id}/like")
async def unlike_share(
    share_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PublicShare).where(PublicShare.id == share_id))
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    existing = await db.execute(
        select(PublicLike).where(PublicLike.user_id == user.id, PublicLike.share_id == share_id)
    )
    like = existing.scalar_one_or_none()
    if like:
        await db.delete(like)
        share.like_count = max((share.like_count or 0) - 1, 0)
        await db.commit()
    return {"liked": False, "like_count": share.like_count or 0}


@router.post("/shares/{share_id}/collect")
async def collect_share(
    share_id: UUID,
    collection_id: UUID = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PublicShare).where(PublicShare.id == share_id))
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    existing = await db.execute(
        select(PublicCollect).where(
            PublicCollect.user_id == user.id,
            PublicCollect.share_id == share_id,
            PublicCollect.collection_id == collection_id if collection_id else PublicCollect.collection_id.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        return {"collected": True, "collect_count": share.collect_count}

    db.add(PublicCollect(user_id=user.id, share_id=share_id, collection_id=collection_id))

    if collection_id:
        coll_result = await db.execute(
            select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id)
        )
        coll = coll_result.scalar_one_or_none()
        if coll:
            seg_result = await db.execute(
                select(Segment).where(Segment.task_id == share.task_id).order_by(Segment.seq_index)
            )
            for seg in seg_result.scalars().all():
                existing_item = await db.execute(
                    select(CollectionItem).where(
                        CollectionItem.collection_id == collection_id,
                        CollectionItem.segment_id == seg.id,
                    )
                )
                if not existing_item.scalar_one_or_none():
                    db.add(CollectionItem(collection_id=collection_id, segment_id=seg.id, push_enabled=True))

    share.collect_count = (share.collect_count or 0) + 1
    await db.commit()
    return {"collected": True, "collect_count": share.collect_count}


@router.delete("/shares/{share_id}/collect")
async def uncollect_share(
    share_id: UUID,
    collection_id: UUID = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PublicShare).where(PublicShare.id == share_id))
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    q = select(PublicCollect).where(PublicCollect.user_id == user.id, PublicCollect.share_id == share_id)
    if collection_id:
        q = q.where(PublicCollect.collection_id == collection_id)
    existing = await db.execute(q)
    collect = existing.scalar_one_or_none()
    if collect:
        await db.delete(collect)
        share.collect_count = max((share.collect_count or 0) - 1, 0)
        await db.commit()
    return {"collected": False, "collect_count": share.collect_count or 0}


@router.post("/shares/{share_id}/play")
async def record_play(
    share_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PublicShare).where(PublicShare.id == share_id))
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    share.play_count = (share.play_count or 0) + 1
    await db.commit()
    return {"play_count": share.play_count}


@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    counts = {}
    for cat in VALID_CATEGORIES:
        result = await db.execute(
            select(func.count()).select_from(PublicShare).where(PublicShare.category == cat)
        )
        counts[cat] = result.scalar() or 0

    return [
        {"key": cat, "name": CATEGORY_NAMES[cat], "count": counts.get(cat, 0)}
        for cat in VALID_CATEGORIES
    ]


@router.get("/difficulties")
async def list_difficulties(db: AsyncSession = Depends(get_db)):
    counts = {}
    for diff in VALID_DIFFICULTIES:
        result = await db.execute(
            select(func.count()).select_from(PublicShare).where(PublicShare.difficulty == diff)
        )
        counts[diff] = result.scalar() or 0

    return [
        {"key": diff, "name": DIFFICULTY_NAMES[diff], "count": counts.get(diff, 0)}
        for diff in VALID_DIFFICULTIES
    ]
