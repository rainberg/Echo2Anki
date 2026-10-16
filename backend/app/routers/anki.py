import os
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.crypto import decrypt_credential, encrypt_credential
from app.database import get_db
from app.deps import get_current_user
from app.models import AnkiPushConfig, Collection, CollectionItem, PushRecord, PushRecordItem, Segment, Task, User
from app.schemas_push import (
    PushConfigCreate,
    PushConfigResponse,
    PushConfigUpdate,
    PushRecordResponse,
    PushRequest,
    PushStatusResponse,
    PushStatusItem,
)

router = APIRouter(prefix="/anki", tags=["anki"])


def _auto_name(push_mode: str, existing_count: int) -> str:
    mode_label = "自建服务器" if push_mode == "self_hosted" else "AnkiWeb"
    return f"{mode_label} #{existing_count + 1}"


@router.post("/configs", response_model=PushConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_push_config(
    body: PushConfigCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check config count limit
    count_result = await db.execute(
        select(func.count()).select_from(AnkiPushConfig).where(AnkiPushConfig.user_id == user.id)
    )
    current_count = count_result.scalar()
    max_configs = user.max_push_configs or 4
    if current_count >= max_configs:
        raise HTTPException(
            status_code=429,
            detail=f"已达到配置上限 ({max_configs} 个)，请联系管理员提升限额",
        )

    # Auto-generate name if empty
    name = body.name.strip() if body.name else ""
    if not name:
        name = _auto_name(body.push_mode, current_count)

    config = AnkiPushConfig(
        user_id=user.id,
        name=name,
        push_mode=body.push_mode,
        deck_name=body.deck_name,
        sync_username=body.sync_username,
        sync_password_enc=encrypt_credential(body.sync_password) if body.sync_password else "",
        ankiweb_username=body.ankiweb_username,
        ankiweb_password_enc=encrypt_credential(body.ankiweb_password) if body.ankiweb_password else "",
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    return _config_response(config)


@router.get("/configs", response_model=list[PushConfigResponse])
async def list_push_configs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnkiPushConfig).where(AnkiPushConfig.user_id == user.id)
    )
    return [_config_response(c) for c in result.scalars().all()]


@router.patch("/configs/{config_id}", response_model=PushConfigResponse)
async def update_push_config(
    config_id: UUID,
    body: PushConfigUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnkiPushConfig).where(AnkiPushConfig.id == config_id, AnkiPushConfig.user_id == user.id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    if body.name is not None:
        config.name = body.name
    if body.deck_name is not None:
        config.deck_name = body.deck_name
    if body.sync_username is not None:
        config.sync_username = body.sync_username
    if body.sync_password is not None:
        config.sync_password_enc = encrypt_credential(body.sync_password)
    if body.ankiweb_username is not None:
        config.ankiweb_username = body.ankiweb_username
    if body.ankiweb_password is not None:
        config.ankiweb_password_enc = encrypt_credential(body.ankiweb_password)

    config.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(config)

    return _config_response(config)


@router.delete("/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_push_config(
    config_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnkiPushConfig).where(AnkiPushConfig.id == config_id, AnkiPushConfig.user_id == user.id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    await db.delete(config)
    await db.commit()


@router.post("/push", response_model=list[PushRecordResponse])
async def push_to_anki(
    body: PushRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate collection
    coll_result = await db.execute(
        select(Collection).where(Collection.id == body.collection_id, Collection.user_id == user.id)
    )
    collection = coll_result.scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Get push-enabled items
    items_result = await db.execute(
        select(CollectionItem).where(
            CollectionItem.collection_id == body.collection_id,
            CollectionItem.push_enabled == True,
        )
    )
    items = items_result.scalars().all()
    if not items:
        raise HTTPException(status_code=400, detail="No push-enabled items in collection")

    # Prepare segments data
    segments_data = []
    segment_ids = []
    for item in items:
        seg_result = await db.execute(select(Segment).where(Segment.id == item.segment_id))
        seg = seg_result.scalar_one_or_none()
        if seg and seg.clip_path:
            audio_path = os.path.join(settings.TASK_DIR, seg.clip_path)
            segments_data.append({
                "segment_id": seg.id,
                "audio_filename": os.path.basename(audio_path),
                "german_text": seg.german_text,
                "chinese_text": seg.chinese_text,
                "audio_dir": os.path.dirname(audio_path),
            })
            segment_ids.append(seg.id)

    # Fetch all requested configs
    config_result = await db.execute(
        select(AnkiPushConfig).where(
            AnkiPushConfig.id.in_(body.config_ids),
            AnkiPushConfig.user_id == user.id,
        )
    )
    configs = config_result.scalars().all()
    if len(configs) != len(body.config_ids):
        found_ids = {str(c.id) for c in configs}
        missing = [str(cid) for cid in body.config_ids if str(cid) not in found_ids]
        raise HTTPException(status_code=400, detail=f"Invalid config IDs: {missing}")

    # Push to each config
    records = []
    for config in configs:
        # 查询该 config 下已成功推送过的 segment_ids
        if not body.force and segment_ids:
            pushed_result = await db.execute(
                select(PushRecordItem.segment_id)
                .join(PushRecord)
                .where(
                    PushRecord.config_id == config.id,
                    PushRecord.status == "done",
                    PushRecordItem.status == "pushed",
                    PushRecordItem.segment_id.in_(segment_ids),
                )
            )
            pushed_ids = {row[0] for row in pushed_result.all()}
            config_segments = [s for s in segments_data if s["segment_id"] not in pushed_ids]
            skipped_count = len(segments_data) - len(config_segments)
        else:
            config_segments = segments_data
            skipped_count = 0

        record = PushRecord(
            user_id=user.id,
            collection_id=body.collection_id,
            config_id=config.id,
            push_mode=config.push_mode,
            deck_name=config.deck_name,
            status="pending",
            card_count=0,
            skipped_count=skipped_count,
            created_at=datetime.now(timezone.utc),
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

        # 没有需要推送的句子（全部已推送且非 force）
        if not config_segments:
            record.status = "done"
            record.card_count = 0
            record.duration_ms = 0
            await db.commit()
            await db.refresh(record)
            records.append(PushRecordResponse.model_validate(record))
            continue

        # 提取不含 segment_id 的数据传给推送函数
        push_data = [
            {k: v for k, v in s.items() if k != "segment_id"}
            for s in config_segments
        ]
        pushed_seg_ids = [s["segment_id"] for s in config_segments]

        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if config.push_mode == "self_hosted":
                cards_count = await loop.run_in_executor(
                    None, _push_self_hosted_sync, push_data, config, config.deck_name, user.id
                )
            else:
                cards_count = await loop.run_in_executor(
                    None, _push_ankiweb_sync, push_data, config, config.deck_name, user.id
                )

            record.status = "done"
            record.card_count = cards_count
            record.duration_ms = int((datetime.now(timezone.utc) - record.created_at).total_seconds() * 1000)

            for seg_id in pushed_seg_ids:
                item_rec = PushRecordItem(
                    push_record_id=record.id,
                    segment_id=seg_id,
                    status="pushed",
                )
                db.add(item_rec)
        except Exception as e:
            record.status = "failed"
            record.error_message = str(e)[:500]
            record.duration_ms = int((datetime.now(timezone.utc) - record.created_at).total_seconds() * 1000)

            for seg_id in pushed_seg_ids:
                item_rec = PushRecordItem(
                    push_record_id=record.id,
                    segment_id=seg_id,
                    status="failed",
                )
                db.add(item_rec)

        await db.commit()
        await db.refresh(record)
        records.append(PushRecordResponse.model_validate(record))

    return records


@router.get("/push-status", response_model=PushStatusResponse)
async def get_push_status(
    collection_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询收藏集内句子在各个推送配置下的已推送情况"""
    coll_result = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id)
    )
    if not coll_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Collection not found")

    # 获取 push_enabled 的 segment_ids
    items_result = await db.execute(
        select(CollectionItem.segment_id).where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.push_enabled == True,
        )
    )
    segment_ids = [row[0] for row in items_result.all()]
    total_items = len(segment_ids)

    # 获取用户所有配置
    config_result = await db.execute(
        select(AnkiPushConfig).where(AnkiPushConfig.user_id == user.id)
    )
    configs = config_result.scalars().all()

    config_statuses = []
    for cfg in configs:
        if segment_ids:
            pushed_result = await db.execute(
                select(func.count(func.distinct(PushRecordItem.segment_id)))
                .join(PushRecord)
                .where(
                    PushRecord.config_id == cfg.id,
                    PushRecord.status == "done",
                    PushRecordItem.status == "pushed",
                    PushRecordItem.segment_id.in_(segment_ids),
                )
            )
            pushed_count = pushed_result.scalar() or 0
        else:
            pushed_count = 0
        config_statuses.append(PushStatusItem(
            config_id=cfg.id,
            pushed_count=pushed_count,
            unpushed_count=total_items - pushed_count,
        ))

    return PushStatusResponse(total_items=total_items, configs=config_statuses)


@router.get("/records", response_model=list[PushRecordResponse])
async def list_push_records(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    coll_result = await db.execute(
        select(Collection).where(Collection.user_id == user.id)
    )
    coll_ids = [c.id for c in coll_result.scalars().all()]

    if not coll_ids:
        return []

    result = await db.execute(
        select(PushRecord)
        .where(PushRecord.collection_id.in_(coll_ids))
        .order_by(PushRecord.created_at.desc())
        .limit(50)
    )
    return [PushRecordResponse.model_validate(r) for r in result.scalars().all()]


def _config_response(config: AnkiPushConfig) -> PushConfigResponse:
    return PushConfigResponse(
        id=config.id,
        name=config.name or "",
        push_mode=config.push_mode,
        deck_name=config.deck_name,
        sync_username=config.sync_username,
        ankiweb_username=config.ankiweb_username,
        has_sync_password=bool(config.sync_password_enc),
        has_ankiweb_password=bool(config.ankiweb_password_enc),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def _push_self_hosted_sync(segments_data, config, deck_name, user_id) -> int:
    if not segments_data:
        return 0

    import sys
    anki_app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    if anki_app_dir not in sys.path:
        sys.path.insert(0, anki_app_dir)

    from anki_push_router import push_cards_to_server

    sync_username = config.sync_username or ""
    sync_password = decrypt_credential(config.sync_password_enc) if config.sync_password_enc else ""

    os.environ["ANKI_SYNC_USERNAME"] = sync_username
    os.environ["ANKI_SYNC_PASSWORD"] = sync_password
    os.environ["ANKI_PUSH_MODE"] = "sync_client"

    # 每个句子携带自己的 audio_dir，支持跨任务收藏集
    audio_dir = segments_data[0]["audio_dir"]
    sentences = []
    for seg in segments_data:
        sentences.append({
            "audio_filename": seg["audio_filename"],
            "audio_dir": seg["audio_dir"],
            "german_text": seg["german_text"],
            "chinese_text": seg["chinese_text"],
        })

    result = push_cards_to_server(sentences, audio_dir, deck_name)
    if not result.get("success"):
        raise RuntimeError(result.get("message", "Push failed"))
    return result.get("count", len(sentences))


def _push_ankiweb_sync(segments_data, config, deck_name, user_id) -> int:
    if not segments_data:
        return 0

    import sys
    anki_app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    if anki_app_dir not in sys.path:
        sys.path.insert(0, anki_app_dir)

    from ankiweb_push import push_cards_to_ankiweb

    ankiweb_password = decrypt_credential(config.ankiweb_password_enc) if config.ankiweb_password_enc else ""
    audio_dir = segments_data[0]["audio_dir"]
    sentences = []
    for seg in segments_data:
        sentences.append({
            "audio_filename": seg["audio_filename"],
            "audio_dir": seg["audio_dir"],
            "german_text": seg["german_text"],
            "chinese_text": seg["chinese_text"],
        })

    result = push_cards_to_ankiweb(
        sentences=sentences,
        audio_dir=audio_dir,
        deck_name=deck_name,
        username=config.ankiweb_username,
        password=ankiweb_password,
    )
    if not result.get("success"):
        raise RuntimeError(result.get("message", "Push failed"))
    return result.get("count", len(sentences))
