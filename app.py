"""
app.py — 德语语音 → 句子选择 → 翻译 → Anki 导出 全链路 Streamlit 应用

使用方式：
    source /opt/anki-venv/bin/activate
    streamlit run app.py --server.port 8501 --server.address 0.0.0.0

功能：
1. 上传德语录音（MP3/WAV）
2. Whisper 转录 + 时间戳 + 音频切割
3. 逐句试听 + 勾选
4. Google 翻译（德语→中文）
5. genanki 导出 .apkg 文件（含嵌入音频）
6. 提示同步到自建 Anki 云
"""

import streamlit as st
import sys
import os
import json
import logging
import tempfile
import shutil
import subprocess
import hashlib
from pathlib import Path
from typing import Optional
import time
from datetime import datetime

# 添加项目到路径
sys.path.insert(0, "/opt/anki-app")

from whisper_timestamps import WhisperTimestampExtractor
from openai_whisper_api import OpenAIWhisperAPI
from cohere_asr import CohereASR
from audio_normalize import describe_audio
from align_and_cut import process_pipeline, split_into_sentences
from anki_api import AnkiPackageExporter, is_rest_api_available
from deep_translator import GoogleTranslator

# ============================================================
# 配置
# ============================================================

logger = logging.getLogger(__name__)

# Streamlit 页面配置
st.set_page_config(
    page_title="德语听力卡片生成器",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 支持的音频格式
SUPPORTED_FORMATS = ["mp3", "wav", "m4a", "ogg"]

# Whisper 模型选项。德语需要多语言模型，不使用 .en 版本。
WHISPER_MODEL_OPTIONS = ["base", "small", "medium"]
DEFAULT_WHISPER_MODEL = "small"
OPENAI_WHISPER_LABEL = "OpenAI Whisper API"
LOCAL_WHISPER_LABEL = "本地 faster-whisper"
COMPARE_MODELS = ["medium", OPENAI_WHISPER_LABEL]

# 临时工作目录
WORK_DIR = "/tmp/anki-streamlit"
os.makedirs(WORK_DIR, exist_ok=True)

# 持久化任务目录：保存转写结果、翻译、标准化音频和切割后的音频。
TASK_ARCHIVE_DIR = os.environ.get("ANKI_STREAMLIT_TASK_DIR", "/var/lib/anki-streamlit/tasks")
os.makedirs(TASK_ARCHIVE_DIR, exist_ok=True)


# ============================================================
# 模型单例（Streamlit 缓存）
# ============================================================

@st.cache_resource
def load_whisper_model(model_size: str = DEFAULT_WHISPER_MODEL):
    """加载 Whisper 时间戳模型。"""
    with st.spinner(f"正在加载 Whisper {model_size} 模型..."):
        return WhisperTimestampExtractor(
            model_size=model_size,
            device="cpu",
            compute_type="int8",
        )


@st.cache_resource
def load_cohere_asr():
    """Load Cohere ASR for text-only transcription."""
    with st.spinner("正在加载 Cohere ASR 模型..."):
        return CohereASR(device="cpu")


def build_transcriber(engine: str, model_size: str, api_key: str = ""):
    """Create a transcription backend for the selected engine."""
    if engine == OPENAI_WHISPER_LABEL:
        return OpenAIWhisperAPI(api_key=api_key)
    return load_whisper_model(model_size)


@st.cache_data
def load_translator():
    """初始化 Google 翻译器。"""
    return GoogleTranslator(source="de", target="zh-CN")


# ============================================================
# 辅助函数
# ============================================================

def convert_to_mp3(input_path: str) -> str:
    """
    将音频文件转换为 MP3（如果还不是 MP3）。
    返回 MP3 文件路径。
    """
    ext = Path(input_path).suffix.lower()
    if ext == ".mp3":
        return input_path

    output_path = input_path + ".mp3"
    from pydub import AudioSegment
    audio = AudioSegment.from_file(input_path)
    audio.export(output_path, format="mp3")
    return output_path


def normalize_uploaded_audio(input_path: str, output_dir: str) -> str:
    """Normalize audio by calling normalize_audio.py."""
    stem = Path(input_path).stem
    output_path = os.path.join(output_dir, f"{stem}.normalized.mp3")
    script_path = "/opt/anki-app/normalize_audio.py"
    proc = subprocess.run(
        [
            sys.executable,
            script_path,
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


def save_uploaded_file(uploaded_file) -> str:
    """保存上传文件到临时目录。"""
    file_path = os.path.join(WORK_DIR, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path


def uploaded_file_hash(uploaded_file) -> str:
    """Return a stable hash for the uploaded file."""
    return hashlib.sha256(uploaded_file.getbuffer()).hexdigest()


def get_session_dir() -> str:
    """为当前 session 创建唯一工作目录。"""
    session_dir = os.path.join(WORK_DIR, st.session_state.session_id)
    os.makedirs(session_dir, exist_ok=True)
    return session_dir


def task_archive_dir(task_id: str) -> str:
    """Return/create the persistent archive directory for a task."""
    path = os.path.join(TASK_ARCHIVE_DIR, task_id)
    os.makedirs(path, exist_ok=True)
    return path


def copy_file_to_dir(src_path: str, dst_dir: str) -> str:
    """Copy a file into dst_dir, skipping work when an identical file exists."""
    if not src_path or not os.path.exists(src_path):
        return ""
    os.makedirs(dst_dir, exist_ok=True)
    dst_path = os.path.join(dst_dir, os.path.basename(src_path))
    if not os.path.exists(dst_path) or os.path.getsize(dst_path) != os.path.getsize(src_path):
        shutil.copy2(src_path, dst_path)
    return dst_path


def copy_clips_to_archive(audio_dir: str, archive_dir: str) -> str:
    """Copy split sentence clips into the persistent task archive."""
    if not audio_dir or not os.path.isdir(audio_dir):
        return ""
    clips_archive = os.path.join(archive_dir, "clips")
    os.makedirs(clips_archive, exist_ok=True)
    for clip in sorted(Path(audio_dir).glob("clip_*.mp3")):
        copy_file_to_dir(str(clip), clips_archive)
    return clips_archive


def save_task_archive(upload_name: str = "") -> None:
    """Persist the current transcription task and generated audio clips."""
    task_id = st.session_state.get("task_id") or st.session_state.session_id
    st.session_state.task_id = task_id
    archive_dir = task_archive_dir(task_id)

    normalized_archive = copy_file_to_dir(
        st.session_state.get("normalized_audio_path", ""),
        archive_dir,
    )
    clips_archive = copy_clips_to_archive(
        st.session_state.get("audio_dir", ""),
        archive_dir,
    )

    data = {
        "task_id": task_id,
        "upload_name": upload_name or st.session_state.get("upload_name", ""),
        "upload_key": st.session_state.get("normalized_audio_upload_key", ""),
        "created_at": st.session_state.get("task_created_at", datetime.utcnow().isoformat(timespec="seconds") + "Z"),
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "normalized_audio_path": normalized_archive or st.session_state.get("normalized_audio_path", ""),
        "audio_dir": clips_archive or st.session_state.get("audio_dir", ""),
        "segments": st.session_state.get("segments", []),
        "translations": st.session_state.get("translations", []),
        "edited_german_texts": st.session_state.get("edited_german_texts", {}),
        "edited_chinese_texts": st.session_state.get("edited_chinese_texts", {}),
        "selected_indices": st.session_state.get("selected_indices", []),
        "cohere_text": st.session_state.get("cohere_text", ""),
    }
    st.session_state.task_created_at = data["created_at"]
    with open(os.path.join(archive_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def translate_batch(
    texts: list[str],
    translator: GoogleTranslator,
    progress_callback=None,
) -> list[str]:
    """
    批量翻译德语文本为中文。
    
    Args:
        texts: 德语文本列表
        translator: GoogleTranslator 实例
        progress_callback: 进度回调函数
    
    Returns:
        中文翻译列表
    """
    translations = []
    total = len(texts)
    
    for i, text in enumerate(texts):
        try:
            result = translator.translate(text)
            translations.append(result)
        except Exception as e:
            logger.warning(f"翻译失败 (句子 {i+1}): {e}")
            translations.append("")
        
        if progress_callback:
            progress_callback((i + 1) / total)
    
    return translations


def run_transcription_comparison(
    audio_path: str,
    output_base_dir: str,
    api_key: str = "",
) -> list[dict]:
    """Run the same audio through comparison models and cut sentence clips."""
    results = []
    for model_name in COMPARE_MODELS:
        started = time.perf_counter()
        try:
            if model_name == OPENAI_WHISPER_LABEL:
                transcriber = OpenAIWhisperAPI(api_key=api_key)
            else:
                transcriber = load_whisper_model(model_name)

            safe_name = model_name.replace(" ", "_").replace("/", "_").lower()
            output_dir = os.path.join(output_base_dir, safe_name)
            os.makedirs(output_dir, exist_ok=True)
            segments, clip_paths = process_pipeline(
                audio_path=audio_path,
                asr_model=None,
                whisper_extractor=transcriber,
                output_dir=output_dir,
            )
            text = " ".join(
                segment.get("text", "").strip()
                for segment in segments
                if segment.get("text", "").strip()
            )
            elapsed = time.perf_counter() - started
            results.append({
                "模型": model_name,
                "耗时(秒)": round(elapsed, 1),
                "句子数": len(segments),
                "字符数": len(text),
                "状态": "成功",
                "转录文本": text,
                "句子": segments,
                "音频": clip_paths,
                "错误": "",
            })
        except Exception as e:
            elapsed = time.perf_counter() - started
            results.append({
                "模型": model_name,
                "耗时(秒)": round(elapsed, 1),
                "句子数": 0,
                "字符数": 0,
                "状态": "失败",
                "转录文本": "",
                "句子": [],
                "音频": [],
                "错误": str(e),
            })
    return results


# ============================================================
# Session 状态初始化
# ============================================================

if "session_id" not in st.session_state:
    st.session_state.session_id = time.strftime("%Y%m%d_%H%M%S")

if "task_id" not in st.session_state:
    st.session_state.task_id = ""

if "upload_name" not in st.session_state:
    st.session_state.upload_name = ""

if "task_created_at" not in st.session_state:
    st.session_state.task_created_at = ""

if "segments" not in st.session_state:
    st.session_state.segments = []

if "selected_indices" not in st.session_state:
    st.session_state.selected_indices = []

if "translations" not in st.session_state:
    st.session_state.translations = []

if "audio_dir" not in st.session_state:
    st.session_state.audio_dir = ""

if "normalized_audio_path" not in st.session_state:
    st.session_state.normalized_audio_path = ""

if "normalized_audio_upload_key" not in st.session_state:
    st.session_state.normalized_audio_upload_key = ""

if "processing_done" not in st.session_state:
    st.session_state.processing_done = False

if "translation_done" not in st.session_state:
    st.session_state.translation_done = False

if "comparison_results" not in st.session_state:
    st.session_state.comparison_results = []

if "edited_german_texts" not in st.session_state:
    st.session_state.edited_german_texts = {}

if "edited_chinese_texts" not in st.session_state:
    st.session_state.edited_chinese_texts = {}

if "deck_name" not in st.session_state:
    st.session_state.deck_name = "德语听力"

if "cohere_text" not in st.session_state:
    st.session_state.cohere_text = ""


# ============================================================
# 主界面
# ============================================================

st.title("🎧 德语听力卡片生成器")
st.markdown(
    """
    上传德语音频 → 自动识别并切割句子 → 选择 → 翻译 → 导出 Anki 卡片
    """
)

# 侧边栏 - 模型状态
with st.sidebar:
    st.subheader("Development")
    st.link_button(
        "Open production app",
        "https://anki.3mudi.com/",
        use_container_width=True,
    )
    st.caption("Legacy page kept for development verification.")
    st.divider()

    with st.expander("系统状态", expanded=False):
        try:
            loaded_model = st.session_state.get("whisper_model_loaded", "")
            st.info(f"Whisper: ✅ {loaded_model} 已就绪" if loaded_model else "Whisper: ⏳ 待加载")
        except Exception:
            pass

        if is_rest_api_available():
            st.success("Anki 云：✅ REST API 可用")
        else:
            st.info("Anki 云：使用本地同步写入")

    st.subheader("识别设置")
    recognition_engine = st.selectbox(
        "识别引擎",
        [OPENAI_WHISPER_LABEL, LOCAL_WHISPER_LABEL],
        help="OpenAI Whisper API 需要 OPENAI_API_KEY，且单文件上限 25 MB。",
    )
    whisper_model_size = st.selectbox(
        "Whisper 模型大小",
        WHISPER_MODEL_OPTIONS,
        index=WHISPER_MODEL_OPTIONS.index(DEFAULT_WHISPER_MODEL),
        disabled=recognition_engine == OPENAI_WHISPER_LABEL,
        help="small 是默认推荐；medium 更准但明显更慢；base 更快但质量较低。",
    )
    openai_api_key_input = st.text_input(
        "OpenAI API Key",
        type="password",
        help="可留空使用服务器环境变量 OPENAI_API_KEY；此输入只在当前页面会话中使用。",
    )

    st.subheader("Anki 设置")
    sidebar_deck_name = st.text_input(
        "目标牌组 / Deck",
        value=st.session_state.deck_name,
        key="deck_name_sidebar",
        help="推送到 Anki sync server 的牌组名称；不存在会自动创建。",
    )
    st.session_state.deck_name = sidebar_deck_name
    
    st.divider()
    
    # 使用说明
    with st.expander("使用说明", expanded=False):
        st.markdown(
            """
            1. 上传德语音频文件 (MP3/WAV)
            2. 等待自动识别与切割
            3. 勾选要学习的句子
            4. 使用 Google 免费翻译并人工修正
            5. 设置牌组后推送到 Anki 服务器
            """
        )


# ============================================================
# Step 1: 上传音频
# ============================================================

st.header("📤 第一步：上传音频")

uploaded_file = st.file_uploader(
    "选择德语录音文件",
    type=SUPPORTED_FORMATS,
    help="支持 MP3、WAV、M4A、OGG 格式",
)

if uploaded_file is not None:
    file_hash = uploaded_file_hash(uploaded_file)
    current_upload_key = f"{uploaded_file.name}:{getattr(uploaded_file, 'size', 0)}:{file_hash[:16]}"
    st.audio(uploaded_file, format=f"audio/{uploaded_file.type.split('/')[-1]}")
    st.caption("上传后会自动执行标准化（MP3 / mono / 16 kHz / 96 kbps），转写只使用标准化后的音频。")
    if not (
        st.session_state.normalized_audio_upload_key == current_upload_key
        and st.session_state.normalized_audio_path
        and os.path.exists(st.session_state.normalized_audio_path)
    ):
        with st.status("标准化音频中...", expanded=True) as status:
            progress = st.progress(0, text="保存上传文件...")
            audio_path = save_uploaded_file(uploaded_file)
            session_dir = get_session_dir()
            os.makedirs(session_dir, exist_ok=True)
            progress.progress(35, text="调用 normalize_audio.py...")
            normalized_path = normalize_uploaded_audio(audio_path, session_dir)
            progress.progress(85, text="读取标准化音频信息...")
            st.session_state.task_id = file_hash[:16]
            st.session_state.upload_name = uploaded_file.name
            st.session_state.task_created_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            st.session_state.normalized_audio_path = normalized_path
            st.session_state.normalized_audio_upload_key = current_upload_key
            save_task_archive(uploaded_file.name)
            try:
                st.json(describe_audio(normalized_path))
            except Exception as e:
                logger.warning(f"无法读取标准化音频信息: {e}")
            progress.progress(100, text="标准化完成")
            status.update(label="标准化完成", state="complete")
        st.rerun()
    if (
        st.session_state.normalized_audio_upload_key == current_upload_key
        and st.session_state.normalized_audio_path
        and os.path.exists(st.session_state.normalized_audio_path)
    ):
        with open(st.session_state.normalized_audio_path, "rb") as normalized_file:
            st.download_button(
                "⬇️ 下载标准化音频（MP3 / mono / 16 kHz / 96 kbps）",
                normalized_file.read(),
                file_name=Path(st.session_state.normalized_audio_path).name,
                mime="audio/mpeg",
                use_container_width=True,
            )
    
    # 处理按钮
    if st.button("🎯 仅 Cohere 转写文本", use_container_width=True):
        with st.status("Cohere 转写中...", expanded=True) as status:
            st.write("🎧 使用已标准化音频...")
            audio_path = st.session_state.normalized_audio_path

            st.write("🤖 加载 Cohere ASR...")
            cohere_asr = load_cohere_asr()
            st.write("📝 开始转写（仅文本，不分句不切片）...")
            text = cohere_asr.transcribe(audio_path, language="de")
            st.session_state.cohere_text = text or ""
            save_task_archive(uploaded_file.name)
            status.update(label="✅ Cohere 转写完成", state="complete")

        if st.session_state.cohere_text:
            st.success("Cohere 转写完成")
        else:
            st.warning("Cohere 未返回可用文本")
        st.rerun()

    if st.session_state.cohere_text:
        st.subheader("Cohere 转写结果（文本）")
        st.text_area(
            "转写文本",
            value=st.session_state.cohere_text,
            height=220,
            key="cohere_text_view",
        )
        st.download_button(
            "⬇️ 下载 Cohere 转写文本 (.txt)",
            st.session_state.cohere_text.encode("utf-8"),
            file_name=f"{Path(uploaded_file.name).stem}.cohere.txt",
            mime="text/plain",
            use_container_width=True,
        )

    if st.button("🚀 开始识别与切割", type="primary", use_container_width=True):
        with st.status("处理中...", expanded=True) as status:
            # 重置状态
            st.session_state.segments = []
            st.session_state.selected_indices = []
            st.session_state.translations = []
            st.session_state.processing_done = False
            st.session_state.translation_done = False
            st.session_state.whisper_model_loaded = ""
            st.session_state.edited_german_texts = {}
            st.session_state.edited_chinese_texts = {}
            # 创建输出目录
            session_dir = get_session_dir()
            clips_dir = os.path.join(session_dir, "clips")
            os.makedirs(clips_dir, exist_ok=True)

            # 使用上传后生成的标准化音频
            st.write("🎧 使用已标准化音频...")
            audio_path = st.session_state.normalized_audio_path
            
            # 加载模型
            active_model_label = (
                OPENAI_WHISPER_LABEL
                if recognition_engine == OPENAI_WHISPER_LABEL
                else f"Whisper {whisper_model_size}"
            )
            st.write(f"🤖 加载 {active_model_label}...")
            whisper = build_transcriber(
                recognition_engine,
                whisper_model_size,
                openai_api_key_input,
            )
            st.session_state.whisper_loaded = True
            st.session_state.whisper_model_loaded = active_model_label
            
            # 运行流水线
            st.write("🎯 运行语音识别流水线...")
            progress_bar = st.progress(0, text="转录中...")
            progress_note = st.empty()

            def pipeline_progress(stage, current, total, message):
                if stage == "whisper":
                    progress_bar.progress(35, text="Whisper 转写并提取时间戳...")
                elif stage == "align":
                    progress_bar.progress(75, text="根据 Whisper 文本划分句子...")
                elif stage == "cut":
                    progress_bar.progress(90, text="切割句子音频...")
                if message:
                    progress_note.info(message)
            
            segments, clip_paths = process_pipeline(
                audio_path=audio_path,
                asr_model=None,
                whisper_extractor=whisper,
                output_dir=clips_dir,
                progress_callback=pipeline_progress,
            )
            
            progress_bar.progress(100, text="完成!")
            
            # 保存结果到 session
            st.session_state.segments = segments
            st.session_state.edited_german_texts = {
                idx: seg["text"] for idx, seg in enumerate(segments)
            }
            st.session_state.audio_dir = clips_dir

            # 自动翻译所有句子，方便用户直接阅读和修正
            st.write("🌐 使用 Google 免费翻译所有句子（德语→中文）...")
            translation_bar = st.progress(0, text="翻译中...")
            translator = load_translator()
            all_texts = [seg["text"] for seg in segments]
            translations = translate_batch(
                all_texts,
                translator,
                progress_callback=lambda p: translation_bar.progress(
                    p,
                    text=f"翻译中... {int(p * 100)}%",
                ),
            )
            st.session_state.translations = translations
            st.session_state.edited_chinese_texts = {
                idx: translations[idx] for idx in range(len(translations))
            }
            st.session_state.translation_done = True
            st.session_state.processing_done = True
            save_task_archive(uploaded_file.name)
            
            status.update(label="✅ 处理完成!", state="complete")
        
        st.success(f"识别和翻译完成！共 {len(segments)} 个句子")
        st.rerun()

    st.divider()
    st.subheader("模型对比")
    st.caption("对同一段音频依次运行 medium 和 OpenAI Whisper API，比较耗时、转录文本和句子切片。")
    if st.button("🔬 对比 Medium 与 OpenAI Whisper", use_container_width=True):
        with st.status("正在对比模型...", expanded=True) as status:
            st.write("📁 保存并转换上传文件...")
            compare_audio_path = save_uploaded_file(uploaded_file)
            compare_base_dir = os.path.join(
                get_session_dir(),
                "comparison",
                time.strftime("%Y%m%d_%H%M%S"),
            )
            os.makedirs(compare_base_dir, exist_ok=True)
            st.write("🎚️ 标准化对比音频...")
            compare_audio_path = normalize_uploaded_audio(compare_audio_path, compare_base_dir)
            st.session_state.normalized_audio_path = compare_audio_path
            results = []

            for model_name in COMPARE_MODELS:
                st.write(f"🎙️ 正在运行 {model_name} 并按句子切割...")
                started = time.perf_counter()
                try:
                    if model_name == OPENAI_WHISPER_LABEL:
                        transcriber = OpenAIWhisperAPI(api_key=openai_api_key_input)
                    else:
                        transcriber = load_whisper_model(model_name)

                    safe_name = model_name.replace(" ", "_").replace("/", "_").lower()
                    output_dir = os.path.join(compare_base_dir, safe_name)
                    os.makedirs(output_dir, exist_ok=True)
                    segments, clip_paths = process_pipeline(
                        audio_path=compare_audio_path,
                        asr_model=None,
                        whisper_extractor=transcriber,
                        output_dir=output_dir,
                    )
                    text = " ".join(
                        segment.get("text", "").strip()
                        for segment in segments
                        if segment.get("text", "").strip()
                    )
                    elapsed = time.perf_counter() - started
                    results.append({
                        "模型": model_name,
                        "耗时(秒)": round(elapsed, 1),
                        "句子数": len(segments),
                        "字符数": len(text),
                        "状态": "成功",
                        "转录文本": text,
                        "句子": segments,
                        "音频": clip_paths,
                        "错误": "",
                    })
                except Exception as e:
                    elapsed = time.perf_counter() - started
                    results.append({
                        "模型": model_name,
                        "耗时(秒)": round(elapsed, 1),
                        "句子数": 0,
                        "字符数": 0,
                        "状态": "失败",
                        "转录文本": "",
                        "句子": [],
                        "音频": [],
                        "错误": str(e),
                    })

            st.session_state.comparison_results = results
            status.update(label="✅ 模型对比完成", state="complete")
        st.rerun()

    if st.session_state.comparison_results:
        summary_rows = [
            {k: v for k, v in row.items() if k not in ("转录文本", "错误", "句子", "音频")}
            for row in st.session_state.comparison_results
        ]
        st.dataframe(summary_rows, use_container_width=True)

        for row in st.session_state.comparison_results:
            label = f"{row['模型']} · {row['状态']} · {row['耗时(秒)']} 秒"
            with st.expander(label):
                if row["错误"]:
                    st.error(row["错误"])
                st.text_area(
                    "转录文本",
                    row["转录文本"],
                    height=220,
                    key=f"compare_text_{row['模型']}",
                )
                if row["句子"]:
                    st.markdown("**按句子切割结果**")
                    for idx, seg in enumerate(row["句子"]):
                        clip_path = row["音频"][idx] if idx < len(row["音频"]) else ""
                        col_audio, col_text = st.columns([2, 5])
                        with col_audio:
                            if clip_path and os.path.exists(clip_path):
                                with open(clip_path, "rb") as f:
                                    st.audio(f.read(), format="audio/mp3")
                        with col_text:
                            st.markdown(f"**{idx + 1}.** {seg['text']}")
                            st.caption(f"{seg['start']:.1f}s - {seg['end']:.1f}s")


# ============================================================
# Step 2: 选择句子
# ============================================================

if st.session_state.processing_done:
    st.header("✏️ 第二步：阅读、修正并选择句子")
    
    segments = st.session_state.segments
    audio_dir = st.session_state.audio_dir
    
    # 全选/取消全选
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("✅ 全选"):
            st.session_state.selected_indices = list(range(len(segments)))
            st.rerun()
    with col2:
        if st.button("❌ 取消全选"):
            st.session_state.selected_indices = []
            st.rerun()
    
    st.divider()
    
    st.caption("所有句子已自动使用 Google 免费翻译。你可以直接修改德语原文和中文翻译，再勾选要推送到 Anki 的句子。")

    # 显示句子列表
    for i, seg in enumerate(segments):
        clip_path = os.path.join(audio_dir, f"clip_{i+1:03d}.mp3")
        
        col1, col2, col3, col4 = st.columns([1, 2, 4, 4])
        
        with col1:
            # 勾选框
            checked = st.checkbox(
                "选择",
                key=f"select_{i}",
                value=i in st.session_state.selected_indices,
                label_visibility="collapsed",
            )
            if checked and i not in st.session_state.selected_indices:
                st.session_state.selected_indices.append(i)
            elif not checked and i in st.session_state.selected_indices:
                st.session_state.selected_indices.remove(i)
        
        with col2:
            # 试听
            if os.path.exists(clip_path):
                with open(clip_path, "rb") as f:
                    st.audio(f.read(), format="audio/mp3")
        
        with col3:
            # 德语文本，可在推送前人工修正
            german_value = st.session_state.edited_german_texts.get(i, seg["text"])
            edited_german = st.text_area(
                f"{i+1}. 德语文本",
                value=german_value,
                key=f"edit_german_{i}",
                height=120,
            )
            st.session_state.edited_german_texts[i] = edited_german
            seg["text"] = edited_german
            st.caption(f"⏱ {seg['start']:.1f}s - {seg['end']:.1f}s")

        with col4:
            chinese_value = st.session_state.edited_chinese_texts.get(
                i,
                st.session_state.translations[i] if i < len(st.session_state.translations) else "",
            )
            edited_chinese = st.text_area(
                f"{i+1}. 中文翻译",
                value=chinese_value,
                key=f"edit_chinese_{i}",
                height=120,
            )
            st.session_state.edited_chinese_texts[i] = edited_chinese
        
        st.divider()

    save_task_archive(st.session_state.get("upload_name", ""))
    
    # 选中数量
    selected_count = len(st.session_state.selected_indices)
    st.info(f"已选择 {selected_count} / {len(segments)} 个句子")
    
    # 推送按钮
    if selected_count > 0:
        st.header("📦 第三步：推送卡片到服务器")

        col1, col2 = st.columns([3, 3])

        with col1:
            deck_name = st.text_input(
                "牌组名称 / Deck",
                key="deck_name_push",
                value=st.session_state.deck_name,
                help="Anki sync server 中的牌组名称（不存在会自动创建）",
            )

        with col2:
            st.info("📡 直接推送到自建 Anki 服务器，无需手动导入")

        if st.button("🚀 一键推送到服务器", type="primary", use_container_width=True):
            with st.status("推送卡片到服务器...", expanded=True) as status:
                sentences = []
                for i in st.session_state.selected_indices:
                    seg = segments[i]
                    sentences.append({
                        "audio_filename": f"clip_{i+1:03d}.mp3",
                        "german_text": st.session_state.edited_german_texts.get(i, seg["text"]),
                        "chinese_text": st.session_state.edited_chinese_texts.get(
                            i,
                            st.session_state.translations[i] if i < len(st.session_state.translations) else "",
                        ),
                    })

                status.write(f"📦 准备推送 {len(sentences)} 张卡片到牌组「{deck_name}」...")

                from anki_sync_push_safe import push_cards_to_server
                result = push_cards_to_server(sentences, audio_dir, deck_name)

                if result["success"]:
                    status.update(label="✅ 推送成功!", state="complete")
                    st.success(f"✅ {result['message']}")

                    with st.expander("📖 同步到 Anki 客户端"):
                        st.markdown(
                            f"""
                            卡片已直接写入服务器数据库，打开 Anki 客户端同步即可：

                            1. **Anki Desktop**: 工具 → 设置 → 同步 → 自建同步服务器
                               - 服务器: `http://89.168.93.94:8080`
                               - 用户名: `anki_user`
                               - 密码: `anki_sync_2024`
                            2. 点击 **同步** 按钮（☁️）
                            3. 卡片出现在牌组「**{deck_name}**」中
                            """
                        )
                else:
                    status.update(label="❌ 推送失败", state="error")
                    st.error(f"❌ {result['message']}")
                    st.info("💡 请检查 sync server 是否正常运行：`sudo docker restart anki-sync-standalone`")
                    st.stop()

# ============================================================
# 页脚
# ============================================================

st.divider()
st.caption(
    "由 Oracle Cloud Frankfurt 托管的德语学习工具 | "
    "faster-whisper | "
    "自建 Anki 同步服务器"
)
