#!/usr/bin/env python3
"""
Migrate Subtitle Beta tasks from /var/lib/anki-streamlit-subtitle/tasks/
into V2 PostgreSQL API. Assigns all tasks to the Guangrui user.
Skips tasks already migrated from V2 Streamlit (by file_hash).
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

from app.models import Segment, Task, User
from app.config import settings

GUANGRUI_USER_ID = "fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f"
SUBTITLE_TASKS_DIR = "/var/lib/anki-streamlit-subtitle/tasks"
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


def compute_file_hash(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def migrate():
    engine = create_engine(SYNC_DB_URL)
    user_id = UUID(GUANGRUI_USER_ID)

    user_upload_dir = os.path.join(UPLOAD_DIR, str(user_id))
    user_task_dir_base = os.path.join(TASK_DIR, str(user_id))
    os.makedirs(user_upload_dir, exist_ok=True)
    os.makedirs(user_task_dir_base, exist_ok=True)

    task_dirs = sorted([
        d for d in os.listdir(SUBTITLE_TASKS_DIR)
        if os.path.isdir(os.path.join(SUBTITLE_TASKS_DIR, d))
    ])

    print(f"Found {len(task_dirs)} Subtitle Beta tasks")
    print(f"Target user: Guangrui ({GUANGRUI_USER_ID})")
    print()

    with Session(engine) as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not user:
            print(f"ERROR: User {GUANGRUI_USER_ID} not found!")
            return
        print(f"User confirmed: {user.email} / {user.display_name}")
        print()

        existing_hashes = set()
        existing_tasks = db.execute(
            select(Task.file_hash).where(Task.user_id == user_id)
        ).scalars().all()
        existing_hashes = set(existing_tasks)
        print(f"Existing file_hashes for user: {len(existing_hashes)}")
        print()

        total_segments = 0
        total_tasks = 0
        skipped_no_segs = 0
        skipped_dup = 0

        for dir_name in task_dirs:
            src_dir = os.path.join(SUBTITLE_TASKS_DIR, dir_name)
            manifest_path = os.path.join(src_dir, "manifest.json")

            if not os.path.exists(manifest_path):
                print(f"SKIP: {dir_name} - no manifest.json")
                continue

            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            segments_data = manifest.get("segments", [])
            upload_key = manifest.get("upload_key", "")
            upload_name = manifest.get("upload_name", "")

            if not segments_data:
                print(f"SKIP: {dir_name} - no segments (incomplete task)")
                skipped_no_segs += 1
                continue

            upload_key_parts = upload_key.split(":") if upload_key else []
            if not upload_name and len(upload_key_parts) >= 1:
                upload_name = upload_key_parts[0]

            if not upload_name:
                upload_name = f"subtitle_{dir_name}.mp3"

            src_audio = None
            for ext in [".mp3", ".wav", ".m4a"]:
                candidates = [
                    f for f in os.listdir(src_dir)
                    if f.endswith(ext) and "normalized" not in f
                ]
                if candidates:
                    src_audio = os.path.join(src_dir, candidates[0])
                    break

            if not src_audio:
                print(f"SKIP: {dir_name} - no source audio found")
                continue

            file_hash = compute_file_hash(src_audio)

            if file_hash in existing_hashes:
                print(f"SKIP: {upload_name} - already exists in DB (duplicate of V2 task)")
                skipped_dup += 1
                continue

            task_id = uuid4()
            task_dir = os.path.join(user_task_dir_base, str(task_id))
            os.makedirs(task_dir, exist_ok=True)

            dest_upload = os.path.join(user_upload_dir, upload_name)
            if os.path.exists(dest_upload):
                base, ext = os.path.splitext(upload_name)
                counter = 1
                while os.path.exists(dest_upload):
                    dest_upload = os.path.join(user_upload_dir, f"{base}_{counter}{ext}")
                    counter += 1
            shutil.copy2(src_audio, dest_upload)

            normalized_src = os.path.join(src_dir, upload_name.replace(".mp3", ".normalized.mp3"))
            if not os.path.exists(normalized_src):
                for f in os.listdir(src_dir):
                    if f.endswith(".normalized.mp3"):
                        normalized_src = os.path.join(src_dir, f)
                        break

            dest_normalized = os.path.join(task_dir, "normalized.mp3")
            if os.path.exists(normalized_src):
                shutil.copy2(normalized_src, dest_normalized)
            else:
                shutil.copy2(src_audio, dest_normalized)
            normalized_path = dest_normalized

            clips_src_dir = os.path.join(src_dir, "subtitle_clips")
            if not os.path.exists(clips_src_dir):
                clips_src_dir = os.path.join(src_dir, "clips")

            clips_dest_dir = os.path.join(task_dir, "clips")
            if os.path.exists(clips_src_dir):
                if os.path.exists(clips_dest_dir):
                    shutil.rmtree(clips_dest_dir)
                shutil.copytree(clips_src_dir, clips_dest_dir)
            else:
                os.makedirs(clips_dest_dir, exist_ok=True)

            duration_sec = get_audio_duration(dest_normalized)
            file_size = os.path.getsize(dest_upload)

            created_at = None
            created_at_str = manifest.get("created_at", "") or manifest.get("updated_at", "")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                except Exception:
                    pass
            if not created_at:
                created_at = datetime.now(timezone.utc)

            task = Task(
                id=task_id,
                user_id=user_id,
                upload_name=os.path.basename(dest_upload),
                file_hash=file_hash,
                file_duration_sec=Decimal(str(duration_sec)) if duration_sec else None,
                file_size_bytes=file_size,
                engine=manifest.get("engine", "local_whisper") or "local_whisper",
                model_size=manifest.get("model_size", "medium") or "medium",
                stage="done",
                progress=Decimal("1"),
                stage_message="Migrated from Subtitle Beta",
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
            existing_hashes.add(file_hash)

            total_segments += len(segments_data)
            total_tasks += 1
            clip_count = len(os.listdir(clips_dest_dir)) if os.path.exists(clips_dest_dir) else 0
            print(f"  MIGRATED: {os.path.basename(dest_upload)} -> task_id={task_id}")
            print(f"    Duration: {duration_sec}s, Segments: {len(segments_data)}, Clips: {clip_count}")

    print()
    print(f"=== Migration Complete ===")
    print(f"Tasks migrated: {total_tasks}")
    print(f"Total segments: {total_segments}")
    print(f"Skipped (no segments): {skipped_no_segs}")
    print(f"Skipped (duplicate): {skipped_dup}")


if __name__ == "__main__":
    migrate()
