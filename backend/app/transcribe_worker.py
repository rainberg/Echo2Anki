"""
Single-threaded transcription worker.
Processes one Cohere ASR job at a time from a FIFO queue.
"""

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Transcription

logger = logging.getLogger(__name__)

_sync_engine = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(
            settings.DATABASE_URL_SYNC,
            pool_size=5,
            max_overflow=10,
        )
    return _sync_engine


class TranscribeWorker:
    """Single-threaded worker that processes transcription jobs sequentially."""

    def __init__(self):
        self._queue: list[str] = []  # transcription IDs
        self._lock = threading.Lock()
        self._active = False
        self._cohere_asr = None
        self._max_queue = 10

    @property
    def queue_size(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def _get_asr(self):
        """Lazy-load Cohere ASR model (heavy, only load when first needed)."""
        if self._cohere_asr is None:
            from cohere_asr import CohereASR
            logger.info("Loading Cohere ASR model on %s...", settings.COHERE_DEVICE)
            self._cohere_asr = CohereASR(device=settings.COHERE_DEVICE)
            logger.info("Cohere ASR model loaded")
        return self._cohere_asr

    def submit(self, transcription_id: str) -> bool:
        """Add a transcription job to the queue. Returns False if queue is full."""
        with self._lock:
            if len(self._queue) >= self._max_queue:
                return False
            self._queue.append(transcription_id)
            if not self._active:
                self._active = True
                t = threading.Thread(target=self._run_loop, daemon=True)
                t.start()
        return True

    def _run_loop(self):
        """Process jobs from the queue one at a time."""
        while True:
            with self._lock:
                if not self._queue:
                    self._active = False
                    return
                transcription_id = self._queue.pop(0)

            self._process_job(transcription_id)

    def _process_job(self, transcription_id: str):
        engine = _get_sync_engine()
        with Session(engine) as db:
            record = db.execute(
                select(Transcription).where(Transcription.id == transcription_id)
            ).scalar_one_or_none()
            if not record:
                logger.warning("Transcription %s not found", transcription_id)
                return

            # Build temp file path
            tmp_dir = os.path.join(settings.WORK_DIR, "transcriptions")
            os.makedirs(tmp_dir, exist_ok=True)
            tmp_path = os.path.join(tmp_dir, f"{transcription_id}_{record.filename}")

            if not os.path.exists(tmp_path):
                record.status = "failed"
                record.error_message = "Audio file not found on disk"
                record.updated_at = datetime.now(timezone.utc)
                db.commit()
                return

            try:
                record.status = "processing"
                record.updated_at = datetime.now(timezone.utc)
                db.commit()

                asr = self._get_asr()
                text = asr.transcribe(tmp_path, language=record.language)

                record.status = "done"
                record.text = text
                record.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info("Transcription %s completed", transcription_id)

            except Exception as exc:
                logger.exception("Transcription %s failed", transcription_id)
                record.status = "failed"
                record.error_message = str(exc)[:500]
                record.updated_at = datetime.now(timezone.utc)
                db.commit()

            finally:
                # Clean up temp file
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass


# Singleton
_worker: Optional[TranscribeWorker] = None


def get_transcribe_worker() -> TranscribeWorker:
    global _worker
    if _worker is None:
        _worker = TranscribeWorker()
    return _worker
