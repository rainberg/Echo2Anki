import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.auth_client import close_http_client
from app.config import settings
from app.database import engine
from app.models import Base
from app.routers.auth import admin_router, router as auth_router
from app.routers.anki import router as anki_router
from app.routers.billing import router as billing_router
from app.routers.collections import router as collections_router
from app.routers.help import admin_help_router, router as help_router
from app.routers.public import router as public_router
from app.routers.recharge import router as recharge_router
from app.routers.segments import router as segments_router
from app.routers.swipe import router as swipe_router
from app.routers.transcribe import router as transcribe_router
from app.routers.system import router as system_router
from app.routers.tags import router as tags_router
from app.routers.tasks import router as tasks_router
from app.routers.ws import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.TASK_DIR, exist_ok=True)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_segments_german_trgm ON segments USING gin (german_text gin_trgm_ops)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_segments_chinese_trgm ON segments USING gin (chinese_text gin_trgm_ops)"
        ))
    settings._async_loop = asyncio.get_event_loop()

    # 恢复服务重启前未完成的任务
    from sqlalchemy import select as sa_select
    from app.models import Task, SystemSetting
    from app.worker import get_worker
    from app.database import AsyncSession
    async with AsyncSession(engine) as db:
        result = await db.execute(
            sa_select(Task).where(Task.stage.in_(["pending", "normalizing", "transcribing", "translating"]))
        )
        pending_tasks = result.scalars().all()
        if pending_tasks:
            # 获取系统 OpenAI Key
            sys_result = await db.execute(
                sa_select(SystemSetting).where(SystemSetting.key == "openai_api_key")
            )
            sys_key = sys_result.scalar_one_or_none()
            openai_key = sys_key.value if sys_key else ""

            task_infos = []
            for t in pending_tasks:
                task_infos.append((str(t.id), t.source_path, t.engine, t.model_size, str(t.user_id)))
                t.stage = "pending"
                t.progress = 0
                t.started_at = None
            await db.commit()

            worker = get_worker()
            for task_id, source_path, task_engine, task_model_size, user_id in task_infos:
                try:
                    # 清理之前取消时遗留的 cancel.json，避免 worker 立即再次取消任务
                    task_dir = os.path.join(settings.TASK_DIR, user_id, task_id)
                    cancel_flag = os.path.join(task_dir, "cancel.json")
                    if os.path.exists(cancel_flag):
                        os.remove(cancel_flag)
                    effective_api_key = openai_key if task_engine == "openai_whisper" else ""
                    worker.submit(task_id, source_path, task_engine, task_model_size, effective_api_key, "")
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Failed to resume task {task_id}: {e}")

    yield
    settings._async_loop = None
    await close_http_client()


app = FastAPI(
    title="Anki Audio Processing API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://anki.3mudi.com",
        "https://auth.3mudi.com",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(segments_router, prefix="/api")
app.include_router(collections_router, prefix="/api")
app.include_router(tags_router, prefix="/api")
app.include_router(billing_router, prefix="/api")
app.include_router(recharge_router, prefix="/api")
app.include_router(public_router, prefix="/api")
app.include_router(anki_router, prefix="/api")
app.include_router(help_router, prefix="/api")
app.include_router(admin_help_router, prefix="/api")
app.include_router(swipe_router, prefix="/api")
app.include_router(transcribe_router, prefix="/api")
app.include_router(ws_router)

app.mount("/api/audio", StaticFiles(directory=settings.TASK_DIR), name="audio")


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


# --- Serve frontend SPA ---
_frontend_dist = Path(settings.FRONTEND_DIST)


@app.get("/favicon.svg")
async def favicon():
    p = _frontend_dist / "favicon.svg"
    if p.is_file():
        return FileResponse(p, media_type="image/svg+xml")
    return FileResponse(_frontend_dist / "index.html")


# Mount frontend assets (js, css, etc.) — must come before catch-all
app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="frontend-assets")


# Catch-all: serve index.html for any non-API path (SPA client-side routing)
@app.get("/{path:path}")
async def spa_catchall(path: str):
    # Serve specific static files if they exist (manifest.json, sw.js, etc.)
    file_path = _frontend_dist / path
    if file_path.is_file():
        return FileResponse(file_path)
    # Otherwise return index.html for SPA routing
    return FileResponse(_frontend_dist / "index.html")
