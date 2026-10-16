#!/usr/bin/env python3
"""
Backfill empty chinese_text in segments by re-calling Google Translate.

Targets recent tasks whose translation was wiped out by Google 429 rate
limiting (2026-10 incident). Uses the same throttle+retry logic as the
fixed worker._translate_batch.

Usage (on server, with backend venv):
    DEEPL_API_KEYS=k1,k2 /opt/anki-venv/bin/python backfill_recent_translations.py <task_id> [task_id ...]
    DEEPL_API_KEYS=k1,k2 /opt/anki-venv/bin/python backfill_recent_translations.py --recent-days 10   # 所有最近任务
    DEEPL_API_KEYS=k1,k2 /opt/anki-venv/bin/python backfill_recent_translations.py --force <task_id>  # 无视已有翻译，全部重翻
"""

import sys
import time

sys.path.insert(0, "/opt/anki-app/backend")

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Segment, Task
from app.config import settings
from app.translation import translate_de_to_zh

THROTTLE = 0.25
FORCE = False


def translate_one(text: str) -> str:
    """DeepL → Google → MyMemory（app.translation 自带重试与兜底）。"""
    return translate_de_to_zh(text)


def backfill_task(db: Session, task: Task) -> tuple[int, int]:
    segments = db.execute(
        select(Segment)
        .where(Segment.task_id == task.id)
        .order_by(Segment.seq_index)
    ).scalars().all()
    if FORCE:
        pending = list(segments)
    else:
        pending = [s for s in segments if not s.chinese_text or not s.chinese_text.strip()]
    print(f"  task {task.id} [{task.upload_name}]: {len(pending)}/{len(segments)} segments need translation")

    updated = 0
    failed = 0
    for i, seg in enumerate(pending, 1):
        zh = translate_one(seg.german_text)
        if zh:
            seg.chinese_text = zh
            updated += 1
        else:
            failed += 1
        if i % 20 == 0:
            db.commit()
            print(f"    progress {i}/{len(pending)} (updated={updated}, failed={failed})")
        time.sleep(THROTTLE)
    db.commit()
    return updated, failed


def main():
    global FORCE
    args = sys.argv[1:]
    if "--force" in args:
        FORCE = True
        args = [a for a in args if a != "--force"]
    engine = create_engine(settings.DATABASE_URL_SYNC)

    with Session(engine) as db:
        if args and args[0] == "--recent-days":
            from datetime import datetime, timedelta, timezone
            since = datetime.now(timezone.utc) - timedelta(days=int(args[1]))
            tasks = db.execute(
                select(Task)
                .where(Task.created_at >= since, Task.segment_count > 0)
                .order_by(Task.created_at.desc())
            ).scalars().all()
        elif args:
            from uuid import UUID
            tasks = db.execute(
                select(Task).where(Task.id.in_([UUID(a) for a in args]))
            ).scalars().all()
        else:
            print(__doc__)
            return

        if not tasks:
            print("No matching tasks.")
            return

        total_updated = total_failed = 0
        for task in tasks:
            updated, failed = backfill_task(db, task)
            total_updated += updated
            total_failed += failed
            print(f"  => done: updated={updated}, failed={failed}")

        print(f"\n=== Backfill complete: updated={total_updated}, failed={total_failed} ===")


if __name__ == "__main__":
    main()
