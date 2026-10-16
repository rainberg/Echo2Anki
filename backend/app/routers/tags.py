from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import Tag, Task, TaskTag, User
from app.schemas import TagCreate, TagResponse, TaskTagSet

router = APIRouter(prefix="/tags", tags=["tags"])


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: TagCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(Tag).where(Tag.user_id == user.id, Tag.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Tag already exists")

    tag = Tag(user_id=user.id, name=body.name, color=body.color)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return TagResponse.model_validate(tag)


@router.get("", response_model=list[TagResponse])
async def list_tags(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Tag).where(Tag.user_id == user.id).order_by(Tag.name)
    )
    return [TagResponse.model_validate(t) for t in result.scalars().all()]


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tag).where(Tag.id == tag_id, Tag.user_id == user.id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.delete(tag)
    await db.commit()


@router.post("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def set_task_tags(
    task_id: UUID,
    body: TaskTagSet,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task_result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    if not task_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Task not found")

    existing = await db.execute(select(TaskTag).where(TaskTag.task_id == task_id))
    for tt in existing.scalars().all():
        await db.delete(tt)

    for tag_id in body.tag_ids:
        tag_result = await db.execute(select(Tag).where(Tag.id == tag_id, Tag.user_id == user.id))
        if tag_result.scalar_one_or_none():
            db.add(TaskTag(task_id=task_id, tag_id=tag_id))

    await db.commit()


@router.get("/tasks/{task_id}", response_model=list[TagResponse])
async def get_task_tags(
    task_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task_result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    if not task_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(Tag)
        .join(TaskTag, TaskTag.tag_id == Tag.id)
        .where(TaskTag.task_id == task_id)
    )
    return [TagResponse.model_validate(t) for t in result.scalars().all()]
