import asyncio
import sys
sys.path.insert(0, "/opt/anki-app/backend")

from app.database import async_session
from app.models import EnginePricing


async def seed():
    async with async_session() as db:
        pricings = [
            EnginePricing(engine_key="local_whisper", engine_name="本地 Whisper", model_size="tiny", credits_per_minute=0.5),
            EnginePricing(engine_key="local_whisper", engine_name="本地 Whisper", model_size="base", credits_per_minute=0.5),
            EnginePricing(engine_key="local_whisper", engine_name="本地 Whisper", model_size="small", credits_per_minute=1.0),
            EnginePricing(engine_key="local_whisper", engine_name="本地 Whisper", model_size="medium", credits_per_minute=2.0),
            EnginePricing(engine_key="local_whisper", engine_name="本地 Whisper", model_size="large", credits_per_minute=4.0),
            EnginePricing(engine_key="openai_whisper", engine_name="OpenAI Whisper API", model_size="whisper-1", credits_per_minute=3.0),
            EnginePricing(engine_key="cohere", engine_name="Cohere ASR", model_size="default", credits_per_minute=1.5),
        ]
        for p in pricings:
            db.add(p)
        await db.commit()
        print(f"Seeded {len(pricings)} engine pricing records")


asyncio.run(seed())
