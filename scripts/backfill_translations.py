#!/usr/bin/env python3
"""
Backfill chinese_text into segments from V1 manifest.json translations field.
Matches by task upload_name -> manifest upload_key (or upload_name) -> translations[idx].
"""

import json
import os
import sys

sys.path.insert(0, "/opt/anki-app/backend")

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.models import Segment, Task
from app.config import settings

GUANGRUI_USER_ID = "fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f"
SYNC_DB_URL = settings.DATABASE_URL_SYNC

V2_TASKS_DIR = "/var/lib/anki-v2/tasks"
SUBTITLE_TASKS_DIR = "/var/lib/anki-streamlit-subtitle/tasks"


def load_manifest_translations(tasks_dir):
    result = {}
    for d in sorted(os.listdir(tasks_dir)):
        full = os.path.join(tasks_dir, d)
        if not os.path.isdir(full):
            continue
        mf = os.path.join(full, "manifest.json")
        if not os.path.exists(mf):
            continue
        with open(mf) as f:
            m = json.load(f)
        segs = m.get("segments", [])
        translations = m.get("translations", [])
        upload_name = m.get("upload_name", "")
        upload_key = m.get("upload_key", "")
        key_name = upload_key.split(":")[0] if upload_key else upload_name
        if translations and segs:
            result[key_name] = translations
            if upload_name and upload_name != key_name:
                result[upload_name] = translations
    return result


def backfill():
    engine = create_engine(SYNC_DB_URL)

    print("Loading translations from V2 Streamlit manifests...")
    v2_trans = load_manifest_translations(V2_TASKS_DIR)
    print(f"  Found {len(v2_trans)} translation sets")

    print("Loading translations from Subtitle Beta manifests...")
    sub_trans = load_manifest_translations(SUBTITLE_TASKS_DIR)
    print(f"  Found {len(sub_trans)} translation sets")

    all_trans = {**v2_trans, **sub_trans}

    with Session(engine) as db:
        tasks = db.execute(
            select(Task).where(Task.user_id == GUANGRUI_USER_ID)
        ).scalars().all()

        total_updated = 0
        total_segs = 0

        for task in tasks:
            name = task.upload_name
            translations = all_trans.get(name)
            if not translations:
                base_name = os.path.splitext(name)[0]
                for key in all_trans:
                    if key.startswith(base_name):
                        translations = all_trans[key]
                        break
            if not translations:
                print(f"  SKIP: {name} - no translations found")
                continue

            segments = db.execute(
                select(Segment).where(Segment.task_id == task.id).order_by(Segment.seq_index)
            ).scalars().all()

            updated = 0
            for seg in segments:
                total_segs += 1
                if seg.chinese_text and seg.chinese_text.strip():
                    continue
                idx = seg.seq_index
                if idx < len(translations):
                    zh = translations[idx].strip() if translations[idx] else ""
                    if zh:
                        seg.chinese_text = zh
                        updated += 1

            if updated:
                db.commit()
                total_updated += updated
                print(f"  UPDATED: {name} - {updated}/{len(segments)} segments backfilled")
            else:
                print(f"  OK: {name} - all segments already have translations")

        print()
        print(f"=== Backfill Complete ===")
        print(f"Total segments checked: {total_segs}")
        print(f"Total segments updated: {total_updated}")


if __name__ == "__main__":
    backfill()
