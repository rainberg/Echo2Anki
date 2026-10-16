"""
task_worker.py — Background task engine for the Anki audio pipeline.

Manages asynchronous processing of audio files:
  normalize -> transcribe -> split sentences -> translate -> done

Task state is persisted as JSON so the Streamlit frontend can poll progress
across reruns.  Each task lives in its own directory under TASK_ROOT.

Usage from the frontend:
    from task_worker import TaskWorker
    worker = TaskWorker()
    task_id = worker.submit(audio_path, upload_name, engine, model_size, api_key)
    status = worker.get_status(task_id)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TASK_ROOT = os.environ.get("ANKI_V2_TASK_DIR", "/var/lib/anki-v2/tasks")
SUBTITLE_TASK_ROOT = os.environ.get(
    "ANKI_SUBTITLE_TASK_DIR",
    "/var/lib/anki-streamlit-subtitle/tasks",
)

ENGINE_LOCAL_WHISPER = "local_whisper"
ENGINE_OPENAI_WHISPER = "openai_whisper"
ENGINE_COHERE = "cohere"

VALID_ENGINES = [ENGINE_LOCAL_WHISPER, ENGINE_OPENAI_WHISPER, ENGINE_COHERE]

STAGE_PENDING = "pending"
STAGE_NORMALIZING = "normalizing"
STAGE_TRANSCRIBING = "transcribing"
STAGE_TRANSLATING = "translating"
STAGE_DONE = "done"
STAGE_FAILED = "failed"
STAGE_CANCELLED = "cancelled"

STAGE_ORDER = [STAGE_PENDING, STAGE_NORMALIZING, STAGE_TRANSCRIBING, STAGE_TRANSLATING, STAGE_DONE]

STAGE_WEIGHTS = {
    STAGE_NORMALIZING: 0.10,
    STAGE_TRANSCRIBING: 0.65,
    STAGE_TRANSLATING: 0.25,
}

_lock = threading.Lock()


def _task_dir(task_id: str) -> str:
    path = os.path.join(TASK_ROOT, task_id)
    os.makedirs(path, exist_ok=True)
    return path


def _status_path(task_id: str) -> str:
    return os.path.join(_task_dir(task_id), "status.json")


def _manifest_path(task_id: str) -> str:
    return os.path.join(_task_dir(task_id), "manifest.json")


def _subtitle_task_dir(task_id: str) -> str:
    return os.path.join(SUBTITLE_TASK_ROOT, task_id)


def _subtitle_manifest_path(task_id: str) -> str:
    return os.path.join(_subtitle_task_dir(task_id), "manifest.json")


def _task_source(task_id: str) -> str:
    if os.path.exists(os.path.join(TASK_ROOT, task_id)):
        return "v2"
    if os.path.exists(_subtitle_task_dir(task_id)):
        return "subtitle"
    return "v2"


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_status(task_id: str) -> Dict[str, Any]:
    source = _task_source(task_id)
    if source == "subtitle":
        manifest = _read_subtitle_manifest(task_id)
        if manifest and manifest.get("segments"):
            return {
                "task_id": task_id,
                "upload_name": manifest.get("upload_name", ""),
                "file_hash": manifest.get("upload_key", "").split(":")[-1] if manifest.get("upload_key") else "",
                "stage": STAGE_DONE,
                "progress": 1.0,
                "segment_count": len(manifest.get("segments", [])),
                "created_at": manifest.get("created_at", "") or manifest.get("updated_at", ""),
                "source": "subtitle",
            }
        return {"task_id": task_id, "stage": STAGE_PENDING, "progress": 0.0, "source": "subtitle"}

    path = _status_path(task_id)
    if not os.path.exists(path):
        return {"task_id": task_id, "stage": STAGE_PENDING, "progress": 0.0}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_status(task_id: str, data: Dict[str, Any]) -> None:
    path = _status_path(task_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_manifest(task_id: str) -> Optional[Dict[str, Any]]:
    source = _task_source(task_id)
    if source == "subtitle":
        manifest = _read_subtitle_manifest(task_id)
        if manifest:
            manifest["source"] = "subtitle"
        return manifest

    path = _manifest_path(task_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_subtitle_manifest(task_id: str) -> Optional[Dict[str, Any]]:
    path = _subtitle_manifest_path(task_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_manifest(task_id: str, data: Dict[str, Any]) -> None:
    path = _manifest_path(task_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def request_cancel(task_id: str) -> bool:
    source = _task_source(task_id)
    if source != "v2":
        return False
    cancel_flag = os.path.join(_task_dir(task_id), "cancel.json")
    with open(cancel_flag, "w", encoding="utf-8") as f:
        json.dump({"cancelled_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, f)
    return True


def _is_cancelled(task_id: str) -> bool:
    cancel_flag = os.path.join(_task_dir(task_id), "cancel.json")
    return os.path.exists(cancel_flag)


def _cleanup_task_dir(task_id: str) -> None:
    tdir = _task_dir(task_id)
    if not os.path.isdir(tdir):
        return
    for fname in os.listdir(tdir):
        fpath = os.path.join(tdir, fname)
        if fname == "status.json":
            continue
        if os.path.isdir(fpath):
            shutil.rmtree(fpath, ignore_errors=True)
        else:
            try:
                os.remove(fpath)
            except OSError:
                pass


def _cleanup_work_dir_file(source_path: str) -> None:
    work_dir = os.environ.get("ANKI_V2_WORK_DIR", "/tmp/anki-v2")
    if not source_path or not os.path.isfile(source_path):
        return
    try:
        resolved = os.path.realpath(source_path)
        work_real = os.path.realpath(work_dir)
        if resolved.startswith(work_real + os.sep):
            os.remove(resolved)
            logger.info("Cleaned up work dir file: %s", resolved)
    except OSError:
        pass


def list_all_tasks() -> List[Dict[str, Any]]:
    tasks = []
    seen_ids = set()

    root = Path(TASK_ROOT)
    if root.exists():
        for sp in root.glob("*/status.json"):
            try:
                data = json.loads(sp.read_text(encoding="utf-8"))
                data["source"] = "v2"
                tasks.append(data)
                seen_ids.add(data.get("task_id", ""))
            except Exception as exc:
                logger.warning("Could not read %s: %s", sp, exc)

    sub_root = Path(SUBTITLE_TASK_ROOT)
    if sub_root.exists():
        for mp in sub_root.glob("*/manifest.json"):
            try:
                data = json.loads(mp.read_text(encoding="utf-8"))
                tid = data.get("task_id", "")
                if tid in seen_ids:
                    continue
                if not data.get("segments"):
                    continue
                tasks.append({
                    "task_id": tid,
                    "upload_name": data.get("upload_name", ""),
                    "file_hash": data.get("upload_key", "").split(":")[-1] if data.get("upload_key") else "",
                    "stage": STAGE_DONE,
                    "progress": 1.0,
                    "segment_count": len(data.get("segments", [])),
                    "created_at": data.get("created_at", "") or data.get("updated_at", ""),
                    "source": "subtitle",
                })
                seen_ids.add(tid)
            except Exception as exc:
                logger.warning("Could not read %s: %s", mp, exc)

    return sorted(tasks, key=lambda t: t.get("created_at", ""), reverse=True)


def find_task_by_hash(content_hash: str) -> Optional[str]:
    prefix = content_hash[:16]
    for task in list_all_tasks():
        fh = task.get("file_hash", "")
        if fh.startswith(prefix):
            return task["task_id"]

    sub_root = Path(SUBTITLE_TASK_ROOT)
    if sub_root.exists():
        for mp in sub_root.glob("*/manifest.json"):
            try:
                data = json.loads(mp.read_text(encoding="utf-8"))
                uk = data.get("upload_key", "")
                if uk and uk.split(":")[-1].startswith(prefix):
                    return data.get("task_id", "")
            except Exception:
                pass
    return None


def _normalize_audio(input_path: str, output_dir: str, task_id: str = "") -> str:
    stem = Path(input_path).stem
    output_path = os.path.join(output_dir, f"{stem}.normalized.mp3")
    proc = subprocess.Popen(
        [
            sys.executable,
            "/opt/anki-app/normalize_audio.py",
            "--input", input_path,
            "--output", output_path,
            "--sample-rate", "16000",
            "--bitrate", "96k",
            "--mono",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if task_id:
        while proc.poll() is None:
            if _is_cancelled(task_id):
                proc.terminate()
                proc.wait(timeout=5)
                raise _CancelRequested()
            time.sleep(0.5)
    else:
        proc.wait()

    if proc.returncode != 0 or not os.path.exists(output_path):
        detail = (proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else "").strip()
        raise RuntimeError(f"normalize_audio.py failed: {detail}")
    return output_path


def _build_transcriber(engine: str, model_size: str, api_key: str = ""):
    if engine == ENGINE_OPENAI_WHISPER:
        from openai_whisper_api import OpenAIWhisperAPI
        return OpenAIWhisperAPI(api_key=api_key)
    if engine == ENGINE_COHERE:
        from cohere_asr import CohereASR
        return CohereASR(device="cpu")
    from whisper_timestamps import WhisperTimestampExtractor
    return WhisperTimestampExtractor(model_size=model_size, device="cpu", compute_type="int8")


def _translate_batch(texts: List[str], progress_callback=None) -> List[str]:
    from deep_translator import GoogleTranslator
    translator = GoogleTranslator(source="de", target="zh-CN")
    translations = []
    total = max(1, len(texts))
    for i, text in enumerate(texts):
        try:
            translations.append(translator.translate(text) or "")
        except Exception as exc:
            logger.warning("Translation failed for sentence %s: %s", i + 1, exc)
            translations.append("")
        if progress_callback:
            progress_callback((i + 1) / total)
    return translations


class _CancelRequested(Exception):
    pass


def _run_pipeline(task_id: str) -> None:
    status = read_status(task_id)
    tdir = _task_dir(task_id)
    engine = status.get("engine", ENGINE_LOCAL_WHISPER)
    model_size = status.get("model_size", "small")
    api_key = status.get("api_key", "")
    source_path = status.get("source_path", "")

    def _check_cancel():
        if _is_cancelled(task_id):
            raise _CancelRequested()

    try:
        _check_cancel()

        status["stage"] = STAGE_NORMALIZING
        status["stage_started_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        status["progress"] = 0.0
        write_status(task_id, status)

        normalized_path = _normalize_audio(source_path, tdir, task_id=task_id)
        status["normalized_audio_path"] = normalized_path
        status["progress"] = 1.0
        write_status(task_id, status)

        _check_cancel()

        status["stage"] = STAGE_TRANSCRIBING
        status["stage_started_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        status["progress"] = 0.0
        write_status(task_id, status)

        transcriber = _build_transcriber(engine, model_size, api_key)

        clips_dir = os.path.join(tdir, "clips")
        os.makedirs(clips_dir, exist_ok=True)

        if engine == ENGINE_COHERE:
            from cohere_asr import CohereASR
            text = transcriber.transcribe(normalized_path, language="de")
            _check_cancel()
            status["cohere_text"] = text or ""
            status["progress"] = 0.5
            write_status(task_id, status)

            from whisper_timestamps import WhisperTimestampExtractor
            whisper = WhisperTimestampExtractor(model_size="tiny", device="cpu", compute_type="int8")

            def transcribe_progress(stage, current, total, message):
                _check_cancel()
                if stage == "whisper":
                    status["progress"] = 0.5 + 0.2
                elif stage == "align":
                    status["progress"] = 0.5 + 0.3
                elif stage == "cut":
                    status["progress"] = 0.5 + 0.4
                if message:
                    status["stage_message"] = message
                write_status(task_id, status)

            from align_and_cut import process_pipeline
            segments, clip_paths = process_pipeline(
                audio_path=normalized_path,
                asr_model=None,
                whisper_extractor=whisper,
                output_dir=clips_dir,
                progress_callback=transcribe_progress,
            )
        else:
            def transcribe_progress(stage, current, total, message):
                _check_cancel()
                if stage == "whisper":
                    status["progress"] = 0.3
                elif stage == "align":
                    status["progress"] = 0.7
                elif stage == "cut":
                    status["progress"] = 0.9
                if message:
                    status["stage_message"] = message
                write_status(task_id, status)

            from align_and_cut import process_pipeline
            segments, clip_paths = process_pipeline(
                audio_path=normalized_path,
                asr_model=None,
                whisper_extractor=transcriber,
                output_dir=clips_dir,
                progress_callback=transcribe_progress,
            )

        _check_cancel()

        status["progress"] = 1.0
        status["segment_count"] = len(segments)
        write_status(task_id, status)

        status["stage"] = STAGE_TRANSLATING
        status["stage_started_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        status["progress"] = 0.0
        write_status(task_id, status)

        all_texts = [seg.get("text", "") for seg in segments]

        def translate_progress(p):
            _check_cancel()
            status["progress"] = p
            write_status(task_id, status)

        translations = _translate_batch(all_texts, progress_callback=translate_progress)

        status["stage"] = STAGE_DONE
        status["progress"] = 1.0
        status["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        write_status(task_id, status)

        manifest = {
            "task_id": task_id,
            "upload_name": status.get("upload_name", ""),
            "file_hash": status.get("file_hash", ""),
            "created_at": status.get("created_at", ""),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "engine": engine,
            "model_size": model_size,
            "normalized_audio_path": normalized_path,
            "audio_dir": clips_dir,
            "segments": segments,
            "translations": translations,
            "favorites": [],
            "push_excluded": [],
        }
        write_manifest(task_id, manifest)

        original_upload = status.get("original_upload_path", "")
        _cleanup_work_dir_file(original_upload)

    except _CancelRequested:
        logger.info("Task %s cancelled by user", task_id)
        status["stage"] = STAGE_CANCELLED
        status["progress"] = 0.0
        status["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        write_status(task_id, status)

    except Exception as exc:
        logger.exception("Task %s failed", task_id)
        status["stage"] = STAGE_FAILED
        status["error"] = str(exc)
        status["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        write_status(task_id, status)


class TaskWorker:
    def __init__(self, max_workers: int = 1):
        self._max_workers = max_workers
        self._queue: List[str] = []
        self._queue_lock = threading.Lock()
        self._active_count = 0
        self._active_lock = threading.Lock()
        self._consumer_thread: Optional[threading.Thread] = None

    def submit(
        self,
        source_path: str,
        upload_name: str,
        engine: str = ENGINE_LOCAL_WHISPER,
        model_size: str = "small",
        api_key: str = "",
    ) -> str:
        fhash = file_hash(source_path)
        task_id = fhash[:16]

        v2_status_path = _status_path(task_id)
        if os.path.exists(v2_status_path):
            existing_status = read_status(task_id)
            if existing_status.get("stage") not in (STAGE_FAILED, STAGE_CANCELLED):
                return task_id
            _cleanup_task_dir(task_id)

        tdir = _task_dir(task_id)
        dest = os.path.join(tdir, os.path.basename(source_path))
        if not os.path.exists(dest):
            shutil.copy2(source_path, dest)

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        status = {
            "task_id": task_id,
            "upload_name": upload_name,
            "file_hash": fhash,
            "source_path": dest,
            "original_upload_path": source_path,
            "engine": engine,
            "model_size": model_size,
            "api_key": api_key,
            "stage": STAGE_PENDING,
            "progress": 0.0,
            "stage_message": "",
            "created_at": now,
            "error": "",
        }
        write_status(task_id, status)

        with self._queue_lock:
            self._queue.append(task_id)
            self._ensure_consumer()

        return task_id

    def _ensure_consumer(self):
        if self._consumer_thread is not None and self._consumer_thread.is_alive():
            return
        self._consumer_thread = threading.Thread(target=self._consume_loop, daemon=True)
        self._consumer_thread.start()

    def _consume_loop(self):
        while True:
            with self._queue_lock:
                if not self._queue:
                    break
                task_id = self._queue.pop(0)

            if _is_cancelled(task_id):
                continue

            with self._active_lock:
                self._active_count += 1
            try:
                _run_pipeline(task_id)
            finally:
                with self._active_lock:
                    self._active_count -= 1

    def queue_size(self) -> int:
        with self._queue_lock:
            return len(self._queue)

    def queue_tasks(self) -> List[str]:
        with self._queue_lock:
            return list(self._queue)

    def remove_from_queue(self, task_id: str) -> bool:
        with self._queue_lock:
            if task_id in self._queue:
                self._queue.remove(task_id)
                request_cancel(task_id)
                return True
        return False

    def restart(
        self,
        task_id: str,
        engine: str = ENGINE_LOCAL_WHISPER,
        model_size: str = "small",
        api_key: str = "",
    ) -> str:
        status = read_status(task_id)
        stage = status.get("stage", "")
        if stage not in (STAGE_FAILED, STAGE_CANCELLED):
            return task_id

        _cleanup_task_dir(task_id)

        source_path = status.get("source_path", "")
        upload_name = status.get("upload_name", "")

        tdir = _task_dir(task_id)
        dest = os.path.join(tdir, os.path.basename(source_path))
        if not os.path.exists(dest) and os.path.exists(source_path):
            shutil.copy2(source_path, dest)
        if not os.path.exists(dest):
            work_dir = os.environ.get("ANKI_V2_WORK_DIR", "/tmp/anki-v2")
            if os.path.isdir(work_dir):
                for fname in os.listdir(work_dir):
                    if fname == os.path.basename(source_path):
                        shutil.copy2(os.path.join(work_dir, fname), dest)
                        break

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        new_status = {
            "task_id": task_id,
            "upload_name": upload_name,
            "file_hash": status.get("file_hash", ""),
            "source_path": dest if os.path.exists(dest) else source_path,
            "original_upload_path": status.get("original_upload_path", ""),
            "engine": engine,
            "model_size": model_size,
            "api_key": api_key,
            "stage": STAGE_PENDING,
            "progress": 0.0,
            "stage_message": "",
            "created_at": now,
            "error": "",
        }
        write_status(task_id, new_status)

        with self._queue_lock:
            if task_id not in self._queue:
                self._queue.append(task_id)
            self._ensure_consumer()

        return task_id

    def get_status(self, task_id: str) -> Dict[str, Any]:
        return read_status(task_id)

    def get_manifest(self, task_id: str) -> Optional[Dict[str, Any]]:
        return read_manifest(task_id)

    def overall_progress(self, task_id: str) -> float:
        status = read_status(task_id)
        stage = status.get("stage", STAGE_PENDING)
        stage_progress = status.get("progress", 0.0)

        if stage == STAGE_PENDING:
            return 0.0
        if stage == STAGE_DONE:
            return 1.0
        if stage == STAGE_FAILED:
            return -1.0

        completed_weight = 0.0
        stage_list = [STAGE_NORMALIZING, STAGE_TRANSCRIBING, STAGE_TRANSLATING]
        for s in stage_list:
            if s == stage:
                completed_weight += STAGE_WEIGHTS[s] * stage_progress
                break
            completed_weight += STAGE_WEIGHTS[s]

        return min(completed_weight, 1.0)

    def eta_seconds(self, task_id: str) -> Optional[float]:
        status = read_status(task_id)
        stage = status.get("stage", STAGE_PENDING)
        if stage in (STAGE_PENDING, STAGE_DONE, STAGE_FAILED):
            return None

        created = status.get("created_at", "")
        if not created:
            return None

        try:
            created_dt = datetime.fromisoformat(created)
            elapsed = (datetime.now(timezone.utc) - created_dt).total_seconds()
        except Exception:
            return None

        overall = self.overall_progress(task_id)
        if overall <= 0.01:
            return None

        remaining_fraction = 1.0 - overall
        rate = overall / elapsed
        if rate <= 0:
            return None
        return remaining_fraction / rate

    def is_processing(self, file_hash_prefix: str) -> Optional[str]:
        for task in list_all_tasks():
            fh = task.get("file_hash", "")
            if fh.startswith(file_hash_prefix[:16]):
                stage = task.get("stage", "")
                if stage not in (STAGE_DONE, STAGE_FAILED, STAGE_CANCELLED):
                    return task["task_id"]
        return None

    @property
    def active_count(self) -> int:
        with self._active_lock:
            return self._active_count
