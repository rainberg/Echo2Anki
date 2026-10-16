#!/usr/bin/env python3
import sys
sys.path.insert(0, "/opt/anki-app/backend")

import asyncio
from app.database import engine, async_session
from app.models import Base, User
from app.auth import hash_password
from sqlalchemy import select

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created")

    async with async_session() as db:
        try:
            user = User(
                email="admin@anki.app",
                password_hash=hash_password("admin123456"),
                display_name="Admin",
                role="admin",
                credits=1000,
                allowed_engines=["local_whisper", "openai_whisper", "cohere"],
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f"User created: {user.id} {user.email} role={user.role} credits={user.credits}")
        except Exception as e:
            print(f"Error: {e}")
            await db.rollback()

        result = await db.execute(select(User))
        users = result.scalars().all()
        for u in users:
            print(f"  {u.email} role={u.role} credits={u.credits}")

asyncio.run(main())
