import asyncio
import sys
import uuid
sys.path.insert(0, '/opt/anki-app/backend')
from app.database import async_session
from sqlalchemy import text

async def seed():
    async with async_session() as s:
        # Mark some tasks as public
        r = await s.execute(text("UPDATE tasks SET is_public=true WHERE stage='done' AND is_public=false"))
        print(f"Marked {r.rowcount} tasks as public")

        # Get the public task IDs
        r = await s.execute(text("SELECT id, user_id FROM tasks WHERE stage='done' AND is_public=true"))
        tasks = r.all()
        print(f"Found {len(tasks)} public done tasks")

        # Create PublicShare records for each task with random difficulty
        import random
        levels = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
        count = 0
        for task_id, user_id in tasks:
            # Check if PublicShare already exists
            existing = await s.execute(
                text("SELECT id FROM public_shares WHERE task_id=:tid"), {"tid": task_id}
            )
            if existing.scalar():
                continue

            level = random.choice(levels)
            share_id = str(uuid.uuid4())
            await s.execute(text(
                "INSERT INTO public_shares (id, task_id, user_id, title, difficulty, created_at) "
                "VALUES (:id, :tid, :uid, :title, :diff, now())"
            ), {
                "id": share_id,
                "tid": task_id,
                "uid": user_id,
                "title": f"Public Share - {level}",
                "diff": level,
            })
            count += 1

        await s.commit()
        print(f"Created {count} new public_shares records")

        # Verify
        r = await s.execute(text("SELECT count(*) FROM public_shares"))
        print(f"Total public_shares: {r.scalar()}")

        r = await s.execute(text(
            "SELECT count(*) FROM segments s JOIN tasks t ON s.task_id=t.id "
            "WHERE t.is_public=true AND t.stage='done'"
        ))
        print(f"Segments available for public feed: {r.scalar()}")

asyncio.run(seed())
