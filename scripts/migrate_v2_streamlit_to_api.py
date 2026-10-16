#!/usr/bin/env python3
"""
Migrate V2 Streamlit tasks from /var/lib/anki-v2/tasks/ into V2 PostgreSQL API.
Assigns all tasks to the Guangrui user (ooJerry@gmail.com).
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

sys.path.insert(0, "/opt/anki-app/backend")

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Segment, Task, User

GUANGRUI_USER_ID = "fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f"
V2_TASKS_DIR = "/var/lib/anki-v2/tasks"
UPLOAD_DIR = settings.UPLOAD_DIR
TASK_DIR = settings.TASK_DIR

SYNC_DB_URL = settings.DATABASE_URL_SYNC


def get_audio_duration(path):
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(path)
        return round(len(audio) / 1000.0, 2)
    except Exception as e:
        print(f"  Warning: could not get duration for {path}: {e}")
        return None


def migrate():
    engine = create_engine(SYNC_DB_URL)
    user_id = UUID(GUANGRUI_USER_ID)

    user_upload_dir = os.path.join(UPLOAD_DIR, str(user_id))
    user_task_dir_base = os.path.join(TASK_DIR, str(user_id))
    os.makedirs(user_upload_dir, exist_ok=True)
    os.makedirs(user_task_dir_base, exist_ok=True)

    task_dirs = sorted([
        d for d in os.listdir(V2_TASKS_DIR)
        if os.path.isdir(os.path.join(V2_TASKS_DIR, d))
    ])

    print(f"Found {len(task_dirs)} V2 Streamlit tasks to migrate")
    print(f"Target user: Guangrui ({GUANGRUI_USER_ID})")
    print()

    with Session(engine) as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not user:
            print(f"ERROR: User {GUANGRUI_USER_ID} not found!")
            return
        print(f"User confirmed: {user.email} / {user.display_name}")
        print()

        total_segments = 0
        total_tasks = 0

        for file_hash_short in task_dirs:
            src_dir = os.path.join(V2_TASKS_DIR, file_hash_short)
            manifest_path = os.path.join(src_dir, "manifest.json")
            status_path = os.path.join(src_dir, "status.json")

            if not os.path.exists(manifest_path):
                print(f"SKIP: {file_hash_short} - no manifest.json")
                continue

            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            with open(status_path, "r", encoding="utf-8") as f:
                status_data = json.load(f)

            upload_name = manifest.get("upload_name", "unknown.mp3")
            file_hash = manifest.get("file_hash", "")
            segments_data = manifest.get("segments", [])
            created_at_str = manifest.get("created_at", "")
            stage = status_data.get("stage", "done")

            if stage != "done":
                print(f"SKIP: {file_hash_short} - stage is '{stage}', not 'done'")
                continue

            existing = db.execute(
                select(Task).where(Task.user_id == user_id, Task.file_hash == file_hash)
            ).scalar_one_or_none()

            if existing:
                print(f"SKIP: {upload_name} - already exists in DB (task_id={existing.id})")
                continue

            task_id = uuid4()
            task_dir = os.path.join(user_task_dir_base, str(task_id))
            os.makedirs(task_dir, exist_ok=True)

            src_audio = None
            for ext in [".mp3", ".wav", ".m4a"]:
                candidates = [f for f in os.listdir(src_dir) if f.endswith(ext) and "normalized" not in f]
                if candidates:
                    src_audio = os.path.join(src_dir, candidates[0])
                    break

            if not src_audio:
                print(f"SKIP: {file_hash_short} - no source audio found")
                continue

            dest_upload = os.path.join(user_upload_dir, upload_name)
            if not os.path.exists(dest_upload):
                shutil.copy2(src_audio, dest_upload)
                print(f"  Copied source audio to {dest_upload}")

            normalized_src = os.path.join(src_dir, upload_name.replace(".mp3", ".normalized.mp3"))
            if os.path.exists(normalized_src):
                dest_normalized = os.path.join(task_dir, "normalized.mp3")
                shutil.copy2(normalized_src, dest_normalized)
                normalized_path = dest_normalized
            else:
                dest_normalized = os.path.join(task_dir, "normalized.mp3")
                shutil.copy2(src_audio, dest_normalized)
                normalized_path = dest_normalized

            clips_src_dir = os.path.join(src_dir, "clips")
            clips_dest_dir = os.path.join(task_dir, "clips")
            if os.path.exists(clips_src_dir):
                if os.path.exists(clips_dest_dir):
                    shutil.rmtree(clips_dest_dir)
                shutil.copytree(clips_src_dir, clips_dest_dir)

            duration_sec = get_audio_duration(dest_normalized)
            file_size = os.path.getsize(dest_upload)

            created_at = None
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                except Exception:
                    pass
            if not created_at:
                created_at = datetime.now(timezone.utc)

            task = Task(
                id=task_id,
                user_id=user_id,
                upload_name=upload_name,
                file_hash=file_hash,
                file_duration_sec=Decimal(str(duration_sec)) if duration_sec else None,
                file_size_bytes=file_size,
                engine=manifest.get("engine", "local_whisper"),
                model_size=manifest.get("model_size", "medium"),
                stage="done",
                progress=Decimal("1"),
                stage_message="Migrated from V2 Streamlit",
                source_path=dest_upload,
                normalized_path=normalized_path,
                clips_dir=clips_dest_dir,
                segment_count=len(segments_data),
                credits_charged=Decimal("0"),
                credits_reserved=Decimal("0"),
                is_public=False,
                created_at=created_at,
                started_at=created_at,
                finished_at=datetime.now(timezone.utc),
            )
            db.add(task)

            for idx, seg in enumerate(segments_data):
                clip_name = f"clip_{idx + 1:03d}.mp3"
                clip_rel = os.path.join(str(user_id), str(task_id), "clips", clip_name)
                segment = Segment(
                    task_id=task_id,
                    seq_index=idx,
                    start_time=Decimal(str(round(seg.get("start", 0), 3))),
                    end_time=Decimal(str(round(seg.get("end", 0), 3))),
                    german_text=seg.get("text", ""),
                    chinese_text=seg.get("chinese_text", ""),
                    clip_path=clip_rel,
                )
                db.add(segment)

            db.commit()

            total_segments += len(segments_data)
            total_tasks += 1
            print(f"  MIGRATED: {upload_name} -> task_id={task_id}")
            print(f"    Duration: {duration_sec}s, Segments: {len(segments_data)}, Clips: {len(os.listdir(clips_dest_dir)) if os.path.exists(clips_dest_dir) else 0}")

    print()
    print(f"=== Migration Complete ===")
    print(f"Tasks migrated: {total_tasks}")
    print(f"Total segments: {total_segments}")


if __name__ == "__main__":
    migrate()
