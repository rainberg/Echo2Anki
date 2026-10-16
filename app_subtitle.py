"""
app_subtitle.py - Subtitle-first production app for German audio -> Anki cards.

It uses one full-audio player with bilingual subtitle highlighting, then lets
the user collect and edit only the sentences that should become Anki cards.
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from deep_translator import GoogleTranslator

sys.path.insert(0, "/opt/anki-app")

from align_and_cut import process_pipeline
from anki_push_router import push_cards_to_server
from audio_normalize import describe_audio
from openai_whisper_api import OpenAIWhisperAPI
from whisper_timestamps import WhisperTimestampExtractor

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="German Subtitle Anki Cards",
    page_icon="Audio",
    layout="wide",
    initial_sidebar_state="expanded",
)

SUPPORTED_FORMATS = ["mp3", "wav", "m4a", "ogg"]
WHISPER_MODEL_OPTIONS = ["base", "small", "medium"]
DEFAULT_WHISPER_MODEL = "small"
OPENAI_WHISPER_LABEL = "OpenAI Whisper API"
LOCAL_WHISPER_LABEL = "Local faster-whisper"
WORK_DIR = "/var/lib/anki-streamlit-subtitle/tasks"
MEDIA_URL_PREFIX = "/subtitle-media"
SUBTITLE_COMPONENT_DIR = Path(__file__).parent / "subtitle_component"
os.makedirs(WORK_DIR, exist_ok=True)
subtitle_player_component = components.declare_component(
    "subtitle_player_component",
    path=str(SUBTITLE_COMPONENT_DIR),
)


@st.cache_resource
def load_whisper_model(model_size: str = DEFAULT_WHISPER_MODEL):
    with st.spinner(f"Loading Whisper {model_size}..."):
        return WhisperTimestampExtractor(
            model_size=model_size,
            device="cpu",
            compute_type="int8",
        )


@st.cache_data
def load_translator():
    return GoogleTranslator(source="de", target="zh-CN")


def build_transcriber(engine: str, model_size: str, api_key: str = ""):
    if engine == OPENAI_WHISPER_LABEL:
        return OpenAIWhisperAPI(api_key=api_key)
    return load_whisper_model(model_size)


def task_dir(task_id: str) -> str:
    path = os.path.join(WORK_DIR, task_id)
    os.makedirs(path, exist_ok=True)
    return path


def get_session_dir() -> str:
    task_id = st.session_state.get("subtitle_task_id")
    if task_id:
        return task_dir(task_id)
    if "subtitle_session_id" not in st.session_state:
        st.session_state.subtitle_session_id = time.strftime("%Y%m%d_%H%M%S")
    return task_dir(st.session_state.subtitle_session_id)


def manifest_path(task_id: str) -> str:
    return os.path.join(task_dir(task_id), "manifest.json")


def list_saved_tasks() -> list[dict]:
    tasks = []
    root = Path(WORK_DIR)
    if not root.exists():
        return tasks
    for manifest in root.glob("*/manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("segments"):
                tasks.append(data)
        except Exception as exc:
            logger.warning("Could not load task manifest %s: %s", manifest, exc)
    return sorted(tasks, key=lambda item: item.get("updated_at", ""), reverse=True)


def load_task(task_id: str) -> bool:
    path = manifest_path(task_id)
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    st.session_state.subtitle_task_id = data.get("task_id", task_id)
    st.session_state.subtitle_audio_path = data.get("normalized_audio_path", "")
    st.session_state.subtitle_audio_upload_key = data.get("upload_key", "")
    st.session_state.subtitle_audio_dir = data.get("audio_dir", "")
    st.session_state.subtitle_segments = data.get("segments", [])
    st.session_state.subtitle_translations = data.get("translations", [])
    st.session_state.subtitle_favorites = data.get("favorites", [])
    st.session_state.subtitle_push_excluded = data.get("push_excluded", [])
    st.session_state.subtitle_processing_done = bool(st.session_state.subtitle_segments)
    return True


def save_task_manifest(upload_name: str = "") -> None:
    task_id = st.session_state.get("subtitle_task_id")
    if not task_id:
        return
    data = {
        "task_id": task_id,
        "upload_name": upload_name or st.session_state.get("subtitle_upload_name", ""),
        "upload_key": st.session_state.get("subtitle_audio_upload_key", ""),
        "created_at": st.session_state.get("subtitle_task_created_at", datetime.utcnow().isoformat(timespec="seconds") + "Z"),
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "normalized_audio_path": st.session_state.get("subtitle_audio_path", ""),
        "audio_dir": st.session_state.get("subtitle_audio_dir", ""),
        "segments": st.session_state.get("subtitle_segments", []),
        "translations": st.session_state.get("subtitle_translations", []),
        "favorites": st.session_state.get("subtitle_favorites", []),
        "push_excluded": st.session_state.get("subtitle_push_excluded", []),
    }
    st.session_state.subtitle_task_created_at = data["created_at"]
    with open(manifest_path(task_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_uploaded_file(uploaded_file, task_id: str) -> str:
    session_dir = task_dir(task_id)
    file_path = os.path.join(session_dir, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path


def uploaded_file_hash(uploaded_file) -> str:
    return hashlib.sha256(uploaded_file.getbuffer()).hexdigest()

def normalize_uploaded_audio(input_path: str, output_dir: str) -> str:
    stem = Path(input_path).stem
    output_path = os.path.join(output_dir, f"{stem}.normalized.mp3")
    proc = subprocess.run(
        [
            sys.executable,
            "/opt/anki-app/normalize_audio.py",
            "--input",
            input_path,
            "--output",
            output_path,
            "--sample-rate",
            "16000",
            "--bitrate",
            "96k",
            "--mono",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not os.path.exists(output_path):
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"normalize_audio.py failed: {detail}")
    return output_path


def translate_batch(texts: list[str], translator: GoogleTranslator, progress_callback=None) -> list[str]:
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


def init_state() -> None:
    defaults = {
        "subtitle_segments": [],
        "subtitle_translations": [],
        "subtitle_audio_path": "",
        "subtitle_audio_upload_key": "",
        "subtitle_audio_dir": "",
        "subtitle_processing_done": False,
        "subtitle_favorites": [],
        "subtitle_push_excluded": [],
        "subtitle_deck_name": "Deutsch Listening",
        "subtitle_editor_seed": [],
        "subtitle_task_id": "",
        "subtitle_upload_name": "",
        "subtitle_task_created_at": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def subtitle_payload() -> list[dict]:
    payload = []
    translations = st.session_state.subtitle_translations
    for idx, seg in enumerate(st.session_state.subtitle_segments):
        payload.append(
            {
                "index": idx + 1,
                "start": float(seg.get("start", 0)),
                "end": float(seg.get("end", 0)),
                "german": seg.get("text", ""),
                "chinese": translations[idx] if idx < len(translations) else "",
            }
        )
    return payload


def media_url_for_path(path: str, task_id: str) -> str:
    if not path:
        return ""
    try:
        resolved = Path(path).resolve()
        task_root = Path(task_dir(task_id)).resolve()
        rel = resolved.relative_to(task_root)
    except Exception:
        return ""
    parts = [task_id] + [part for part in rel.parts if part not in ("", ".")]
    return f"{MEDIA_URL_PREFIX}/" + "/".join(parts)


def normalize_favorite_indices(value, total_segments: int) -> list[int]:
    normalized = []
    if not isinstance(value, list):
        return normalized
    for item in value:
        try:
            idx = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < total_segments:
            normalized.append(idx)
    return sorted(set(normalized))


def normalize_index_list(value, allowed: set[int]) -> list[int]:
    normalized = []
    if not isinstance(value, list):
        return normalized
    for item in value:
        try:
            idx = int(item)
        except (TypeError, ValueError):
            continue
        if idx in allowed:
            normalized.append(idx)
    return sorted(set(normalized))


def render_subtitle_player(audio_path: str, rows: list[dict], task_id: str, favorites: list[int]) -> list[int] | None:
    if not audio_path or not os.path.exists(audio_path):
        st.warning("Normalized audio was not found.")
        return None

    audio_url = media_url_for_path(audio_path, task_id)
    if not audio_url:
        st.warning("Could not build a media URL for the saved audio.")
        return None

    result = subtitle_player_component(
        audio_url=audio_url,
        cues=rows,
        favorites=favorites,
        key=f"subtitle_player_{task_id}",
        default={"favorites": favorites},
    )
    if isinstance(result, dict):
        return normalize_favorite_indices(result.get("favorites"), len(rows))
    return None


init_state()

st.title("German Subtitle Anki Cards")
st.caption("One player, bilingual subtitles, editable favorites, and sync-client Anki push.")

with st.sidebar:
    st.subheader("Tasks")
    st.link_button("Open development page", "https://anki.3mudi.com/dev/", use_container_width=True)
    saved_tasks = list_saved_tasks()
    if saved_tasks:
        labels = [f"{task.get('upload_name') or task['task_id']} - {len(task.get('segments', []))} cues - {task.get('updated_at', '')}" for task in saved_tasks]
        selected_task_label = st.selectbox("Saved tasks", labels)
        selected_task = saved_tasks[labels.index(selected_task_label)]
        if st.button("Load saved task", use_container_width=True):
            if load_task(selected_task["task_id"]):
                st.rerun()
    st.divider()
    recognition_engine = st.selectbox("Recognition engine", [OPENAI_WHISPER_LABEL, LOCAL_WHISPER_LABEL])
    whisper_model_size = st.selectbox(
        "Whisper model size",
        WHISPER_MODEL_OPTIONS,
        index=WHISPER_MODEL_OPTIONS.index(DEFAULT_WHISPER_MODEL),
        disabled=recognition_engine == OPENAI_WHISPER_LABEL,
    )
    openai_api_key_input = st.text_input("OpenAI API Key", type="password")
    st.session_state.subtitle_deck_name = st.text_input(
        "Target deck / Deck",
        value=st.session_state.subtitle_deck_name,
    )

uploaded_file = st.file_uploader("Choose German audio", type=SUPPORTED_FORMATS)

if uploaded_file is not None:
    file_hash = uploaded_file_hash(uploaded_file)
    task_id = file_hash[:16]
    current_upload_key = f"{uploaded_file.name}:{getattr(uploaded_file, 'size', 0)}:{file_hash}"
    existing_manifest = manifest_path(task_id)
    if os.path.exists(existing_manifest) and st.session_state.get("subtitle_task_id") != task_id:
        if load_task(task_id):
            st.success("Loaded the saved task for this audio. No upload/transcription repeat needed.")
            st.rerun()
    if not (
        st.session_state.subtitle_audio_upload_key == current_upload_key
        and st.session_state.subtitle_audio_path
        and os.path.exists(st.session_state.subtitle_audio_path)
    ):
        with st.status("Normalizing uploaded audio...", expanded=True) as status:
            st.session_state.subtitle_task_id = task_id
            st.session_state.subtitle_upload_name = uploaded_file.name
            st.session_state.subtitle_task_created_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            session_dir = task_dir(task_id)
            source_path = save_uploaded_file(uploaded_file, task_id)
            normalized_path = normalize_uploaded_audio(source_path, session_dir)
            st.session_state.subtitle_audio_path = normalized_path
            st.session_state.subtitle_audio_upload_key = current_upload_key
            st.session_state.subtitle_processing_done = False
            st.session_state.subtitle_segments = []
            st.session_state.subtitle_translations = []
            st.session_state.subtitle_favorites = []
            st.session_state.subtitle_push_excluded = []
            save_task_manifest(uploaded_file.name)
            try:
                st.json(describe_audio(normalized_path))
            except Exception as exc:
                logger.warning("Could not describe normalized audio: %s", exc)
            status.update(label="Normalization complete", state="complete")
        st.rerun()

    if st.session_state.subtitle_audio_path:
        with open(st.session_state.subtitle_audio_path, "rb") as f:
            st.download_button(
                "Download normalized audio",
                f.read(),
                file_name=Path(st.session_state.subtitle_audio_path).name,
                mime="audio/mpeg",
                use_container_width=True,
            )

    if st.button("Transcribe, split, and build bilingual subtitles", type="primary", use_container_width=True):
        with st.status("Processing...", expanded=True) as status:
            session_dir = get_session_dir()
            clips_dir = os.path.join(session_dir, "subtitle_clips")
            os.makedirs(clips_dir, exist_ok=True)
            st.write("Using normalized audio.")
            transcriber = build_transcriber(recognition_engine, whisper_model_size, openai_api_key_input)
            progress_bar = st.progress(0, text="Transcribing...")
            progress_note = st.empty()

            def pipeline_progress(stage, current, total, message):
                if stage == "whisper":
                    progress_bar.progress(35, text="Whisper transcription and timestamps...")
                elif stage == "align":
                    progress_bar.progress(70, text="Building sentence subtitle timeline...")
                elif stage == "cut":
                    progress_bar.progress(85, text="Preparing Anki sentence clips...")
                if message:
                    progress_note.info(message)

            segments, clip_paths = process_pipeline(
                audio_path=st.session_state.subtitle_audio_path,
                asr_model=None,
                whisper_extractor=transcriber,
                output_dir=clips_dir,
                progress_callback=pipeline_progress,
            )
            st.session_state.subtitle_segments = segments
            st.session_state.subtitle_audio_dir = clips_dir

            st.write("Translating all cues with Google Translate...")
            translator = load_translator()
            translation_bar = st.progress(0, text="Translating...")
            st.session_state.subtitle_translations = translate_batch(
                [seg.get("text", "") for seg in segments],
                translator,
                progress_callback=lambda p: translation_bar.progress(p, text=f"Translating... {int(p * 100)}%"),
            )
            st.session_state.subtitle_favorites = []
            st.session_state.subtitle_push_excluded = []
            st.session_state.subtitle_processing_done = True
            save_task_manifest()
            progress_bar.progress(100, text="Done")
            status.update(label="Bilingual subtitles ready", state="complete")
        st.rerun()

if st.session_state.subtitle_processing_done:
    st.header("Player")
    st.caption("Click a subtitle row to jump playback. Click only the checkbox on the right to add or remove it from Favorite list.")
    player_favorites = render_subtitle_player(
        st.session_state.subtitle_audio_path,
        subtitle_payload(),
        st.session_state.get("subtitle_task_id", ""),
        st.session_state.subtitle_favorites,
    )
    if player_favorites is not None and player_favorites != st.session_state.subtitle_favorites:
        st.session_state.subtitle_favorites = player_favorites
        st.session_state.subtitle_push_excluded = normalize_index_list(
            st.session_state.get("subtitle_push_excluded", []),
            set(player_favorites),
        )
        save_task_manifest()
        st.rerun()

    favorites = st.session_state.subtitle_favorites
    favorite_count = len(favorites)
    favorite_set = set(favorites)
    st.session_state.subtitle_push_excluded = normalize_index_list(
        st.session_state.get("subtitle_push_excluded", []),
        favorite_set,
    )

    if favorite_count > 0:
        st.header("Favorite list")
        favorite_rows = []
        push_excluded = set(st.session_state.subtitle_push_excluded)
        for idx in favorites:
            seg = st.session_state.subtitle_segments[idx]
            favorite_rows.append({
                "Push": idx not in push_excluded,
                "No": idx + 1,
                "Time": f"{seg.get('start', 0):.1f}-{seg.get('end', 0):.1f}s",
                "German": seg.get("text", ""),
                "Chinese": st.session_state.subtitle_translations[idx] if idx < len(st.session_state.subtitle_translations) else "",
            })
        edited_favorites = st.data_editor(
            favorite_rows,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            disabled=["No", "Time"],
            column_config={
                "Push": st.column_config.CheckboxColumn("Push"),
                "No": st.column_config.NumberColumn("No"),
                "Time": st.column_config.TextColumn("Time"),
                "German": st.column_config.TextColumn("German"),
                "Chinese": st.column_config.TextColumn("Chinese"),
            },
            key="subtitle_favorite_text_editor",
        )

        push_indices = []
        next_push_excluded = []
        for row in edited_favorites:
            idx = int(row["No"]) - 1
            if 0 <= idx < len(st.session_state.subtitle_segments):
                if row.get("Push"):
                    push_indices.append(idx)
                else:
                    next_push_excluded.append(idx)
                st.session_state.subtitle_segments[idx]["text"] = row.get("German", "")
                if idx < len(st.session_state.subtitle_translations):
                    st.session_state.subtitle_translations[idx] = row.get("Chinese", "")
        st.session_state.subtitle_push_excluded = sorted(set(next_push_excluded))
        save_task_manifest()

        if st.button("Push selected to Anki", type="primary", use_container_width=True, disabled=len(push_indices) == 0):
            with st.status("Pushing cards to server...", expanded=True) as status:
                sentences = []
                for idx in push_indices:
                    seg = st.session_state.subtitle_segments[idx]
                    sentences.append(
                        {
                            "audio_filename": f"clip_{idx + 1:03d}.mp3",
                            "german_text": seg.get("text", ""),
                            "chinese_text": st.session_state.subtitle_translations[idx]
                            if idx < len(st.session_state.subtitle_translations)
                            else "",
                        }
                    )
                result = push_cards_to_server(
                    sentences,
                    st.session_state.subtitle_audio_dir,
                    st.session_state.subtitle_deck_name,
                )
                if result.get("success"):
                    status.update(label="Push succeeded", state="complete")
                    st.success(result.get("message", "Push succeeded"))
                else:
                    status.update(label="Push failed", state="error")
                    st.error(result.get("message", "Push failed"))

st.divider()
st.caption("One player | bilingual highlight | favorites to Anki")
