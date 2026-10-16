import asyncio
import sys
sys.path.insert(0, '/opt/anki-app/backend')
from app.database import async_session
from sqlalchemy import text

async def check():
    async with async_session() as s:
        r = await s.execute(text('SELECT stage, count(*) FROM tasks GROUP BY stage'))
        for row in r:
            print(f'Task stage: {row[0]} count: {row[1]}')
        r = await s.execute(text('SELECT count(*) FROM public_shares'))
        print(f'Public shares: {r.scalar()}')
        r = await s.execute(text("SELECT count(*) FROM tasks WHERE is_public=true"))
        print(f'Public tasks: {r.scalar()}')

asyncio.run(check())
