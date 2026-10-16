import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import (
    AnkiPushConfig,
    Collection,
    CollectionItem,
    PushRecord,
    PushRecordItem,
    Segment,
    Task,
    User,
)

STREAMLIT_WORK_DIR = "/var/lib/anki-streamlit-subtitle/tasks"

engine = create_async_engine(settings.DATABASE_URL, echo=False)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def find_user_by_email_or_create(email: str, display_name: str) -> User:
    async with Session() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            return user
        user = User(
            id=uuid4(),
            email=email,
            display_name=display_name,
            role="user",
            credits=0,
            credits_reserved=0,
            allowed_engines=["local_whisper"],
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def migrate_streamlit_tasks(user_email: str = None, dry_run: bool = False):
    if not os.path.isdir(STREAMLIT_WORK_DIR):
        print(f"Streamlit work dir not found: {STREAMLIT_WORK_DIR}")
        return

    manifests = []
    for manifest_path in Path(STREAMLIT_WORK_DIR).glob("*/manifest.json"):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if data.get("segments"):
                manifests.append(data)
        except Exception as e:
            print(f"  [WARN] Cannot read {manifest_path}: {e}")

    manifests.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
    print(f"Found {len(manifests)} Streamlit tasks with segments")

    if user_email:
        user = await find_user_by_email_or_create(user_email, "Streamlit User")
    else:
        async with Session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
        if not user:
            print("No users found in database. Please specify --user-email")
            return

    stats = {"tasks_created": 0, "tasks_existing": 0, "segments_created": 0, "collections_created": 0, "push_records_created": 0, "push_items_created": 0}

    for manifest in manifests:
        task_id_str = manifest.get("task_id", "")
        upload_name = manifest.get("upload_name", task_id_str)
        segments_data = manifest.get("segments", [])
        translations = manifest.get("translations", [])
        favorites = manifest.get("favorites", [])
        push_excluded = manifest.get("push_excluded", [])
        audio_dir = manifest.get("audio_dir", "")

        pushed_indices = [idx for idx in favorites if idx not in push_excluded]

        async with Session() as db:
            existing = await db.execute(
                select(Task).where(Task.user_id == user.id, Task.upload_name == upload_name)
            )
            existing_task = existing.scalar_one_or_none()

            if existing_task:
                stats["tasks_existing"] += 1
                task = existing_task
            else:
                file_hash = hashlib.sha256(upload_name.encode()).hexdigest()
                task = Task(
                    id=uuid4(),
                    user_id=user.id,
                    upload_name=upload_name,
                    file_hash=file_hash,
                    engine="local_whisper",
                    model_size="small",
                    stage="done",
                    progress=1.0,
                    segment_count=len(segments_data),
                    is_public=False,
                )
                db.add(task)
                await db.commit()
                await db.refresh(task)
                stats["tasks_created"] += 1

            existing_segs = await db.execute(
                select(Segment).where(Segment.task_id == task.id)
            )
            existing_seg_list = existing_segs.scalars().all()

            if not existing_seg_list:
                for idx, seg in enumerate(segments_data):
                    clip_filename = f"clip_{idx + 1:03d}.mp3"
                    clip_path = ""
                    if audio_dir and os.path.isdir(audio_dir):
                        clip_full = os.path.join(audio_dir, clip_filename)
                        if os.path.exists(clip_full):
                            rel = os.path.relpath(clip_full, settings.TASK_DIR)
                            clip_path = rel

                    seg_record = Segment(
                        id=uuid4(),
                        task_id=task.id,
                        seq_index=idx,
                        start_time=seg.get("start", 0),
                        end_time=seg.get("end", 0),
                        german_text=seg.get("text", ""),
                        chinese_text=translations[idx] if idx < len(translations) else "",
                        clip_path=clip_path,
                    )
                    db.add(seg_record)
                    stats["segments_created"] += 1
                await db.commit()

                existing_segs = await db.execute(
                    select(Segment).where(Segment.task_id == task.id).order_by(Segment.seq_index)
                )
                existing_seg_list = existing_segs.scalars().all()

            if pushed_indices and existing_seg_list:
                coll_name = f"Streamlit - {upload_name}"
                existing_coll = await db.execute(
                    select(Collection).where(Collection.user_id == user.id, Collection.name == coll_name)
                )
                coll = existing_coll.scalar_one_or_none()

                if not coll:
                    coll = Collection(
                        id=uuid4(),
                        user_id=user.id,
                        name=coll_name,
                        description="从 Streamlit 字幕版迁移的推送历史",
                    )
                    db.add(coll)
                    await db.commit()
                    await db.refresh(coll)
                    stats["collections_created"] += 1

                pushed_seg_ids = []
                for idx in pushed_indices:
                    if idx < len(existing_seg_list):
                        seg = existing_seg_list[idx]
                        existing_item = await db.execute(
                            select(CollectionItem).where(
                                CollectionItem.collection_id == coll.id,
                                CollectionItem.segment_id == seg.id,
                            )
                        )
                        if not existing_item.scalar_one_or_none():
                            item = CollectionItem(
                                id=uuid4(),
                                collection_id=coll.id,
                                segment_id=seg.id,
                                push_enabled=True,
                            )
                            db.add(item)
                        pushed_seg_ids.append(seg.id)

                await db.commit()

                if pushed_seg_ids:
                    existing_push = await db.execute(
                        select(PushRecord).where(PushRecord.collection_id == coll.id)
                    )
                    if not existing_push.scalar_one_or_none():
                        push_config = await db.execute(
                            select(AnkiPushConfig).where(AnkiPushConfig.user_id == user.id)
                        )
                        config = push_config.scalar_one_or_none()

                        push_record = PushRecord(
                            id=uuid4(),
                            user_id=user.id,
                            task_id=task.id,
                            collection_id=coll.id,
                            config_id=config.id if config else None,
                            push_mode="self_hosted",
                            deck_name="Deutsch Listening",
                            card_count=len(pushed_seg_ids),
                            status="done",
                        )
                        db.add(push_record)
                        await db.commit()
                        await db.refresh(push_record)
                        stats["push_records_created"] += 1

                        for seg_id in pushed_seg_ids:
                            item_rec = PushRecordItem(
                                id=uuid4(),
                                push_record_id=push_record.id,
                                segment_id=seg_id,
                                status="pushed",
                            )
                            db.add(item_rec)
                            stats["push_items_created"] += 1
                        await db.commit()

    print("\n=== Migration Summary ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if dry_run:
        print("  (DRY RUN - no changes were made)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate Streamlit push history to Web App")
    parser.add_argument("--user-email", type=str, help="User email to associate migrated data with")
    parser.add_argument("--dry-run", action="store_true", help="Only analyze, don't write")
    args = parser.parse_args()

    asyncio.run(migrate_streamlit_tasks(user_email=args.user_email, dry_run=args.dry_run))
