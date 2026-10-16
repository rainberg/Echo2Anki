"""
anki_sync_push.py — 直接将卡片推送到自建 Anki Sync Server

功能：
1. 暂停 sync server 容器（防止数据库锁冲突）
2. 将卡片数据写入 collection.anki2 的 notes/cards 表
3. 复制音频文件到 media 目录
4. 重启 sync server 容器
5. 更新同步状态标记，使下次 sync 时正常同步

数据格式：
- 使用 Anki 内置的 Basic note type（Front/Back 字段）
- Front: 德语原文（含 [sound:filename.mp3] 引用）
- Back: 中文翻译
- 音频文件存入 media 目录
"""

import os
import shutil
import time
import hashlib
import struct
import zlib
import json
import subprocess
import tempfile
import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

# ============================================================
# Sudo 包装
# ============================================================

def _run(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    """运行命令，自动带 sudo 处理 docker volume 文件操作。"""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30, **kwargs)


def _copy_with_sudo(src: str, dst: str):
    """使用 sudo cp 复制文件（root 权限）。"""
    _run(["sudo", "cp", src, dst])


def _write_file_with_sudo(content: bytes, dst: str):
    """使用 sudo tee 写入文件。"""
    proc = subprocess.Popen(
        ["sudo", "tee", dst],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    proc.communicate(content)
    proc.wait()


def _mkdir_with_sudo(path: str):
    """使用 sudo mkdir -p 创建目录。"""
    _run(["sudo", "mkdir", "-p", path])


def _chmod_with_sudo(path: str, mode: str = "644"):
    """使用 sudo chmod 设置权限。"""
    _run(["sudo", "chmod", mode, path])


def _chown_with_sudo(path: str, owner: str = "ubuntu"):
    """使用 sudo chown 更改所有者。"""
    _run(["sudo", "chown", owner, path])

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

# Docker volume 中的数据路径
DATA_DIR = "/var/lib/docker/volumes/anki-cloud_app-data/_data/anki_user"
COLLECTION_DB = os.path.join(DATA_DIR, "collection.anki2")
MEDIA_DIR = os.path.join(DATA_DIR, "media")
MEDIA_DB = os.path.join(DATA_DIR, "media.db")

# Anki Basic note type ID（已存在于数据库中）
BASIC_NOTE_TYPE_ID = 1623434819882

# Default deck ID（我们使用 Default 牌组，也可创建新牌组）
DEFAULT_DECK_ID = 1

# 容器名称
CONTAINER_NAME = "anki-sync-standalone"

# ============================================================
# Utilities
# ============================================================

def _now_ms() -> int:
    """返回毫秒级时间戳。"""
    return int(time.time() * 1000)


def _crc32_checksum(text: str) -> int:
    """计算 Anki 的 csum（第一个字段的小写去空格后 crc32）。"""
    # 只使用第一个字段（Front）
    clean = text.strip().lower()
    return zlib.crc32(clean.encode("utf-8")) & 0xFFFFFFFF


def _generate_guid() -> str:
    """生成 Anki GUID（8 位 base64 字符）。"""
    # Anki 使用 os.urandom 生成 8 字节然后 base64
    import base64
    random_bytes = os.urandom(8)
    return base64.b64encode(random_bytes, altchars=b"-_").decode("ascii").rstrip("=")


def _next_note_id() -> int:
    """生成新的 note ID（基于时间戳+随机数）。"""
    return int(time.time() * 1000) + random.randint(0, 999)


def _next_card_id() -> int:
    """生成新的 card ID。"""
    return int(time.time() * 1000) + random.randint(0, 999)


import random


def _next_row_id(conn, table: str) -> int:
    """返回指定表的下一个可用整数 ID（max(id)+1）。"""
    row = conn.execute(f"SELECT MAX(id) FROM {table}").fetchone()
    max_id = row[0] if row and row[0] is not None else 0
    return int(max_id) + 1


def _get_deck_id(deck_name: str, conn) -> int:
    """获取或创建牌组，返回 deck ID。"""
    import sqlite3
    
    row = conn.execute("SELECT id FROM decks WHERE name = ?", (deck_name,)).fetchone()
    if row:
        return row[0]
    
    # 创建新牌组
    deck_id = int(time.time() * 1000)
    conn.execute(
        "INSERT INTO decks (id, name, mtime_secs, usn, common, kind) VALUES (?, ?, ?, ?, ?, ?)",
        (deck_id, deck_name, int(time.time()), -1, "", "")
    )
    return deck_id


def _get_last_usn(conn) -> int:
    """获取当前的 usn 最大值。"""
    max_usn = conn.execute("SELECT MAX(usn) FROM notes").fetchone()[0]
    max_usn2 = conn.execute("SELECT MAX(usn) FROM cards").fetchone()[0]
    return max(max_usn or 0, max_usn2 or 0)


def _next_new_card_due(conn, deck_id: int) -> int:
    """获取指定牌组中新卡队列的下一个 due 序号。"""
    max_due = conn.execute(
        "SELECT MAX(due) FROM cards WHERE did = ? AND queue = 0 AND type = 0",
        (deck_id,),
    ).fetchone()[0]
    return (max_due or 0) + 1


# ============================================================
# 核心功能
# ============================================================

class AnkiSyncPusher:
    """将卡片直接推送到 sync server 的 SQLite 数据库。"""

    def __init__(self):
        self.temp_dir = None  # 用于存放备份文件

    def _stop_container(self):
        """暂停 sync server 容器。"""
        logger.info("正在停止 sync server 容器...")
        result = subprocess.run(
            ["docker", "stop", CONTAINER_NAME],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(f"停止容器失败: {result.stderr}")
        logger.info("容器已停止")
        # 等待数据库释放锁
        time.sleep(2)

    def _start_container(self):
        """重启 sync server 容器。"""
        logger.info("正在启动 sync server 容器...")
        result = subprocess.run(
            ["docker", "start", CONTAINER_NAME],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(f"启动容器失败: {result.stderr}")
        # 等待服务就绪
        time.sleep(3)
        logger.info("容器已启动")

    def _copy_audio_to_media(self, audio_source_path: str) -> str:
        """
        将音频文件复制到 media 目录。
        返回 Anki 引用的文件名（不含 [sound:] 前缀）。
        """
        _mkdir_with_sudo(MEDIA_DIR)
        
        # 生成唯一文件名
        basename = os.path.basename(audio_source_path)
        name, ext = os.path.splitext(basename)
        if not ext:
            ext = ".mp3"
        
        # 检查是否已存在同名文件
        target_path = os.path.join(MEDIA_DIR, basename)
        
        # 用 sudo 检查文件是否存在
        result = subprocess.run(
            ["sudo", "test", "-f", target_path],
            capture_output=True
        )
        if result.returncode != 0:
            # 复制音频（用 sudo 写进去）
            _run(["sudo", "cp", audio_source_path, target_path])
            _run(["sudo", "chmod", "644", target_path])
            logger.info(f"音频已复制到: {target_path}")
        else:
            logger.info(f"音频已存在: {target_path}")
        
        return basename

    def _register_media_files(self, audio_paths: List[str], usn: int):
        """将音频文件注册到 media.db（用于同步时的媒体文件校验）。"""
        import sqlite3

        # 创建临时 media.db 的副本写入
        tmp = tempfile.mktemp(suffix=".media.db")
        try:
            _copy_with_sudo(MEDIA_DB, tmp)
            _chown_with_sudo(tmp)
            
            conn = sqlite3.connect(tmp)
            now = int(time.time())
            registered = 0
            
            for audio_path in audio_paths:
                basename = os.path.basename(audio_path)
                name, ext = os.path.splitext(basename)
                if not ext:
                    basename += ".mp3"
                
                # 检查是否已存在
                cur = conn.execute("SELECT fname FROM media WHERE fname = ?", (basename,))
                if cur.fetchone():
                    logger.info(f"media.db 已存在: {basename}")
                    continue
                
                # 计算文件大小和校验和
                media_path = os.path.join(MEDIA_DIR, basename)
                result = subprocess.run(
                    ["sudo", "stat", "--format=%s", media_path],
                    capture_output=True, text=True, timeout=10
                )
                file_size = int(result.stdout.strip()) if result.returncode == 0 else 0
                
                # 计算 SHA1 校验和（Anki 使用 SHA1）
                import hashlib
                sha1_result = subprocess.run(
                    ["sudo", "sha1sum", media_path],
                    capture_output=True, text=True, timeout=30
                )
                sha1_hex = sha1_result.stdout.split()[0] if sha1_result.returncode == 0 else "0" * 40
                sha1_bytes = bytes.fromhex(sha1_hex)
                
                conn.execute(
                    "INSERT OR IGNORE INTO media (fname, csum, size, usn, mtime) VALUES (?, ?, ?, ?, ?)",
                    (basename, sha1_bytes, file_size, usn, now)
                )
                registered += 1
                usn += 1

            # anki-cloud-sync expects media.db schema version 4 with a meta
            # summary row. Keep it fresh after direct media inserts.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    last_usn int NOT NULL,
                    total_bytes int NOT NULL,
                    total_nonempty_files int NOT NULL
                )
            """)
            conn.execute("DELETE FROM meta")
            conn.execute("""
                INSERT INTO meta (last_usn, total_bytes, total_nonempty_files)
                SELECT
                    COALESCE(MAX(usn), 0),
                    COALESCE(SUM(size), 0),
                    COALESCE(SUM(CASE WHEN size > 0 THEN 1 ELSE 0 END), 0)
                FROM media
            """)
            conn.execute("PRAGMA user_version = 4")
            
            conn.commit()
            conn.close()
            
            # 写回
            _copy_with_sudo(tmp, MEDIA_DB)
            _chmod_with_sudo(MEDIA_DB, "644")
            logger.info(f"media.db 已注册 {registered} 个文件")
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def push_cards(
        self,
        sentences: List[Dict[str, Any]],
        audio_dir: str,
        deck_name: str = "德语听力",
    ) -> Dict[str, Any]:
        """
        将卡片直接推送到 sync server 数据库。

        Args:
            sentences: [{audio_filename, german_text, chinese_text}, ...]
            audio_dir: 音频文件所在目录
            deck_name: 目标牌组名称

        Returns:
            {success, count, deck_name, message}
        """
        import sqlite3

        try:
            # 1. 暂停容器
            self._stop_container()

            # 2. 复制 collection DB（先做备份）
            timestamp = int(time.time())
            backup_path = f"{COLLECTION_DB}.backup_{timestamp}"
            _copy_with_sudo(COLLECTION_DB, backup_path)
            _chown_with_sudo(backup_path)
            logger.info(f"数据库已备份: {backup_path}")

            # 3. 复制数据库到可写临时位置
            temp_db = f"/tmp/anki_push_temp_{timestamp}.anki2"
            _copy_with_sudo(COLLECTION_DB, temp_db)
            _chown_with_sudo(temp_db)

            # 连接副本
            conn = sqlite3.connect(temp_db)
            
            # 注册 unicase collation（decks 表使用）
            def collate_unicase(a, b):
                la = (a or '').lower()
                lb = (b or '').lower()
                if la < lb: return -1
                if la > lb: return 1
                return 0
            conn.create_collation('unicase', collate_unicase)

            # 4. 获取/创建牌组
            deck_id = _get_deck_id(deck_name, conn)

            # 5. 获取当前 usn
            base_usn = _get_last_usn(conn) + 1
            next_due = _next_new_card_due(conn, deck_id)
            next_note_id = _next_row_id(conn, "notes")
            next_card_id = _next_row_id(conn, "cards")

            # 6. 逐个插入卡片
            now = int(time.time())
            cards_added = 0
            media_entries = []  # 收集需要注册到 media.db 的条目
            
            for i, item in enumerate(sentences):
                audio_path = os.path.join(audio_dir, item["audio_filename"])
                if not os.path.exists(audio_path):
                    logger.warning(f"音频文件不存在: {audio_path}")
                    continue

                german_text = item["german_text"]
                chinese_text = item.get("chinese_text", "")

                # 复制音频并获取文件名
                audio_filename = self._copy_audio_to_media(audio_path)
                # 记录 media 条目，后面统一注册到 media.db
                media_entries.append(audio_path)

                # 构建字段数据（Front=[sound], Back=德语 + 中文）
                # 用 \x1f 分隔
                front_field = f"[sound:{audio_filename}]"
                back_field = f"{german_text}\n\n{chinese_text}" if chinese_text else german_text
                flds = f"{front_field}\x1f{back_field}"

                # 生成 note/card，使用数据库当前最大 ID 递增，避免 UNIQUE 冲突
                note_id = next_note_id
                next_note_id += 1
                guid = _generate_guid()
                csum = _crc32_checksum(front_field)
                sfld = front_field.lower()
                usn_this = base_usn + i

                # 插入 note
                conn.execute(
                    """INSERT INTO notes 
                    (id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '')""",
                    (note_id, guid, BASIC_NOTE_TYPE_ID, now, usn_this, 
                     "deutsch-lernen", flds, sfld, csum)
                )

                # 生成 card（每个 note 一张 card）
                card_id = next_card_id
                next_card_id += 1
                conn.execute(
                    """INSERT INTO cards
                    (id, nid, did, ord, mod, usn, type, queue, due, ivl, factor, reps, lapses, left, odue, odid, flags, data)
                    VALUES (?, ?, ?, 0, ?, ?, 0, 0, ?, 0, 0, 0, 0, 0, 0, 0, 0, '{}')""",
                    (card_id, note_id, deck_id, now, usn_this, next_due)
                )
                next_due += 1
                
                cards_added += 1

            # 7. 提交并写回
            conn.commit()
            conn.close()

            # 将修改后的数据库写回
            _copy_with_sudo(temp_db, COLLECTION_DB)
            _chmod_with_sudo(COLLECTION_DB, "600")
            os.unlink(temp_db)

            # 8. 注册音频文件到 media.db
            media_usn = base_usn + cards_added
            self._register_media_files(media_entries, media_usn)

            logger.info(f"成功写入 {cards_added} 张卡片到数据库")

            # 8. 重启容器
            self._start_container()

            return {
                "success": True,
                "count": cards_added,
                "deck_name": deck_name,
                "message": f"成功推送 {cards_added} 张卡片到牌组「{deck_name}」",
            }

        except Exception as e:
            # 尝试重启容器
            try:
                self._start_container()
            except Exception:
                pass
            logger.error(f"推送失败: {e}")
            return {
                "success": False,
                "count": 0,
                "deck_name": deck_name,
                "message": f"推送失败: {str(e)}",
            }

    def get_current_collection_info(self) -> Dict[str, Any]:
        """获取当前数据库状态（不修改）。"""
        import sqlite3
        
        try:
            # 检查数据库是否存在
            check = subprocess.run(
                ["sudo", "test", "-f", COLLECTION_DB],
                capture_output=True
            )
            if check.returncode != 0:
                return {"error": "collection.db 不存在"}
            
            # 复制一份避免锁冲突，同时避免权限问题
            temp_copy = f"/tmp/collection_inspect_{int(time.time())}.anki2"
            _copy_with_sudo(COLLECTION_DB, temp_copy)
            _chown_with_sudo(temp_copy)
            
            conn = sqlite3.connect(temp_copy)
            def collate_unicase(a, b):
                la = (a or '').lower()
                lb = (b or '').lower()
                if la < lb: return -1
                if la > lb: return 1
                return 0
            conn.create_collation('unicase', collate_unicase)
            
            info = {}
            info["total_notes"] = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            info["total_cards"] = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
            info["decks"] = [
                {"id": r[0], "name": r[1]}
                for r in conn.execute("SELECT id, name FROM decks ORDER BY name")
            ]
            info["notetypes"] = [
                {"id": r[0], "name": r[1]}
                for r in conn.execute("SELECT id, name FROM notetypes ORDER BY name")
            ]
            
            conn.close()
            os.unlink(temp_copy)
            
            return info
        
        except Exception as e:
            return {"error": str(e)}


# ============================================================
# 简便函数（供 app.py 直接调用）
# ============================================================

def push_cards_to_server(
    sentences: List[Dict[str, Any]],
    audio_dir: str,
    deck_name: str = "德语听力",
) -> Dict[str, Any]:
    """简便函数：推送卡片到 sync server。"""
    pusher = AnkiSyncPusher()
    return pusher.push_cards(sentences, audio_dir, deck_name)


def get_server_info() -> Dict[str, Any]:
    """简便函数：获取服务器状态。"""
    pusher = AnkiSyncPusher()
    return pusher.get_current_collection_info()


# ============================================================
# 测试 / CLI 模式
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "info":
        info = get_server_info()
        print(json.dumps(info, ensure_ascii=False, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "--test":
        # 快速自检
        print("=== 测试 AnkiSyncPusher ===")
        info = get_server_info()
        print(f"数据库状态: {json.dumps(info, ensure_ascii=False, indent=2)}")
        
        if os.path.exists(MEDIA_DIR):
            media_count = len(os.listdir(MEDIA_DIR))
            print(f"媒体文件数: {media_count}")
        else:
            print("媒体目录不存在")
        
        print(f"数据库路径: {COLLECTION_DB}")
        print("测试完成")
    else:
        print(f"用法: {sys.argv[0]} [info|--test]")
        print("  info    - 查看当前数据库状态")
        print("  --test  - 运行自检")
