"""
app_v2.py — Async processing version of the German audio -> Anki card pipeline.

Changes from the original app.py:
1. Background processing after upload (normalize, transcribe, translate)
2. Real-time progress display with ETA
3. Browse completed tasks, play audio, favorite sentences, push to Anki
4. Duplicate upload warning
5. Engine selection on upload
6. Does not affect existing app.py or app_subtitle.py

Usage:
    source /opt/anki-venv/bin/activate
    streamlit run app_v2.py --server.port 8502 --server.address 0.0.0.0
"""

import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, "/opt/anki-app")

from task_worker import (
    ENGINE_COHERE,
    ENGINE_LOCAL_WHISPER,
    ENGINE_OPENAI_WHISPER,
    STAGE_CANCELLED,
    STAGE_DONE,
    STAGE_FAILED,
    STAGE_NORMALIZING,
    STAGE_PENDING,
    STAGE_TRANSCRIBING,
    STAGE_TRANSLATING,
    TaskWorker,
    _task_source,
    file_hash,
    list_all_tasks,
    read_manifest,
    read_status,
    request_cancel,
)
from anki_push_router import push_cards_to_server
from audio_normalize import describe_audio

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="德语听力卡片生成器",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="expanded",
)

SUPPORTED_FORMATS = ["mp3", "wav", "m4a", "ogg"]
SUPPORTED_EXTENSIONS = set(SUPPORTED_FORMATS)
WORK_DIR = "/tmp/anki-v2"
V2_TASK_ROOT = os.environ.get("ANKI_V2_TASK_DIR", "/var/lib/anki-v2/tasks")
SUBTITLE_TASK_ROOT = os.environ.get("ANKI_SUBTITLE_TASK_DIR", "/var/lib/anki-streamlit-subtitle/tasks")
V2_MEDIA_URL_PREFIX = "/media"
SUBTITLE_MEDIA_URL_PREFIX = "/subtitle-media"
SUBTITLE_COMPONENT_DIR = Path(__file__).parent / "subtitle_component"
os.makedirs(WORK_DIR, exist_ok=True)

_subtitle_player_component = components.declare_component(
    "subtitle_player_component",
    path=str(SUBTITLE_COMPONENT_DIR),
)


def _scan_work_dir() -> list:
    files = []
    if not os.path.isdir(WORK_DIR):
        return files
    for fname in sorted(os.listdir(WORK_DIR)):
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        fpath = os.path.join(WORK_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        fhash = file_hash(fpath)
        files.append({"name": fname, "path": fpath, "hash": fhash, "size": os.path.getsize(fpath)})
    return files


def _v2_tasks() -> list:
    return [t for t in list_all_tasks() if t.get("source") != "subtitle"]


def _media_url_for_path(path: str, task_id: str, source: str = "v2") -> str:
    if not path:
        return ""
    try:
        resolved = Path(path).resolve()
        if source == "subtitle":
            task_root = Path(SUBTITLE_TASK_ROOT).resolve()
            prefix = SUBTITLE_MEDIA_URL_PREFIX
        else:
            task_root = Path(V2_TASK_ROOT).resolve()
            prefix = V2_MEDIA_URL_PREFIX
        rel = resolved.relative_to(task_root)
    except Exception:
        return ""
    parts = [p for p in rel.parts if p not in ("", ".")]
    return f"{prefix}/" + "/".join(parts)


def _subtitle_payload(segments: list, translations: list) -> list:
    payload = []
    for idx, seg in enumerate(segments):
        payload.append({
            "index": idx + 1,
            "start": float(seg.get("start", 0)),
            "end": float(seg.get("end", 0)),
            "german": seg.get("text", ""),
            "chinese": translations[idx] if idx < len(translations) else "",
        })
    return payload


def _normalize_favorite_indices(value, total_segments: int) -> list:
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


def _normalize_index_list(value, allowed: set) -> list:
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

ENGINE_LABELS = {
    ENGINE_LOCAL_WHISPER: "本地 faster-whisper",
    ENGINE_OPENAI_WHISPER: "OpenAI Whisper API",
    ENGINE_COHERE: "Cohere ASR",
}

STAGE_LABELS = {
    STAGE_PENDING: "⏳ 等待中",
    STAGE_NORMALIZING: "🔊 标准化音频",
    STAGE_TRANSCRIBING: "🎯 语音识别",
    STAGE_TRANSLATING: "🌐 翻译中",
    STAGE_DONE: "✅ 完成",
    STAGE_FAILED: "❌ 失败",
    STAGE_CANCELLED: "🚫 已取消",
}


if "v2_worker" not in st.session_state:
    st.session_state.v2_worker = TaskWorker()

if "v2_current_task_id" not in st.session_state:
    st.session_state.v2_current_task_id = ""

if "v2_favorites" not in st.session_state:
    st.session_state.v2_favorites = []

if "v2_push_excluded" not in st.session_state:
    st.session_state.v2_push_excluded = []

if "v2_deck_name" not in st.session_state:
    st.session_state.v2_deck_name = "Deutsch Listening"


def _save_uploaded(uploaded_file) -> str:
    os.makedirs(WORK_DIR, exist_ok=True)
    path = os.path.join(WORK_DIR, uploaded_file.name)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path


def _uploaded_hash(uploaded_file) -> str:
    return hashlib.sha256(uploaded_file.getbuffer()).hexdigest()


def _format_eta(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return "计算中..."
    if seconds < 60:
        return f"{int(seconds)} 秒"
    minutes = int(seconds / 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes} 分 {secs} 秒"
    hours = int(minutes / 60)
    mins = minutes % 60
    return f"{hours} 时 {mins} 分"


def _render_progress(task_id: str) -> bool:
    worker = st.session_state.v2_worker
    done = False

    status = worker.get_status(task_id)
    stage = status.get("stage", STAGE_PENDING)
    stage_msg = status.get("stage_message", "")
    error = status.get("error", "")

    overall = worker.overall_progress(task_id)
    eta = worker.eta_seconds(task_id)

    stage_label = STAGE_LABELS.get(stage, stage)

    progress_container = st.container()
    with progress_container:
        st.markdown(f"### {stage_label}")
        if stage_msg:
            st.caption(stage_msg)

        if stage == STAGE_FAILED:
            st.error(f"处理失败: {error}")
            return True

        if stage == STAGE_CANCELLED:
            st.warning("任务已被取消")
            return True

        progress_bar = st.progress(min(max(overall, 0.0), 1.0), text=f"总进度 {int(overall * 100)}%")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("当前阶段", stage_label)
        with col2:
            st.metric("总进度", f"{int(overall * 100)}%")
        with col3:
            st.metric("预计剩余", _format_eta(eta))

        if stage not in (STAGE_DONE, STAGE_CANCELLED, STAGE_FAILED):
            if st.button("🚫 取消此任务", key=f"cancel_{task_id}", use_container_width=True):
                request_cancel(task_id)
                st.warning("已发送取消请求...")
                st.rerun()

        if stage == STAGE_DONE:
            segment_count = status.get("segment_count", 0)
            st.success(f"处理完成！共 {segment_count} 个句子")
            done = True

    return done


def _render_task_browser():
    tasks = list_all_tasks()
    if not tasks:
        st.info("暂无已完成的任务。请先上传音频文件。")
        return

    task_options = {}
    for t in tasks:
        stage = t.get("stage", "")
        name = t.get("upload_name", t.get("task_id", ""))
        created = t.get("created_at", "")[:19].replace("T", " ")
        seg_count = t.get("segment_count", "")
        source = t.get("source", "v2")
        source_tag = "字幕Beta" if source == "subtitle" else "v2"
        label = f"[{source_tag}] {name} | {STAGE_LABELS.get(stage, stage)} | {created}"
        if seg_count:
            label += f" | {seg_count} 句"
        task_options[label] = t["task_id"]

    selected_label = st.selectbox(
        "选择任务",
        options=list(task_options.keys()),
        index=0,
    )

    if st.button("📂 加载任务", use_container_width=True):
        task_id = task_options[selected_label]
        st.session_state.v2_current_task_id = task_id
        manifest = read_manifest(task_id)
        if manifest:
            st.session_state.v2_favorites = manifest.get("favorites", [])
            st.session_state.v2_push_excluded = manifest.get("push_excluded", [])
        st.rerun()


def _render_sentence_browser(task_id: str):
    manifest = read_manifest(task_id)
    if not manifest:
        st.warning("无法加载任务数据")
        return

    segments = manifest.get("segments", [])
    translations = manifest.get("translations", [])
    audio_dir = manifest.get("audio_dir", "")
    normalized_path = manifest.get("normalized_audio_path", "")
    source = manifest.get("source", _task_source(task_id))

    if not segments:
        st.info("该任务没有句子数据")
        return

    if source == "subtitle":
        st.caption("📂 来源：字幕 Beta 版")

    st.header("🎧 播放器")
    st.caption("点击字幕行跳转播放，点击右侧 ✓ 按钮收藏/取消收藏")

    audio_url = _media_url_for_path(normalized_path, task_id, source)
    if not audio_url or not os.path.exists(normalized_path):
        st.warning("音频文件不存在，无法使用播放器")
    else:
        player_favorites = _subtitle_player_component(
            audio_url=audio_url,
            cues=_subtitle_payload(segments, translations),
            favorites=st.session_state.v2_favorites,
            key=f"v2_player_{task_id}",
            default={"favorites": st.session_state.v2_favorites},
        )
        if isinstance(player_favorites, dict):
            new_favs = _normalize_favorite_indices(player_favorites.get("favorites"), len(segments))
            if new_favs != st.session_state.v2_favorites:
                st.session_state.v2_favorites = new_favs
                st.session_state.v2_push_excluded = _normalize_index_list(
                    st.session_state.v2_push_excluded,
                    set(new_favs),
                )
                _save_favorites(task_id)
                st.rerun()

    favorites = st.session_state.v2_favorites
    favorite_set = set(favorites)
    st.session_state.v2_push_excluded = _normalize_index_list(
        st.session_state.v2_push_excluded,
        favorite_set,
    )

    if len(favorites) > 0:
        st.header("⭐ 收藏列表")
        favorite_rows = []
        push_excluded = set(st.session_state.v2_push_excluded)
        for idx in reversed(favorites):
            seg = segments[idx]
            favorite_rows.append({
                "推送": idx not in push_excluded,
                "序号": idx + 1,
                "时间": f"{seg.get('start', 0):.1f}-{seg.get('end', 0):.1f}s",
                "德语": seg.get("text", ""),
                "中文": translations[idx] if idx < len(translations) else "",
            })

        edited_favorites = st.data_editor(
            favorite_rows,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            disabled=["序号", "时间"],
            column_config={
                "推送": st.column_config.CheckboxColumn("推送"),
                "序号": st.column_config.NumberColumn("序号"),
                "时间": st.column_config.TextColumn("时间"),
                "德语": st.column_config.TextColumn("德语"),
                "中文": st.column_config.TextColumn("中文"),
            },
            key=f"v2_favorite_editor_{task_id}",
        )

        push_indices = []
        next_push_excluded = []
        for row in edited_favorites:
            idx = int(row["序号"]) - 1
            if 0 <= idx < len(segments):
                if row.get("推送"):
                    push_indices.append(idx)
                else:
                    next_push_excluded.append(idx)
                segments[idx]["text"] = row.get("德语", "")
                if idx < len(translations):
                    translations[idx] = row.get("中文", "")
        st.session_state.v2_push_excluded = sorted(set(next_push_excluded))
        _save_favorites(task_id)

        push_count = len(push_indices)
        st.info(f"已收藏 {len(favorites)} / {len(segments)} 个句子 | 待推送 {push_count} 个")

        if push_count > 0:
            _render_push_section(task_id, manifest, audio_dir)
    else:
        st.info(f"共 {len(segments)} 个句子，请在播放器中点击 ✓ 收藏")


def _save_favorites(task_id: str):
    manifest = read_manifest(task_id)
    if not manifest:
        return
    manifest["favorites"] = st.session_state.v2_favorites
    manifest["push_excluded"] = st.session_state.v2_push_excluded
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    source = manifest.pop("source", _task_source(task_id))
    if source == "subtitle":
        from task_worker import _subtitle_manifest_path
        path = _subtitle_manifest_path(task_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    else:
        from task_worker import write_manifest
        write_manifest(task_id, manifest)


def _render_push_section(task_id: str, manifest: dict, audio_dir: str):
    st.header("📦 推送卡片到 Anki 服务器")

    segments = manifest.get("segments", [])
    translations = manifest.get("translations", [])
    favorites = st.session_state.v2_favorites
    push_excluded = set(st.session_state.v2_push_excluded)

    push_indices = [i for i in favorites if i not in push_excluded]

    if not push_indices:
        st.warning("没有待推送的句子，请先收藏句子")
        return

    deck_name = st.text_input(
        "牌组名称 / Deck",
        value=st.session_state.v2_deck_name,
        key=f"v2_deck_{task_id}",
    )
    st.session_state.v2_deck_name = deck_name

    st.caption(f"将推送 {len(push_indices)} 张卡片到牌组「{deck_name}」")

    if st.button("🚀 推送到 Anki 服务器", type="primary", use_container_width=True):
        with st.status("推送卡片到服务器...", expanded=True) as status:
            sentences = []
            for i in push_indices:
                seg = segments[i]
                sentences.append({
                    "audio_filename": f"clip_{i+1:03d}.mp3",
                    "german_text": seg.get("text", ""),
                    "chinese_text": translations[i] if i < len(translations) else "",
                })

            status.write(f"📦 准备推送 {len(sentences)} 张卡片到牌组「{deck_name}」...")

            result = push_cards_to_server(sentences, audio_dir, deck_name)

            if result.get("success"):
                status.update(label="✅ 推送成功!", state="complete")
                st.success(f"✅ {result.get('message', '推送成功')}")
                with st.expander("📖 同步到 Anki 客户端"):
                    st.markdown(
                        f"""
                        卡片已推送到服务器，打开 Anki 客户端同步即可：

                        1. **Anki Desktop**: 工具 → 设置 → 同步 → 自建同步服务器
                           - 服务器: `http://89.168.93.94:8080`
                        2. 点击 **同步** 按钮（☁️）
                        3. 卡片出现在牌组「**{deck_name}**」中
                        """
                    )
            else:
                status.update(label="❌ 推送失败", state="error")
                st.error(f"❌ {result.get('message', '推送失败')}")


# ============================================================
# Sidebar
# ============================================================

with st.sidebar:
    st.subheader("Anki 音频处理")
    st.divider()

    st.subheader("识别引擎")
    engine_key = st.selectbox(
        "选择引擎",
        options=list(ENGINE_LABELS.keys()),
        format_func=lambda k: ENGINE_LABELS[k],
        index=0,
    )
    model_size = "small"
    if engine_key == ENGINE_LOCAL_WHISPER:
        model_size = st.selectbox(
            "Whisper 模型大小",
            ["base", "small", "medium"],
            index=1,
        )
    api_key = ""
    if engine_key == ENGINE_OPENAI_WHISPER:
        api_key = st.text_input("OpenAI API Key", type="password")

    st.divider()
    st.subheader("Anki 设置")
    st.session_state.v2_deck_name = st.text_input(
        "目标牌组 / Deck",
        value=st.session_state.v2_deck_name,
    )

    st.divider()
    with st.expander("使用说明", expanded=False):
        st.markdown(
            """
            **功能说明：**

            1. 上传音频后自动后台处理
            2. 实时查看处理进度和预计完成时间
            3. 浏览已完成任务，逐句播放
            4. 收藏句子并推送到 Anki
            5. 重复上传同一文件会收到提醒
            6. 可选择转写引擎
            """
        )


# ============================================================
# Main page
# ============================================================

st.title("🎧 德语听力卡片生成器")
st.caption("异步后台处理 · 实时进度 · 引擎选择 · 重复检测")

tab_upload, tab_progress, tab_tasks = st.tabs(["📤 上传音频", "📊 处理进度", "📂 已完成任务"])

# ---- Tab 1: Upload ----
with tab_upload:
    st.header("上传音频文件")

    uploaded_files = st.file_uploader(
        "选择德语录音文件（支持多文件）",
        type=SUPPORTED_FORMATS,
        key="v2_file_uploader",
        accept_multiple_files=True,
        help="支持 MP3、WAV、M4A、OGG 格式，可同时选择多个文件",
    )

    if uploaded_files:
        worker = st.session_state.v2_worker

        for uploaded_file in uploaded_files:
            fhash = _uploaded_hash(uploaded_file)
            upload_key = f"{uploaded_file.name}:{getattr(uploaded_file, 'size', 0)}:{fhash}"

            if st.session_state.get(f"v2_uploaded_{fhash[:16]}") == upload_key:
                continue

            processing_task = worker.is_processing(fhash)

            if processing_task:
                st.warning(f"⚠️ {uploaded_file.name} 正在后台处理中，无需重复上传")
                continue

            existing_task = None
            for t in _v2_tasks():
                if t.get("file_hash", "").startswith(fhash[:16]) and t.get("stage") == STAGE_DONE:
                    existing_task = t["task_id"]
                    break

            if existing_task:
                st.info(f"ℹ️ {uploaded_file.name} 已处理完成，可在「已完成任务」中查看")
                continue

            source_path = _save_uploaded(uploaded_file)
            task_id = worker.submit(
                source_path=source_path,
                upload_name=uploaded_file.name,
                engine=engine_key,
                model_size=model_size,
                api_key=api_key,
            )
            st.session_state[f"v2_uploaded_{fhash[:16]}"] = upload_key
            st.session_state.v2_current_task_id = task_id
            st.success(f"✅ {uploaded_file.name} 已提交后台处理")

        queue_size = worker.queue_size()
        if queue_size > 0:
            st.info(f"📋 排队中：{queue_size} 个任务等待处理")

    st.divider()
    st.header("📁 待处理文件")
    st.caption(f"扫描目录：`{WORK_DIR}`")

    work_files = _scan_work_dir()

    if not work_files:
        st.info("目录中没有可处理的音频文件。")
    else:
        v2_only = _v2_tasks()
        processing_hashes = set()
        done_hashes = set()
        stopped_hashes = set()
        for t in v2_only:
            fh = t.get("file_hash", "")
            prefix = fh[:16] if fh else ""
            stage = t.get("stage", "")
            if stage == STAGE_DONE:
                done_hashes.add(prefix)
            elif stage in (STAGE_FAILED, STAGE_CANCELLED):
                stopped_hashes.add(prefix)
            else:
                processing_hashes.add(prefix)

        selectable_files = []
        for f in work_files:
            prefix = f["hash"][:16]
            if prefix in processing_hashes:
                continue
            if prefix in done_hashes:
                continue
            selectable_files.append(f)

        cols = st.columns([0.05, 0.40, 0.20, 0.20, 0.15])
        with cols[0]:
            st.markdown("**☑**")
        with cols[1]:
            st.markdown("**文件名**")
        with cols[2]:
            st.markdown("**大小**")
        with cols[3]:
            st.markdown("**哈希**")
        with cols[4]:
            st.markdown("**状态**")

        for f in work_files:
            prefix = f["hash"][:16]
            is_processing = prefix in processing_hashes
            is_done = prefix in done_hashes
            is_stopped = prefix in stopped_hashes
            is_selectable = not is_processing and not is_done

            cols = st.columns([0.05, 0.40, 0.20, 0.20, 0.15])
            with cols[0]:
                if is_selectable:
                    st.checkbox(
                        "选",
                        value=True,
                        key=f"v2_select_{prefix}",
                        label_visibility="collapsed",
                    )
            with cols[1]:
                st.text(f["name"])
            with cols[2]:
                size_mb = f["size"] / (1024 * 1024)
                st.text(f"{size_mb:.1f} MB")
            with cols[3]:
                st.text(prefix[:12] + "...")
            with cols[4]:
                if is_processing:
                    st.text("🔄 处理中")
                elif is_done:
                    st.text("✅ 已完成")
                elif is_stopped:
                    st.text("🚫 已停止")
                else:
                    st.text("⏳ 待处理")

        if not selectable_files:
            st.success("所有文件已提交处理或处理完成，无需重复操作。")
        else:
            selected_files = []
            for f in selectable_files:
                prefix = f["hash"][:16]
                key = f"v2_select_{prefix}"
                if st.session_state.get(key, True):
                    selected_files.append(f)

            st.markdown(f"已勾选 **{len(selected_files)}** / {len(selectable_files)} 个待处理文件")

            if st.button("🚀 开始后处理", type="primary", use_container_width=True, disabled=len(selected_files) == 0):
                worker = st.session_state.v2_worker
                submitted = 0
                skipped = 0
                for f in selected_files:
                    source_path = f["path"]
                    upload_name = f["name"]

                    processing_task = worker.is_processing(f["hash"])
                    if processing_task:
                        skipped += 1
                        continue

                    existing_task = None
                    for t in _v2_tasks():
                        if t.get("file_hash", "").startswith(f["hash"][:16]) and t.get("stage") == STAGE_DONE:
                            existing_task = t["task_id"]
                            break
                    if existing_task:
                        skipped += 1
                        continue

                    task_id = worker.submit(
                        source_path=source_path,
                        upload_name=upload_name,
                        engine=engine_key,
                        model_size=model_size,
                        api_key=api_key,
                    )
                    st.session_state.v2_current_task_id = task_id
                    submitted += 1

                if submitted > 0:
                    st.success(f"✅ 已提交 {submitted} 个文件进行后台处理")
                if skipped > 0:
                    st.warning(f"⚠️ 跳过 {skipped} 个文件（已在处理或已完成）")
                if submitted > 0:
                    st.rerun()

    if st.button("🔄 刷新状态", use_container_width=True):
        st.rerun()

# ---- Tab 2: Progress ----
with tab_progress:
    st.header("处理进度")

    worker = st.session_state.v2_worker
    all_tasks = list_all_tasks()
    v2_only = [t for t in all_tasks if t.get("source") != "subtitle"]
    active_tasks = [t for t in v2_only if t.get("stage") not in (STAGE_DONE, STAGE_FAILED, STAGE_CANCELLED)]
    stopped_tasks = [t for t in v2_only if t.get("stage") in (STAGE_FAILED, STAGE_CANCELLED)]

    if not active_tasks:
        st.info("暂无正在处理的任务。请先上传音频文件。")
    else:
        st.subheader(f"活跃任务 ({len(active_tasks)})")

        for t in active_tasks:
            tid = t.get("task_id", "")
            stage = t.get("stage", STAGE_PENDING)
            name = t.get("upload_name", tid)
            stage_label = STAGE_LABELS.get(stage, stage)

            with st.expander(f"{name} — {stage_label}", expanded=(tid == st.session_state.v2_current_task_id)):
                _render_progress(tid)

                if stage not in (STAGE_DONE, STAGE_CANCELLED, STAGE_FAILED):
                    if st.button("🚫 取消", key=f"cancel_list_{tid}"):
                        removed = worker.remove_from_queue(tid)
                        if not removed:
                            request_cancel(tid)
                        st.warning("已发送取消请求...")
                        st.rerun()

    if stopped_tasks:
        st.divider()
        st.subheader(f"已停止的任务 ({len(stopped_tasks)})")

        for t in stopped_tasks:
            tid = t.get("task_id", "")
            stage = t.get("stage", "")
            name = t.get("upload_name", tid)
            stage_label = STAGE_LABELS.get(stage, stage)
            error = t.get("error", "")

            with st.expander(f"{name} — {stage_label}"):
                if error:
                    st.error(f"错误: {error}")

                col_r1, col_r2 = st.columns(2)
                with col_r1:
                    if st.button("🔄 重新开始", key=f"restart_{tid}", use_container_width=True):
                        worker.restart(
                            tid,
                            engine=engine_key,
                            model_size=model_size,
                            api_key=api_key,
                        )
                        st.success(f"✅ {name} 已重新提交处理")
                        st.rerun()
                with col_r2:
                    if st.button("🗑️ 删除任务", key=f"delete_{tid}", use_container_width=True):
                        from task_worker import _task_dir
                        import shutil
                        tdir = _task_dir(tid)
                        if os.path.isdir(tdir):
                            shutil.rmtree(tdir, ignore_errors=True)
                        st.success(f"已删除任务 {name}")
                        st.rerun()

    queue_ids = worker.queue_tasks()
    if queue_ids:
        st.subheader(f"排队中 ({len(queue_ids)})")
        for i, tid in enumerate(queue_ids):
            status = read_status(tid)
            name = status.get("upload_name", tid)
            st.text(f"  {i+1}. {name}")

    if active_tasks:
        st.caption("页面将自动刷新以更新进度...")
        time.sleep(3)
        st.rerun()

# ---- Tab 3: Completed tasks ----
with tab_tasks:
    st.header("已完成任务")

    _render_task_browser()

    current_id = st.session_state.v2_current_task_id
    if current_id:
        status = read_status(current_id)
        if status.get("stage") == STAGE_DONE:
            _render_sentence_browser(current_id)

st.divider()
st.caption("异步后台处理 | 实时进度 | 引擎选择 | 自建 Anki 同步服务器")
