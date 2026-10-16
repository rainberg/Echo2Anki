import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import Transcription, User
from app.config import settings
from app.transcribe_worker import get_transcribe_worker

router = APIRouter(prefix="/transcribe", tags=["transcribe"])

ALLOWED_EXTENSIONS = {".flac", ".mp3", ".mpeg", ".mpga", ".ogg", ".wav"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB
SUPPORTED_LANGUAGES = {"de", "en", "fr", "it", "es", "pt", "el", "nl", "pl", "vi", "zh", "ar", "ja", "ko"}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_transcription(
    file: UploadFile = File(...),
    language: str = Form("de"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate language
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}. Supported: {', '.join(sorted(SUPPORTED_LANGUAGES))}")

    # Validate file extension
    filename = file.filename or "audio.wav"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    # Read file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size: 25MB")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Create DB record
    record = Transcription(
        user_id=user.id,
        filename=filename,
        language=language,
        status="pending",
        file_size=len(content),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    # Save file to temp dir
    tmp_dir = os.path.join(settings.WORK_DIR, "transcriptions")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"{record.id}_{filename}")
    with open(tmp_path, "wb") as f:
        f.write(content)

    # Submit to worker queue
    worker = get_transcribe_worker()
    if not worker.submit(str(record.id)):
        # Queue full — clean up
        os.remove(tmp_path)
        record.status = "failed"
        record.error_message = "转录队列已满，请稍后重试"
        record.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(record)
        raise HTTPException(status_code=429, detail="转录队列已满，请稍后重试")

    return {
        "id": str(record.id),
        "filename": record.filename,
        "language": record.language,
        "status": record.status,
        "file_size": record.file_size,
        "queue_size": worker.queue_size,
        "created_at": record.created_at.isoformat(),
    }


@router.get("/")
async def list_transcriptions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transcription)
        .where(Transcription.user_id == user.id)
        .order_by(Transcription.created_at.desc())
        .limit(50)
    )
    records = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "filename": r.filename,
            "language": r.language,
            "status": r.status,
            "file_size": r.file_size,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in records
    ]


@router.get("/{transcription_id}")
async def get_transcription(
    transcription_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transcription).where(
            Transcription.id == uuid.UUID(transcription_id),
            Transcription.user_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Transcription not found")

    return {
        "id": str(record.id),
        "filename": record.filename,
        "language": record.language,
        "status": record.status,
        "text": record.text,
        "error_message": record.error_message,
        "file_size": record.file_size,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


@router.delete("/{transcription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transcription(
    transcription_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transcription).where(
            Transcription.id == uuid.UUID(transcription_id),
            Transcription.user_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Transcription not found")
    await db.delete(record)
    await db.commit()
