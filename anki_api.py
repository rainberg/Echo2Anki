"""
anki_api.py — Anki 卡片生成与导出模块

功能：
1. 使用 genanki 生成 .apkg 文件（含嵌入音频）
2. 提供下载接口（.apkg 文件）
3. 后续可扩展为调用 anki-cloud REST API（完整平台部署后）

依赖：
- genanki
- pydub (音频处理)

环境变量（可选，当前主要通过 genanki 导出）:
- ANKI_API_BASE: anki-cloud REST API 地址（未来扩展）
- ANKI_API_TOKEN: API 令牌（未来扩展）
"""

import os
import genanki
import logging
from typing import Optional, Dict, Any
import tempfile
import shutil

logger = logging.getLogger(__name__)

# ============================================================
# Note Model（卡片模板）
# ============================================================

# 德语听力卡片模型 ID（固定，避免每次不同）
GERMAN_AUDIO_MODEL_ID = 1726354051

# 创建笔记类型
german_audio_model = genanki.Model(
    GERMAN_AUDIO_MODEL_ID,
    "GermanAudioCard",
    fields=[
        {"name": "Audio"},      # [sound:xxx.mp3]
        {"name": "German"},     # 德语原文
        {"name": "Chinese"},    # 中文翻译
    ],
    templates=[
        {
            "name": "German Listening",
            "qfmt": "{{Audio}}",            # 正面只显示音频播放器
            "afmt": "{{FrontSide}}\n\n<hr id=answer>\n\n<b>{{German}}</b>\n<br>\n<i>{{Chinese}}</i>",  # 背面：德语 + 中文
        },
    ],
    css="""
.card {
    font-family: 'Noto Sans SC', 'Microsoft YaHei', Arial, sans-serif;
    font-size: 20px;
    text-align: center;
    color: #333;
    padding: 20px;
}
.german {
    font-size: 24px;
    font-weight: bold;
    color: #1a5276;
}
.chinese {
    font-size: 18px;
    color: #666;
    margin-top: 10px;
}
""",
)


# ============================================================
# Deck（牌组）
# ============================================================

DEFAULT_DECK_NAME = "德语听力"


def create_deck(deck_name: str = DEFAULT_DECK_NAME) -> genanki.Deck:
    """创建或获取牌组。"""
    # genanki 会自动处理牌组 ID（基于名称）
    deck_id = abs(hash(deck_name)) % (10 ** 10)
    return genanki.Deck(deck_id, deck_name)


# ============================================================
# Media Files（媒体文件管理）
# ============================================================

class MediaManager:
    """管理 apkg 中的媒体文件（音频片段）。"""

    def __init__(self):
        self.files = []

    def add_audio(self, audio_path: str) -> str:
        """
        注册一个音频文件到包中。
        返回文件名（用于字段引用）。
        """
        basename = os.path.basename(audio_path)
        if basename not in self.files:
            self.files.append(basename)
        return basename


# ============================================================
# Note Builder（笔记构建）
# ============================================================

class NoteBuilder:
    """构建带音频的 Anki 笔记。"""

    def __init__(self, media_mgr: MediaManager):
        self.media_mgr = media_mgr

    def create_note(
        self,
        audio_path: str,
        german_text: str,
        chinese_text: str,
        tags: Optional[list] = None,
    ) -> genanki.Note:
        """
        创建一张 Anki 笔记卡。

        Args:
            audio_path: 音频文件的路径
            german_text: 德语原文
            chinese_text: 中文翻译
            tags: 标签列表

        Returns:
            genanki.Note
        """
        if tags is None:
            tags = ["deutsch-lernen"]

        # 注册音频文件
        audio_filename = self.media_mgr.add_audio(audio_path)

        return genanki.Note(
            model=german_audio_model,
            fields=[
                f"[sound:{audio_filename}]",   # Audio 字段
                german_text,                     # German 字段
                chinese_text,                    # Chinese 字段
            ],
            tags=tags,
        )


# ============================================================
# Package Exporter（包导出）
# ============================================================

class AnkiPackageExporter:
    """
    导出 genanki 包 (.apkg)。

    使用方式：
        exporter = AnkiPackageExporter()
        apkg_path = exporter.export(sentences, audio_dir, output_path)
    """

    def __init__(
        self,
        deck_name: str = DEFAULT_DECK_NAME,
    ):
        self.deck_name = deck_name
        self.media_mgr = MediaManager()
        self.note_builder = NoteBuilder(self.media_mgr)

    def export(
        self,
        sentences: list[Dict[str, Any]],
        audio_dir: str,
        output_path: str,
    ) -> str:
        """
        将句子列表导出为 .apkg 文件。

        Args:
            sentences: [{audio_filename, german_text, chinese_text}, ...]
            audio_dir: 音频文件所在目录
            output_path: 输出 .apkg 路径

        Returns:
            生成的 .apkg 文件路径
        """
        deck = create_deck(self.deck_name)

        for item in sentences:
            audio_path = os.path.join(audio_dir, item["audio_filename"])
            if not os.path.exists(audio_path):
                logger.warning(f"音频文件不存在: {audio_path}")
                continue

            note = self.note_builder.create_note(
                audio_path=audio_path,
                german_text=item["german_text"],
                chinese_text=item.get("chinese_text", ""),
                tags=item.get("tags", ["deutsch-lernen"]),
            )
            deck.add_note(note)

        # 创建包
        package = genanki.Package(deck)
        package.media_files = [
            os.path.join(audio_dir, f)
            for f in self.media_mgr.files
            if os.path.exists(os.path.join(audio_dir, f))
        ]

        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # 写入文件
        package.write_to_file(output_path)
        logger.info(f"已导出 {len(sentences)} 张卡片到 {output_path}")

        return output_path


# ============================================================
# anki-cloud REST API（预留）
# ============================================================

# 环境变量
ANKI_API_BASE = os.environ.get("ANKI_API_BASE", "http://localhost:8080/api/v1")
ANKI_API_TOKEN = os.environ.get("ANKI_API_TOKEN", "")


def is_rest_api_available() -> bool:
    """检查 anki-cloud REST API 是否可用（需要完整平台部署）。"""
    if not ANKI_API_TOKEN:
        return False
    try:
        import requests
        r = requests.get(f"{ANKI_API_BASE}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def add_card_via_api(
    deck_name: str,
    german_text: str,
    chinese_text: str,
    audio_data: Optional[bytes] = None,
) -> Dict[str, Any]:
    """
    通过 anki-cloud REST API 添加卡片（需要完整平台部署）。
    当前为预留接口，待平台升级后启用。

    Args:
        deck_name: 牌组名称
        german_text: 德语原文
        chinese_text: 中文翻译
        audio_data: 音频二进制数据

    Returns:
        API 响应
    """
    raise NotImplementedError(
        "anki-cloud REST API 需要完整平台部署（含 Bun + 数据库 + OAuth）。\n"
        "当前运行的是 standalone 模式，请使用 genanki 导出 .apkg 文件。"
    )
