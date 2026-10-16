import hashlib
import os
import shutil
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import Collection, CollectionItem, PushRecordItem, Segment, SystemSetting, Task, User
from app.schemas import (
    TaskDetailResponse,
    TaskListResponse,
    TaskResponse,
    TaskRetry,
    TaskUpdate,
    SegmentResponse,
    SegmentUpdate,
)
from app.billing import check_balance, estimate_cost, refund_all_reserved
from app.worker import get_worker

router = APIRouter(prefix="/tasks", tags=["tasks"])
bearer_scheme = HTTPBearer()

VALID_ENGINES = ["local_whisper", "openai_whisper", "cohere", "doubao"]
VALID_MODEL_SIZES = {
    "local_whisper": ["tiny", "base", "small", "medium", "large"],
    "openai_whisper": ["whisper-1"],
    "cohere": ["default"],
    "doubao": ["seedasr-2.0"],
}


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _user_upload_dir(user_id: UUID) -> str:
    d = os.path.join(settings.UPLOAD_DIR, str(user_id))
    os.makedirs(d, exist_ok=True)
    return d


def _user_task_dir(user_id: UUID, task_id: UUID) -> str:
    d = os.path.join(settings.TASK_DIR, str(user_id), str(task_id))
    os.makedirs(d, exist_ok=True)
    return d


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    file: UploadFile = File(...),
    engine: str = Form("local_whisper"),
    model_size: str = Form("small"),
    api_key: str = Form(""),
    skip_normalize: str = Form(""),
    title: str = Form(""),
    difficulty: str = Form(""),
    category: str = Form(""),
    user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    if engine not in VALID_ENGINES:
        raise HTTPException(status_code=400, detail=f"Invalid engine: {engine}")
    if engine not in (user.allowed_engines or []):
        raise HTTPException(status_code=403, detail=f"Engine '{engine}' not allowed for this user")
    if model_size not in VALID_MODEL_SIZES.get(engine, []):
        raise HTTPException(status_code=400, detail=f"Invalid model_size '{model_size}' for engine '{engine}'")

    upload_dir = _user_upload_dir(user.id)
    tmp_path = os.path.join(upload_dir, file.filename or "upload")
    with open(tmp_path, "wb") as f:
        content = await file.read()
        f.write(content)

    file_hash = _file_hash(tmp_path)
    file_size = os.path.getsize(tmp_path)

    existing = await db.execute(
        select(Task).where(Task.user_id == user.id, Task.file_hash == file_hash, Task.engine == engine)
    )
    existing_task = existing.scalar_one_or_none()
    if existing_task and existing_task.stage not in ("failed", "cancelled"):
        if os.path.exists(tmp_path) and tmp_path != existing_task.source_path:
            os.remove(tmp_path)
        return TaskResponse.model_validate(existing_task)

    if existing_task:
        task_dir = _user_task_dir(user.id, existing_task.id)
        for fname in os.listdir(task_dir):
            fpath = os.path.join(task_dir, fname)
            if os.path.isdir(fpath):
                shutil.rmtree(fpath, ignore_errors=True)
            elif fname != os.path.basename(existing_task.source_path or ""):
                os.remove(fpath)

    duration_estimate = Decimal(str(file_size)) / Decimal("16000") * Decimal("1.2")

    task = Task(
        user_id=user.id,
        upload_name=file.filename or "upload",
        title=title or "",
        difficulty=difficulty or "",
        category=category or "",
        file_hash=file_hash,
        file_size_bytes=file_size,
        engine=engine,
        model_size=model_size,
        stage="pending",
        progress=Decimal("0"),
        source_path=tmp_path,
    )

    if existing_task:
        existing_task.stage = "pending"
        existing_task.progress = Decimal("0")
        existing_task.engine = engine
        existing_task.model_size = model_size
        existing_task.error = ""
        existing_task.stage_message = ""
        existing_task.started_at = None
        existing_task.finished_at = None
        existing_task.source_path = tmp_path
        existing_task.upload_name = file.filename or "upload"
        existing_task.file_size_bytes = file_size
        await db.commit()
        await db.refresh(existing_task)
        task = existing_task
    else:
        db.add(task)
        await db.commit()
        await db.refresh(task)

    try:
        estimated_cost = await estimate_cost(db, duration_estimate, engine, model_size)
        await check_balance(credentials.credentials, estimated_cost)
    except ValueError as e:
        task.stage = "failed"
        task.error = str(e)
        await db.commit()
        await db.refresh(task)
        raise HTTPException(status_code=402, detail=str(e))

    task_dir = _user_task_dir(user.id, task.id)
    dest = os.path.join(task_dir, file.filename or "upload")
    if not os.path.exists(dest):
        shutil.copy2(tmp_path, dest)
    task.source_path = dest
    await db.commit()

    # Fallback to system OpenAI key if user didn't provide one
    effective_api_key = api_key
    if engine == "openai_whisper" and not api_key:
        result = await db.execute(select(SystemSetting).where(SystemSetting.key == "openai_api_key"))
        sys_key = result.scalar_one_or_none()
        if sys_key and sys_key.value:
            effective_api_key = sys_key.value

    worker = get_worker()
    worker.submit(str(task.id), dest, engine, model_size, effective_api_key, credentials.credentials, skip_normalize=bool(skip_normalize))

    return TaskResponse.model_validate(task)


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    page: int = 1,
    per_page: int = 20,
    stage: str = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Task).where(Task.user_id == user.id)
    count_query = select(func.count()).select_from(Task).where(Task.user_id == user.id)

    if stage:
        query = query.where(Task.stage == stage)
        count_query = count_query.where(Task.stage == stage)

    total = (await db.execute(count_query)).scalar()
    query = query.order_by(Task.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    tasks = result.scalars().all()

    return TaskListResponse(
        items=[TaskResponse.model_validate(t) for t in tasks],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(
    task_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    segments = await db.execute(
        select(Segment).where(Segment.task_id == task_id).order_by(Segment.seq_index)
    )
    seg_list = segments.scalars().all()

    seg_ids = [s.id for s in seg_list]
    collected_ids = set()
    pushed_ids = set()
    pushed_at_map = {}
    if seg_ids:
        coll_result = await db.execute(
            select(CollectionItem.segment_id)
            .join(CollectionItem.collection)
            .where(CollectionItem.segment_id.in_(seg_ids), Collection.user_id == user.id)
        )
        collected_ids = {row[0] for row in coll_result.all()}

        push_result = await db.execute(
            select(PushRecordItem.segment_id, PushRecordItem.created_at)
            .where(PushRecordItem.segment_id.in_(seg_ids), PushRecordItem.status == "pushed")
            .order_by(PushRecordItem.created_at.desc())
        )
        for row in push_result.all():
            sid, pushed_at = row[0], row[1]
            pushed_ids.add(sid)
            if sid not in pushed_at_map or pushed_at > pushed_at_map[sid]:
                pushed_at_map[sid] = pushed_at

    resp = TaskDetailResponse.model_validate(task)
    resp.segments = []
    for s in seg_list:
        sr = SegmentResponse.model_validate(s)
        sr.collected = s.id in collected_ids
        sr.pushed = s.id in pushed_ids
        sr.last_pushed_at = pushed_at_map.get(s.id)
        resp.segments.append(sr)
    return resp


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    body: TaskUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if body.is_public is not None:
        task.is_public = body.is_public
    if body.title is not None:
        task.title = body.title
    if body.difficulty is not None:
        task.difficulty = body.difficulty
    if body.category is not None:
        task.category = body.category
    await db.commit()
    await db.refresh(task)
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.stage not in ("done", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail="Cannot delete a running task")

    # Delete dependent records in order (foreign key constraints)
    # 1. Push record items referencing segments of this task
    seg_result = await db.execute(select(Segment.id).where(Segment.task_id == task_id))
    seg_ids = [row[0] for row in seg_result.all()]
    if seg_ids:
        await db.execute(PushRecordItem.__table__.delete().where(PushRecordItem.segment_id.in_(seg_ids)))
        # 2. Collection items referencing segments of this task
        await db.execute(CollectionItem.__table__.delete().where(CollectionItem.segment_id.in_(seg_ids)))

    # 3. Task tags
    from app.models import TaskTag
    await db.execute(TaskTag.__table__.delete().where(TaskTag.task_id == task_id))

    # 4. Segments (cascade from task should handle this, but explicit for safety)
    await db.execute(Segment.__table__.delete().where(Segment.task_id == task_id))

    # 5. Push records referencing this task
    from app.models import PushRecord
    await db.execute(PushRecord.__table__.delete().where(PushRecord.task_id == task_id))

    # 6. Public shares referencing this task
    from app.models import PublicShare
    await db.execute(PublicShare.__table__.delete().where(PublicShare.task_id == task_id))

    # 7. Billing records referencing this task (nullify task_id first)
    from app.models import BillingRecord
    await db.execute(BillingRecord.__table__.update().where(BillingRecord.task_id == task_id).values(task_id=None))

    # 8. Finally delete the task itself
    await db.delete(task)
    await db.commit()

    # Clean up files
    task_dir = os.path.join(settings.TASK_DIR, str(user.id), str(task_id))
    if os.path.isdir(task_dir):
        shutil.rmtree(task_dir, ignore_errors=True)


@router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(
    task_id: UUID,
    body: TaskRetry = None,
    user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.stage not in ("failed", "cancelled"):
        raise HTTPException(status_code=400, detail="Can only retry failed or cancelled tasks")

    engine = (body.engine if body else None) or task.engine
    model_size = (body.model_size if body else None) or task.model_size
    api_key = (body.api_key if body else None) or ""

    if engine not in (user.allowed_engines or []):
        raise HTTPException(status_code=403, detail=f"Engine '{engine}' not allowed")

    if task.credits_reserved and task.credits_reserved > 0:
        await refund_all_reserved(db, task.user_id, task.id, task.credits_reserved, credentials.credentials, task.reserve_reference_id)
        task.credits_reserved = Decimal("0")
        task.reserve_reference_id = None

    duration_estimate = Decimal(str(task.file_size_bytes or 0)) / Decimal("16000") * Decimal("1.2")
    if duration_estimate <= 0:
        duration_estimate = Decimal("60")

    try:
        estimated_cost = await estimate_cost(db, duration_estimate, engine, model_size)
        await check_balance(credentials.credentials, estimated_cost)
    except ValueError as e:
        raise HTTPException(status_code=402, detail=str(e))

    task.stage = "pending"
    task.progress = Decimal("0")
    task.engine = engine
    task.model_size = model_size
    task.error = ""
    task.stage_message = ""
    task.started_at = None
    task.finished_at = None
    await db.commit()
    await db.refresh(task)

    # 清理之前取消时遗留的 cancel.json，避免 worker 立即再次取消任务
    task_dir = os.path.join(settings.TASK_DIR, str(user.id), str(task_id))
    cancel_flag = os.path.join(task_dir, "cancel.json")
    if os.path.exists(cancel_flag):
        os.remove(cancel_flag)

    # Fallback to system OpenAI key if user didn't provide one
    effective_api_key = api_key
    if engine == "openai_whisper" and not api_key:
        result = await db.execute(select(SystemSetting).where(SystemSetting.key == "openai_api_key"))
        sys_key = result.scalar_one_or_none()
        if sys_key and sys_key.value:
            effective_api_key = sys_key.value

    worker = get_worker()
    worker.submit(str(task.id), task.source_path, engine, model_size, effective_api_key, credentials.credentials)

    return TaskResponse.model_validate(task)


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: UUID,
    user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.stage in ("done", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail="Task already finished")

    task_dir = os.path.join(settings.TASK_DIR, str(user.id), str(task_id))
    cancel_flag = os.path.join(task_dir, "cancel.json")
    os.makedirs(task_dir, exist_ok=True)
    with open(cancel_flag, "w") as f:
        f.write('{"cancelled_at": "' + datetime.now(timezone.utc).isoformat() + '"}')

    if task.credits_reserved and task.credits_reserved > 0 and not task.started_at:
        await refund_all_reserved(db, task.user_id, task.id, task.credits_reserved, credentials.credentials, task.reserve_reference_id)
        task.credits_reserved = Decimal("0")
        task.reserve_reference_id = None

    task.stage = "cancelled"
    task.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)

    return TaskResponse.model_validate(task)
