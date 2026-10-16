"""Swipe router — feed / rate / collect / stats endpoints."""

import logging
import random
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import get_current_user, get_optional_user
from app.models import PublicShare, Segment, SegmentRating, Task, User
from app.schemas_swipe import (
    DIFFICULTY_LEVELS,
    SwipeCollectRequest,
    SwipeFeedResponse,
    SwipeFeedSegment,
    SwipeRateRequest,
    SwipeStatsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/swipe", tags=["swipe"])


# ── Helper: compute user's current difficulty level ─────────────────────


async def _get_user_level(db: AsyncSession, user_id: Optional[UUID]) -> str:
    """根据用户历史标注计算当前难度级别。

    算法：
    - 无标注 → A1
    - 最近 5 次标注中 easy 占多数 → 升一级（不超过 C2）
    - 最近 5 次标注中 hard 占多数 → 降一级（不低于 A1）
    - 否则保持当前级别
    """
    if user_id is None:
        return "A1"

    # 获取该用户所有标注，按时间倒序
    result = await db.execute(
        select(SegmentRating)
        .where(SegmentRating.user_id == user_id)
        .order_by(SegmentRating.created_at.desc())
    )
    ratings = result.scalars().all()

    if not ratings:
        return "A1"

    # 计算当前级别：基于 easy/hard 比例
    easy_count = sum(1 for r in ratings if r.rating == "easy")
    hard_count = sum(1 for r in ratings if r.rating == "hard")

    # 用最近 5 次标注来决定升降
    recent = ratings[:5]
    recent_easy = sum(1 for r in recent if r.rating == "easy")
    recent_hard = sum(1 for r in recent if r.rating == "hard")

    # 基础级别由总标注决定
    base_idx = min(easy_count // 3, len(DIFFICULTY_LEVELS) - 1)

    # 最近趋势微调
    if recent_easy > recent_hard:
        base_idx = min(base_idx + 1, len(DIFFICULTY_LEVELS) - 1)
    elif recent_hard > recent_easy:
        base_idx = max(base_idx - 1, 0)

    return DIFFICULTY_LEVELS[base_idx]


# ── GET /feed ───────────────────────────────────────────────────────────


@router.get("/feed", response_model=SwipeFeedResponse)
async def get_feed(
    source: str = "public",
    level: Optional[str] = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """获取 swipe feed 片段列表。

    - source=public: 从公开分享中获取
    - level: 指定难度级别过滤
    - 80% 当前难度及以下 + 20% 更高难度
    - 排除已标注的片段
    """
    user_id = user.id if user else None
    current_level = level or await _get_user_level(db, user_id)

    if source == "mine":
        # ── 我的片段：用户自己的已完成 Task 的 Segments ──
        if user_id is None:
            raise HTTPException(status_code=401, detail="Login required for 'mine' source")

        query = (
            select(Segment, Task.upload_name)
            .join(Task, Segment.task_id == Task.id)
            .where(Task.user_id == user_id, Task.stage.in_(["completed", "done"]))
        )

        # 排除已标注的
        rated_subquery = select(SegmentRating.segment_id).where(
            SegmentRating.user_id == user_id
        )
        query = query.where(Segment.id.notin_(rated_subquery))

        query = query.limit(limit)
        result = await db.execute(query)
        rows = result.all()

        segments = []
        for seg, upload_name in rows:
            duration = float(seg.end_time - seg.start_time) if seg.end_time and seg.start_time else 0.0
            audio_url = f"/api/segments/{seg.id}/clip" if seg.clip_path else ""
            segments.append(
                SwipeFeedSegment(
                    id=seg.id,
                    german_text=seg.german_text,
                    chinese_text=seg.chinese_text or "",
                    audio_url=audio_url,
                    difficulty=None,
                    source_title=upload_name or "",
                    duration=duration,
                )
            )

        total_rated_result = await db.execute(
            select(func.count()).select_from(SegmentRating).where(
                SegmentRating.user_id == user_id
            )
        )
        total_rated = total_rated_result.scalar() or 0

        return SwipeFeedResponse(
            segments=segments,
            current_level=current_level,
            total_rated=total_rated,
        )

    # ── source=public：从公开分享中获取 ──
    # 查询所有公开的、已完成的 Task 的 Segments
    # 通过 PublicShare 关联获取 difficulty
    query = (
        select(Segment, PublicShare.difficulty, PublicShare.title)
        .join(Task, Segment.task_id == Task.id)
        .join(PublicShare, PublicShare.task_id == Task.id)
        .where(Task.is_public == True, Task.stage.in_(["completed", "done"]))
    )

    # 如果指定了 level，只返回该难度
    if level:
        query = query.where(PublicShare.difficulty == level)
    else:
        # 80% 当前难度及以下 + 20% 更高难度
        current_idx = DIFFICULTY_LEVELS.index(current_level) if current_level in DIFFICULTY_LEVELS else 0
        lower_levels = DIFFICULTY_LEVELS[: current_idx + 1]
        higher_levels = DIFFICULTY_LEVELS[current_idx + 1 :]

        # 先查当前难度及以下的
        query_lower = query.where(PublicShare.difficulty.in_(lower_levels))
        # 再查更高难度的
        query_higher = query.where(PublicShare.difficulty.in_(higher_levels)) if higher_levels else None

        # 排除已标注的
        if user_id:
            rated_subquery = select(SegmentRating.segment_id).where(
                SegmentRating.user_id == user_id
            )
            query_lower = query_lower.where(Segment.id.notin_(rated_subquery))
            if query_higher is not None:
                query_higher = query_higher.where(Segment.id.notin_(rated_subquery))
        else:
            # 匿名用户：排除匿名标注
            rated_subquery = select(SegmentRating.segment_id).where(
                SegmentRating.user_id.is_(None)
            )
            query_lower = query_lower.where(Segment.id.notin_(rated_subquery))
            if query_higher is not None:
                query_higher = query_higher.where(Segment.id.notin_(rated_subquery))

        # 获取结果
        result_lower = await db.execute(query_lower)
        rows_lower = result_lower.all()

        rows_higher = []
        if query_higher is not None:
            result_higher = await db.execute(query_higher)
            rows_higher = result_higher.all()

        # 80/20 分配
        lower_count = max(int(limit * 0.8), 1)
        higher_count = limit - lower_count

        # 随机打乱
        random.shuffle(rows_lower)
        random.shuffle(rows_higher)

        selected = rows_lower[:lower_count] + rows_higher[:higher_count]
        random.shuffle(selected)

        # 构建 response
        segments = []
        for seg, difficulty, title in selected:
            duration = float(seg.end_time - seg.start_time) if seg.end_time and seg.start_time else 0.0
            audio_url = f"/api/segments/{seg.id}/clip" if seg.clip_path else ""
            segments.append(
                SwipeFeedSegment(
                    id=seg.id,
                    german_text=seg.german_text,
                    chinese_text=seg.chinese_text or "",
                    audio_url=audio_url,
                    difficulty=difficulty,
                    source_title=title or "",
                    duration=duration,
                )
            )

        # 获取 total_rated
        total_rated = 0
        if user_id:
            count_result = await db.execute(
                select(func.count()).select_from(SegmentRating).where(
                    SegmentRating.user_id == user_id
                )
            )
            total_rated = count_result.scalar() or 0

        return SwipeFeedResponse(
            segments=segments,
            current_level=current_level,
            total_rated=total_rated,
        )

    # 指定了 level 的情况
    # 排除已标注的
    if user_id:
        rated_subquery = select(SegmentRating.segment_id).where(
            SegmentRating.user_id == user_id
        )
        query = query.where(Segment.id.notin_(rated_subquery))
    else:
        rated_subquery = select(SegmentRating.segment_id).where(
            SegmentRating.user_id.is_(None)
        )
        query = query.where(Segment.id.notin_(rated_subquery))

    query = query.limit(limit)
    result = await db.execute(query)
    rows = result.all()

    segments = []
    for seg, difficulty, title in rows:
        duration = float(seg.end_time - seg.start_time) if seg.end_time and seg.start_time else 0.0
        audio_url = f"/api/segments/{seg.id}/clip" if seg.clip_path else ""
        segments.append(
            SwipeFeedSegment(
                id=seg.id,
                german_text=seg.german_text,
                chinese_text=seg.chinese_text or "",
                audio_url=audio_url,
                difficulty=difficulty,
                source_title=title or "",
                duration=duration,
            )
        )

    total_rated = 0
    if user_id:
        count_result = await db.execute(
            select(func.count()).select_from(SegmentRating).where(
                SegmentRating.user_id == user_id
            )
        )
        total_rated = count_result.scalar() or 0

    return SwipeFeedResponse(
        segments=segments,
        current_level=current_level,
        total_rated=total_rated,
    )


# ── POST /rate ──────────────────────────────────────────────────────────


@router.post("/rate")
async def rate_segment(
    body: SwipeRateRequest,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """标注片段难度（upsert）。"""
    user_id = user.id if user else None

    # 检查 segment 是否存在
    result = await db.execute(select(Segment).where(Segment.id == body.segment_id))
    segment = result.scalar_one_or_none()
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")

    # Upsert: 查找已有标注
    if user_id:
        existing_result = await db.execute(
            select(SegmentRating).where(
                SegmentRating.user_id == user_id,
                SegmentRating.segment_id == body.segment_id,
            )
        )
    else:
        existing_result = await db.execute(
            select(SegmentRating).where(
                SegmentRating.user_id.is_(None),
                SegmentRating.segment_id == body.segment_id,
            )
        )

    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.rating = body.rating
        await db.commit()
        await db.refresh(existing)
        return {"id": str(existing.id), "rating": existing.rating, "segment_id": str(existing.segment_id)}
    else:
        rating = SegmentRating(
            user_id=user_id,
            segment_id=body.segment_id,
            rating=body.rating,
            is_collected=False,
        )
        db.add(rating)
        await db.commit()
        await db.refresh(rating)
        return {"id": str(rating.id), "rating": rating.rating, "segment_id": str(rating.segment_id)}


# ── POST /collect ───────────────────────────────────────────────────────


@router.post("/collect")
async def collect_segment(
    body: SwipeCollectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """收藏片段（需要登录）。"""
    # 检查 segment 是否存在
    result = await db.execute(select(Segment).where(Segment.id == body.segment_id))
    segment = result.scalar_one_or_none()
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")

    # Upsert rating: 标记为 collected
    existing_result = await db.execute(
        select(SegmentRating).where(
            SegmentRating.user_id == user.id,
            SegmentRating.segment_id == body.segment_id,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.is_collected = True
        await db.commit()
        await db.refresh(existing)
        return {"id": str(existing.id), "is_collected": True, "segment_id": str(existing.segment_id)}
    else:
        rating = SegmentRating(
            user_id=user.id,
            segment_id=body.segment_id,
            rating="easy",
            is_collected=True,
        )
        db.add(rating)
        await db.commit()
        await db.refresh(rating)
        return {"id": str(rating.id), "is_collected": True, "segment_id": str(rating.segment_id)}


# ── GET /stats ──────────────────────────────────────────────────────────


@router.get("/stats", response_model=SwipeStatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """返回用户的标注统计信息。"""
    user_id = user.id if user else None

    if user_id:
        # 获取所有标注
        result = await db.execute(
            select(SegmentRating)
            .where(SegmentRating.user_id == user_id)
            .order_by(SegmentRating.created_at.asc())
        )
        ratings = result.scalars().all()
    else:
        # 匿名用户
        result = await db.execute(
            select(SegmentRating)
            .where(SegmentRating.user_id.is_(None))
            .order_by(SegmentRating.created_at.asc())
        )
        ratings = result.scalars().all()

    total_rated = len(ratings)
    easy_count = sum(1 for r in ratings if r.rating == "easy")
    hard_count = sum(1 for r in ratings if r.rating == "hard")

    # 计算连续 easy/hard（从最近往前数）
    consecutive_easy = 0
    consecutive_hard = 0
    for r in reversed(ratings):
        if r.rating == "easy":
            if consecutive_hard > 0:
                break
            consecutive_easy += 1
        elif r.rating == "hard":
            if consecutive_easy > 0:
                break
            consecutive_hard += 1

    current_level = await _get_user_level(db, user_id)

    return SwipeStatsResponse(
        current_level=current_level,
        total_rated=total_rated,
        easy_count=easy_count,
        hard_count=hard_count,
        consecutive_easy=consecutive_easy,
        consecutive_hard=consecutive_hard,
    )
