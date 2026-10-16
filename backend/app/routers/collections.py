from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import Collection, CollectionItem, PushRecord, Segment, Task, User
from app.schemas import (
    CollectionCreate,
    CollectionDetailResponse,
    CollectionItemAdd,
    CollectionItemResponse,
    CollectionItemToggle,
    CollectionResponse,
    CollectionUpdate,
    SegmentResponse,
)

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post("", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_collection(
    body: CollectionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    coll = Collection(user_id=user.id, name=body.name, description=body.description)
    db.add(coll)
    await db.commit()
    await db.refresh(coll)

    resp = CollectionResponse.model_validate(coll)
    resp.item_count = 0
    return resp


@router.get("", response_model=list[CollectionResponse])
async def list_collections(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Collection).where(Collection.user_id == user.id).order_by(Collection.updated_at.desc())
    )
    collections = result.scalars().all()

    resp_list = []
    for coll in collections:
        count_result = await db.execute(
            select(func.count()).select_from(CollectionItem).where(CollectionItem.collection_id == coll.id)
        )
        item_count = count_result.scalar() or 0
        r = CollectionResponse.model_validate(coll)
        r.item_count = item_count
        resp_list.append(r)
    return resp_list


@router.get("/{collection_id}", response_model=CollectionDetailResponse)
async def get_collection(
    collection_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id)
    )
    coll = result.scalar_one_or_none()
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")

    items_result = await db.execute(
        select(CollectionItem)
        .where(CollectionItem.collection_id == collection_id)
        .order_by(CollectionItem.added_at.desc())
    )
    items = items_result.scalars().all()

    item_responses = []
    for item in items:
        seg_result = await db.execute(select(Segment).where(Segment.id == item.segment_id))
        seg = seg_result.scalar_one_or_none()
        ir = CollectionItemResponse(
            id=item.id,
            segment_id=item.segment_id,
            push_enabled=item.push_enabled,
            added_at=item.added_at,
            segment=SegmentResponse.model_validate(seg) if seg else None,
        )
        item_responses.append(ir)

    count_result = await db.execute(
        select(func.count()).select_from(CollectionItem).where(CollectionItem.collection_id == coll.id)
    )
    resp = CollectionDetailResponse.model_validate(coll)
    resp.item_count = count_result.scalar() or 0
    resp.items = item_responses
    return resp


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: UUID,
    body: CollectionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id)
    )
    coll = result.scalar_one_or_none()
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")

    if body.name is not None:
        coll.name = body.name
    if body.description is not None:
        coll.description = body.description
    coll.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(coll)

    count_result = await db.execute(
        select(func.count()).select_from(CollectionItem).where(CollectionItem.collection_id == coll.id)
    )
    resp = CollectionResponse.model_validate(coll)
    resp.item_count = count_result.scalar() or 0
    return resp


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id)
    )
    coll = result.scalar_one_or_none()
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")
    # 清理关联的推送记录
    pr_result = await db.execute(
        select(PushRecord).where(PushRecord.collection_id == collection_id)
    )
    for pr in pr_result.scalars().all():
        await db.delete(pr)
    await db.delete(coll)
    await db.commit()


@router.post("/batch-delete", status_code=status.HTTP_204_NO_CONTENT)
async def batch_delete_collections(
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    collection_ids = body.get("collection_ids", [])
    if not collection_ids:
        return
    uuids = [UUID(cid) for cid in collection_ids]
    result = await db.execute(
        select(Collection).where(
            Collection.id.in_(uuids),
            Collection.user_id == user.id,
        )
    )
    colls = result.scalars().all()
    if not colls:
        return
    # 清理关联的推送记录
    pr_result = await db.execute(
        select(PushRecord).where(PushRecord.collection_id.in_(uuids))
    )
    for pr in pr_result.scalars().all():
        await db.delete(pr)
    for coll in colls:
        await db.delete(coll)
    await db.commit()


@router.post("/{collection_id}/items", response_model=list[CollectionItemResponse])
async def add_items(
    collection_id: UUID,
    body: CollectionItemAdd,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id)
    )
    coll = result.scalar_one_or_none()
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")

    added = []
    for seg_id in body.segment_ids:
        existing = await db.execute(
            select(CollectionItem).where(
                CollectionItem.collection_id == collection_id,
                CollectionItem.segment_id == seg_id,
            )
        )
        if existing.scalar_one_or_none():
            continue

        seg_result = await db.execute(select(Segment).where(Segment.id == seg_id))
        seg = seg_result.scalar_one_or_none()
        if not seg:
            continue

        task_result = await db.execute(select(Task).where(Task.id == seg.task_id, Task.user_id == user.id))
        if not task_result.scalar_one_or_none():
            continue

        dup_result = await db.execute(
            select(CollectionItem)
            .join(CollectionItem.segment)
            .where(
                CollectionItem.collection_id == collection_id,
                Segment.german_text == seg.german_text,
            )
        )
        if dup_result.scalar_one_or_none():
            continue

        item = CollectionItem(collection_id=collection_id, segment_id=seg_id, push_enabled=True)
        db.add(item)
        added.append(item)

    if added:
        coll.updated_at = datetime.now(timezone.utc)
        await db.commit()
        for item in added:
            await db.refresh(item)

    resp_list = []
    for item in added:
        seg_result = await db.execute(select(Segment).where(Segment.id == item.segment_id))
        seg = seg_result.scalar_one_or_none()
        ir = CollectionItemResponse(
            id=item.id,
            segment_id=item.segment_id,
            push_enabled=item.push_enabled,
            added_at=item.added_at,
            segment=SegmentResponse.model_validate(seg) if seg else None,
        )
        resp_list.append(ir)
    return resp_list


@router.delete("/{collection_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item(
    collection_id: UUID,
    item_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CollectionItem).where(
            CollectionItem.id == item_id,
            CollectionItem.collection_id == collection_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    coll_result = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id)
    )
    if not coll_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Collection not found")

    await db.delete(item)
    await db.commit()


@router.post("/{collection_id}/items/batch-delete", status_code=status.HTTP_204_NO_CONTENT)
async def batch_remove_items(
    collection_id: UUID,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    coll_result = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id)
    )
    if not coll_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Collection not found")

    item_ids = body.get("item_ids", [])
    if not item_ids:
        return

    result = await db.execute(
        select(CollectionItem).where(
            CollectionItem.id.in_([UUID(iid) for iid in item_ids]),
            CollectionItem.collection_id == collection_id,
        )
    )
    for item in result.scalars().all():
        await db.delete(item)
    await db.commit()


@router.patch("/{collection_id}/items/{item_id}", response_model=CollectionItemResponse)
async def toggle_item(
    collection_id: UUID,
    item_id: UUID,
    body: CollectionItemToggle,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CollectionItem).where(
            CollectionItem.id == item_id,
            CollectionItem.collection_id == collection_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    coll_result = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id)
    )
    if not coll_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Collection not found")

    item.push_enabled = body.push_enabled
    await db.commit()
    await db.refresh(item)

    seg_result = await db.execute(select(Segment).where(Segment.id == item.segment_id))
    seg = seg_result.scalar_one_or_none()
    return CollectionItemResponse(
        id=item.id,
        segment_id=item.segment_id,
        push_enabled=item.push_enabled,
        added_at=item.added_at,
        segment=SegmentResponse.model_validate(seg) if seg else None,
    )
