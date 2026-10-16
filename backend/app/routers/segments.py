from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import Segment, Task, User
from app.schemas import SegmentResponse, SegmentUpdate

router = APIRouter(prefix="/segments", tags=["segments"])


@router.get("/{task_id}", response_model=list[SegmentResponse])
async def list_segments(
    task_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task_result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(Segment).where(Segment.task_id == task_id).order_by(Segment.seq_index)
    )
    segments = result.scalars().all()
    return [SegmentResponse.model_validate(s) for s in segments]


@router.patch("/{segment_id}", response_model=SegmentResponse)
async def update_segment(
    segment_id: UUID,
    body: SegmentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Segment)
        .join(Task, Segment.task_id == Task.id)
        .where(Segment.id == segment_id, Task.user_id == user.id)
    )
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    if body.chinese_text is not None:
        segment.chinese_text = body.chinese_text
    if body.german_text is not None:
        segment.german_text = body.german_text

    await db.commit()
    await db.refresh(segment)
    return SegmentResponse.model_validate(segment)


@router.post("/{segment_id}/translate", response_model=SegmentResponse)
async def translate_segment(
    segment_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Segment)
        .join(Task, Segment.task_id == Task.id)
        .where(Segment.id == segment_id, Task.user_id == user.id)
    )
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    if not segment.german_text:
        raise HTTPException(status_code=400, detail="No german text to translate")

    import asyncio

    from app.translation import translate_de_to_zh
    try:
        # 在线程池执行，避免同步 HTTP 调用阻塞事件循环
        translation = await asyncio.get_event_loop().run_in_executor(
            None, translate_de_to_zh, segment.german_text
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")
    if not translation:
        raise HTTPException(status_code=502, detail="Translation service unavailable, please retry later")

    segment.chinese_text = translation
    await db.commit()
    await db.refresh(segment)
    return SegmentResponse.model_validate(segment)
