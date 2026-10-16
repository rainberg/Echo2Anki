from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Segment, SystemSetting, Task
from app.billing import charge_credits_sync, settle_credits_sync, refund_all_reserved_sync


def _broadcast_progress(user_id, task_id, stage, progress, message=""):
    try:
        import asyncio
        from app.routers.ws import broadcast_task_progress
        loop = getattr(settings, "_async_loop", None)
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                broadcast_task_progress(str(user_id), str(task_id), stage, float(progress), message),
                loop,
            )
    except Exception:
        pass

logger = logging.getLogger(__name__)

STAGE_PENDING = "pending"
STAGE_NORMALIZING = "normalizing"
STAGE_TRANSCRIBING = "transcribing"
STAGE_TRANSLATING = "translating"
STAGE_DONE = "done"
STAGE_FAILED = "failed"
STAGE_CANCELLED = "cancelled"

_lock = threading.Lock()
_worker_instance: Optional["TaskWorkerV2"] = None

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


def get_worker() -> "TaskWorkerV2":
    global _worker_instance
    with _lock:
        if _worker_instance is None:
            _worker_instance = TaskWorkerV2(max_workers=settings.WORKER_MAX)
        return _worker_instance


def _is_cancelled(task_dir: str) -> bool:
    return os.path.exists(os.path.join(task_dir, "cancel.json"))


def _normalize_audio(input_path: str, output_path: str, task_dir: str = "") -> str:
    proc = subprocess.Popen(
        [
            sys.executable,
            os.path.join(_PROJECT_ROOT, "normalize_audio.py"),
            "--input", input_path,
            "--output", output_path,
            "--sample-rate", "16000",
            "--bitrate", "96k",
            "--mono",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if task_dir:
        while proc.poll() is None:
            if _is_cancelled(task_dir):
                proc.terminate()
                proc.wait(timeout=5)
                raise _CancelRequested()
            import time
            time.sleep(0.5)
    else:
        proc.wait()

    if proc.returncode != 0 or not os.path.exists(output_path):
        detail = (proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else "").strip()
        raise RuntimeError(f"normalize_audio.py failed: {detail}")
    return output_path


def _build_transcriber(engine: str, model_size: str, api_key: str = "", doubao_creds: Optional[dict] = None):
    if engine == "openai_whisper":
        from openai_whisper_api import OpenAIWhisperAPI
        return OpenAIWhisperAPI(api_key=api_key)
    if engine == "cohere":
        from cohere_asr import CohereASR
        return CohereASR(device="cpu")
    if engine == "doubao":
        from doubao_asr import DoubaoASR
        creds = doubao_creds or {}
        return DoubaoASR(
            api_key=creds.get("doubao_api_key", ""),
            app_id=creds.get("doubao_app_id", ""),
            access_token=creds.get("doubao_access_token", ""),
        )
    from whisper_timestamps import WhisperTimestampExtractor
    return WhisperTimestampExtractor(model_size=model_size, device="cpu", compute_type="int8")


def _translate_batch(
    texts: list[str],
    throttle: float = 0.25,
) -> list[str]:
    """逐句翻译德语→中文（Google 直调 + MyMemory 兜底，见 app/translation.py）。

    节流到约 4 请求/秒，低于 Google 免费接口 5 请求/秒限额，
    避免大批量任务触发 429 限流导致整批空翻译。
    """
    import time
    from app.translation import translate_de_to_zh
    translations = []
    for text in texts:
        translations.append(translate_de_to_zh(text))
        time.sleep(throttle)
    return translations


class _CancelRequested(Exception):
    pass


def _run_pipeline(
    task_id_str: str,
    source_path: str,
    engine: str,
    model_size: str,
    api_key: str,
    access_token: str,
    skip_normalize: bool = False,
):
    from uuid import UUID
    task_id = UUID(task_id_str)

    engine_db = _get_sync_engine()
    with Session(engine_db) as db:
        task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
        if not task:
            return

        if task.stage in ("cancelled", "failed"):
            # Refund any leftover reserved credits from old billing model
            if task.credits_reserved and task.credits_reserved > 0:
                try:
                    ok = refund_all_reserved_sync(db, task.user_id, task.id, task.credits_reserved, access_token, task.reserve_reference_id or "")
                    if ok:
                        task.credits_reserved = Decimal("0")
                        task.reserve_reference_id = None
                        db.commit()
                    else:
                        logger.error("Refund FAILED for skipped task %s — credits_reserved NOT cleared", task_id_str)
                except Exception:
                    logger.exception("Billing refund failed for skipped task %s", task_id_str)
            return

        user_id = task.user_id
        task_dir = os.path.join(settings.TASK_DIR, str(user_id), str(task_id))
        os.makedirs(task_dir, exist_ok=True)

        def _check_cancel():
            if _is_cancelled(task_dir):
                raise _CancelRequested()

        def _update_stage(stage: str, progress: Decimal, message: str = "", error: str = ""):
            task.stage = stage
            task.progress = progress
            task.stage_message = message
            if error:
                task.error = error
            if stage == STAGE_NORMALIZING and not task.started_at:
                task.started_at = datetime.now(timezone.utc)
            if stage in (STAGE_DONE, STAGE_FAILED, STAGE_CANCELLED):
                task.finished_at = datetime.now(timezone.utc)
            db.commit()
            _broadcast_progress(user_id, task_id, stage, progress, message)

        try:
            _check_cancel()

            if skip_normalize and engine != "doubao":
                # Doubao 需要公网可访问的 mp3 URL，强制走标准化保证格式
                normalized_path = source_path
                task.normalized_path = source_path
                # 创建符号链接 normalized.mp3 -> 源文件，让前端能通过固定 URL 访问
                norm_link = os.path.join(task_dir, "normalized.mp3")
                if not os.path.exists(norm_link):
                    try:
                        os.symlink(os.path.basename(source_path), norm_link)
                    except OSError:
                        pass  # 符号链接创建失败不影响任务执行
                _update_stage(STAGE_NORMALIZING, Decimal("1"), "Skipped normalization")
            else:
                _update_stage(STAGE_NORMALIZING, Decimal("0"), "Normalizing audio...")

                normalized_path = os.path.join(task_dir, "normalized.mp3")
                _normalize_audio(source_path, normalized_path, task_dir)
                task.normalized_path = normalized_path
                _update_stage(STAGE_NORMALIZING, Decimal("1"), "Audio normalized")

            _check_cancel()
            _update_stage(STAGE_TRANSCRIBING, Decimal("0"), "Transcribing audio...")

            doubao_creds = None
            if engine == "doubao":
                # 豆包凭据：优先系统设置（管理员面板），环境变量兜底（DoubaoASR 内部处理）
                rows = db.execute(
                    select(SystemSetting).where(
                        SystemSetting.key.in_(("doubao_api_key", "doubao_app_id", "doubao_access_token"))
                    )
                ).scalars().all()
                doubao_creds = {s.key: (s.value or "") for s in rows}

            transcriber = _build_transcriber(engine, model_size, api_key, doubao_creds)

            clips_dir = os.path.join(task_dir, "clips")
            os.makedirs(clips_dir, exist_ok=True)

            if engine == "cohere":
                # Cohere: only transcribe, no Whisper/alignment/cutting
                cohere_text = transcriber.transcribe(normalized_path, "de")
                _check_cancel()
                _update_stage(STAGE_TRANSCRIBING, Decimal("1"), f"Cohere transcribed")

                task.transcription_text = cohere_text or ""
                task.segment_count = 0
                db.commit()
            elif engine == "doubao":
                # Doubao: 云端大模型 ASR，经公网 URL 提交，utterances 自带分句时间戳
                base_url = os.environ.get("PUBLIC_BASE_URL", "https://anki.3mudi.com").rstrip("/")
                audio_url = f"{base_url}/api/audio/{user_id}/{task_id}/normalized.mp3"
                logger.info("Doubao ASR audio URL: %s", audio_url)

                def _doubao_progress(waited: float):
                    _update_stage(
                        STAGE_TRANSCRIBING, Decimal("0"),
                        f"Doubao ASR processing ({waited:.0f}s elapsed)",
                    )

                full_text, segments = transcriber.transcribe_url(
                    audio_url,
                    audio_format="mp3",
                    cancel_check=_check_cancel,
                    progress_callback=_doubao_progress,
                )

                _check_cancel()
                _update_stage(STAGE_TRANSCRIBING, Decimal("1"), f"Transcribed {len(segments)} segments")

                from align_and_cut import cut_audio_clips
                cut_audio_clips(normalized_path, segments, clips_dir)

                task.transcription_text = full_text or ""
                task.segment_count = len(segments)
                task.clips_dir = clips_dir
                db.commit()
            else:
                from align_and_cut import process_pipeline
                segments, clip_paths = process_pipeline(
                    normalized_path, None, transcriber, clips_dir, None
                )

                _check_cancel()
                _update_stage(STAGE_TRANSCRIBING, Decimal("1"), f"Transcribed {len(segments)} segments")

                task.segment_count = len(segments)
                task.clips_dir = clips_dir
                db.commit()

            if engine == "cohere":
                # Cohere: skip translation and segment creation
                pass
            else:
                _update_stage(STAGE_TRANSLATING, Decimal("0"), "Translating segments...")

                all_texts = [seg.get("text", "") for seg in segments]
                translations = _translate_batch(all_texts)

                for idx, seg in enumerate(segments):
                    clip_name = f"clip_{idx + 1:03d}.mp3"
                    clip_rel = os.path.join(str(user_id), str(task_id), "clips", clip_name)
                    segment = Segment(
                        task_id=task_id,
                        seq_index=idx,
                        start_time=Decimal(str(round(seg["start"], 3))),
                        end_time=Decimal(str(round(seg["end"], 3))),
                        german_text=seg.get("text", ""),
                        chinese_text=translations[idx] if idx < len(translations) else "",
                        clip_path=clip_rel,
                    )
                    db.add(segment)

                db.commit()

            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(normalized_path)
                task.file_duration_sec = Decimal(str(round(len(audio) / 1000.0, 2)))
            except Exception:
                pass

            _update_stage(STAGE_DONE, Decimal("1"), "Task completed")

            try:
                # Refund any leftover reserved credits from old billing model first
                reserved = task.credits_reserved or Decimal("0")
                ref_id = task.reserve_reference_id or ""
                if reserved > 0:
                    ok = refund_all_reserved_sync(db, task.user_id, task.id, reserved, access_token, ref_id)
                    if ok:
                        task.credits_reserved = Decimal("0")
                        task.reserve_reference_id = None
                        db.commit()
                    else:
                        logger.error("Refund FAILED for done task %s — credits_reserved NOT cleared", task_id_str)

                # Charge actual cost
                actual_dur = task.file_duration_sec or Decimal("0")
                if actual_dur > 0:
                    actual_amount = charge_credits_sync(
                        db, task.user_id, task.id, actual_dur, task.engine, task.model_size, access_token,
                    )
                    task.credits_charged = actual_amount
                    db.commit()
            except Exception:
                logger.exception("Billing charge failed for task %s", task_id_str)

        except _CancelRequested:
            _update_stage(STAGE_CANCELLED, Decimal("0"), "Task cancelled")
            # Refund any leftover reserved credits from old billing model
            try:
                reserved = task.credits_reserved or Decimal("0")
                if reserved > 0:
                    ok = refund_all_reserved_sync(db, task.user_id, task.id, reserved, access_token, task.reserve_reference_id or "")
                    if ok:
                        task.credits_reserved = Decimal("0")
                        task.reserve_reference_id = None
                        db.commit()
                    else:
                        logger.error("Refund FAILED for cancelled task %s — credits_reserved NOT cleared", task_id_str)
            except Exception:
                logger.exception("Billing refund (cancel) failed for task %s", task_id_str)

        except Exception as exc:
            logger.exception("Task %s failed", task_id_str)
            _update_stage(STAGE_FAILED, Decimal("0"), "", str(exc))
            # Refund any leftover reserved credits from old billing model
            try:
                reserved = task.credits_reserved or Decimal("0")
                if reserved > 0:
                    ok = refund_all_reserved_sync(db, task.user_id, task.id, reserved, access_token, task.reserve_reference_id or "")
                    if ok:
                        task.credits_reserved = Decimal("0")
                        task.reserve_reference_id = None
                        db.commit()
                    else:
                        logger.error("Refund FAILED for failed task %s — credits_reserved NOT cleared", task_id_str)
            except Exception:
                logger.exception("Billing refund (fail) failed for task %s", task_id_str)


class TaskWorkerV2:
    def __init__(self, max_workers: int = 2):
        self._max_workers = max_workers
        # 本地引擎（local_whisper, cohere）和远程引擎（openai_whisper, doubao）分开队列
        self._local_queue: list[tuple] = []
        self._remote_queue: list[tuple] = []
        self._queue_lock = threading.Lock()
        self._local_active = 0
        self._remote_active = 0
        self._active_lock = threading.Lock()
        self._threads: list[threading.Thread] = []

    def _is_remote(self, engine: str) -> bool:
        return engine in ("openai_whisper", "doubao")

    def submit(self, task_id: str, source_path: str, engine: str, model_size: str, api_key: str, access_token: str = "", skip_normalize: bool = False):
        task_info = (task_id, source_path, engine, model_size, api_key, access_token, skip_normalize)
        with self._queue_lock:
            if self._is_remote(engine):
                self._remote_queue.append(task_info)
            else:
                self._local_queue.append(task_info)
            self._ensure_workers()

    def _ensure_workers(self):
        # 本地引擎 worker
        while self._local_active < self._max_workers and self._local_queue:
            task_info = self._local_queue.pop(0)
            t = threading.Thread(target=self._run_local_task, args=(task_info,), daemon=True)
            t.start()
            self._threads.append(t)
            with self._active_lock:
                self._local_active += 1
        # 远程引擎 worker（不占用本地 worker 名额）
        while self._remote_active < self._max_workers and self._remote_queue:
            task_info = self._remote_queue.pop(0)
            t = threading.Thread(target=self._run_remote_task, args=(task_info,), daemon=True)
            t.start()
            self._threads.append(t)
            with self._active_lock:
                self._remote_active += 1

    def _run_local_task(self, task_info):
        task_id, source_path, engine, model_size, api_key, access_token, skip_normalize = task_info
        try:
            _run_pipeline(task_id, source_path, engine, model_size, api_key, access_token, skip_normalize)
        except Exception as e:
            logger.exception("Worker thread error for task %s", task_id)
        finally:
            with self._active_lock:
                self._local_active -= 1
            with self._queue_lock:
                self._ensure_workers()

    def _run_remote_task(self, task_info):
        task_id, source_path, engine, model_size, api_key, access_token, skip_normalize = task_info
        try:
            _run_pipeline(task_id, source_path, engine, model_size, api_key, access_token, skip_normalize)
        except Exception as e:
            logger.exception("Worker thread error for task %s", task_id)
        finally:
            with self._active_lock:
                self._remote_active -= 1
            with self._queue_lock:
                self._ensure_workers()

    @property
    def queue_size(self) -> int:
        with self._queue_lock:
            return len(self._local_queue) + len(self._remote_queue)

    @property
    def active_count(self) -> int:
        with self._active_lock:
            return self._local_active + self._remote_active
