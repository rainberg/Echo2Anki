import base64
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
import zlib
import hashlib
from pathlib import Path
from typing import Any, Dict, List


DATA_DIR = Path("/var/lib/docker/volumes/anki-cloud_app-data/_data/anki_user")
COLLECTION_DB = DATA_DIR / "collection.anki2"
MEDIA_DIR = DATA_DIR / "media"
MEDIA_DB = DATA_DIR / "media.db"
CONTAINER_NAME = "anki-sync-standalone"
BASIC_NOTE_TYPE_ID = 1623434819882


def _sudo_prefix() -> List[str]:
    return [] if os.geteuid() == 0 else ["sudo"]


def _run(cmd: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(_sudo_prefix() + cmd, capture_output=True, text=True, timeout=timeout)


def _check(cmd: List[str], timeout: int = 60) -> None:
    cp = _run(cmd, timeout=timeout)
    if cp.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{cp.stderr}")


def _path_exists(path: Path) -> bool:
    cp = _run(["test", "-e", str(path)], timeout=20)
    return cp.returncode == 0


def _copy(src: Path, dst: Path) -> None:
    _check(["cp", "-a", str(src), str(dst)])


def _chmod(path: Path, mode: str) -> None:
    _check(["chmod", mode, str(path)])


def _ensure_dir(path: Path) -> None:
    _check(["mkdir", "-p", str(path)])


def _chown_current_user(path: Path) -> None:
    uid = os.getuid()
    gid = os.getgid()
    _check(["chown", f"{uid}:{gid}", str(path)])


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except PermissionError:
        _check(["rm", "-f", str(path)])


def _stop_container() -> None:
    _check(["docker", "stop", CONTAINER_NAME], timeout=90)
    time.sleep(1)


def _start_container() -> None:
    _check(["docker", "start", CONTAINER_NAME], timeout=90)
    time.sleep(2)


def _sqlite_quick_check(path: Path) -> None:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    try:
        conn.create_collation("unicase", _collate_unicase)
        result = conn.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        conn.close()
    if result != "ok":
        raise RuntimeError(f"{path.name} quick_check failed: {result}")


def _assert_databases_available_for_push() -> None:
    busy_paths = []
    for path in (COLLECTION_DB, MEDIA_DB):
        cp = _run(["fuser", str(path)], timeout=10)
        if cp.returncode == 0:
            pids = " ".join((cp.stdout or "").split())
            busy_paths.append(f"{path.name} ({pids or 'in use'})")

    if busy_paths:
        raise RuntimeError(
            "Anki sync is still using the database. Please wait for AnkiDroid/Anki media sync "
            f"to finish, then retry. Busy: {', '.join(busy_paths)}"
        )

    for path in (COLLECTION_DB, MEDIA_DB):
        try:
            _sqlite_quick_check(path)
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                raise RuntimeError(
                    "Anki database is locked by an active sync. Please wait for sync/media sync to finish, then retry."
                ) from exc
            raise


def _guid() -> str:
    return base64.b64encode(os.urandom(8), altchars=b"-_").decode("ascii").rstrip("=")


def _crc32_checksum(text: str) -> int:
    return zlib.crc32(text.strip().lower().encode("utf-8")) & 0xFFFFFFFF


def _collate_unicase(a, b):
    la = (a or "").lower()
    lb = (b or "").lower()
    if la < lb:
        return -1
    if la > lb:
        return 1
    return 0


def _next_row_id(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COALESCE(MAX(id),0)+1 FROM {table}").fetchone()
    return int(row[0])


def _max_usn(conn: sqlite3.Connection) -> int:
    n = conn.execute("SELECT COALESCE(MAX(usn),0) FROM notes").fetchone()[0]
    c = conn.execute("SELECT COALESCE(MAX(usn),0) FROM cards").fetchone()[0]
    d = conn.execute("SELECT COALESCE(MAX(usn),0) FROM decks").fetchone()[0]
    col = conn.execute("SELECT COALESCE(MAX(usn),0) FROM col").fetchone()[0]
    return int(max(n or 0, c or 0, d or 0, col or 0))


def _refresh_col_metadata(conn: sqlite3.Connection) -> None:
    now_ms = int(time.time() * 1000)
    conn.execute("UPDATE col SET mod=?, usn=?, ls=?", (now_ms, _max_usn(conn), now_ms - 1))


def _get_or_create_deck_id(deck_name: str, conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM decks WHERE name = ?", (deck_name,)).fetchone()
    if row:
        return int(row[0])

    default = conn.execute("SELECT common, kind FROM decks WHERE id=1").fetchone()
    if default:
        common_blob, kind_blob = default
    else:
        common_blob = sqlite3.Binary(b"\x08\x01\x10\x01\x18\xa6\x0a")
        kind_blob = sqlite3.Binary(b"\x0a\x02\x08\x01")

    deck_id = int(time.time() * 1000)
    deck_usn = _max_usn(conn) + 1
    conn.execute(
        "INSERT INTO decks (id, name, mtime_secs, usn, common, kind) VALUES (?, ?, ?, ?, ?, ?)",
        (deck_id, deck_name, int(time.time()), deck_usn, common_blob, kind_blob),
    )
    return deck_id


def _short_file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def _copy_audio_to_media(src_audio: Path) -> str:
    _ensure_dir(MEDIA_DIR)
    suffix = src_audio.suffix or ".mp3"
    stem = src_audio.stem if src_audio.suffix else src_audio.name
    digest = _short_file_hash(src_audio)
    filename = f"{stem}_{digest}{suffix}"
    target = MEDIA_DIR / filename
    if not _path_exists(target):
        _copy(src_audio, target)
        _chmod(target, "644")
    return filename


def _register_media(entries: List[Path], usn_start: int) -> None:
    tmp_media = Path(tempfile.mktemp(suffix=".media.db"))
    try:
        _copy(MEDIA_DB, tmp_media)
        _chown_current_user(tmp_media)
        conn = sqlite3.connect(str(tmp_media))
        cur = conn.cursor()
        current_media_usn = cur.execute("SELECT COALESCE(MAX(usn),0) FROM media").fetchone()[0]
        usn = max(int(current_media_usn or 0), usn_start - 1) + 1
        now = int(time.time())

        for src in entries:
            fname = src.name if src.suffix else f"{src.name}.mp3"
            fpath = MEDIA_DIR / fname
            if not _path_exists(fpath):
                continue
            exists = cur.execute("SELECT 1 FROM media WHERE fname = ?", (fname,)).fetchone()
            if exists:
                continue

            stat = _run(["stat", "--format=%s", str(fpath)], timeout=20)
            size = int(stat.stdout.strip()) if stat.returncode == 0 and stat.stdout.strip() else 0
            sha1 = _run(["sha1sum", str(fpath)], timeout=20)
            sha1_hex = sha1.stdout.split()[0] if sha1.returncode == 0 and sha1.stdout.strip() else "0" * 40
            sha1_bytes = bytes.fromhex(sha1_hex)

            cur.execute(
                "INSERT OR IGNORE INTO media (fname, csum, size, usn, mtime) VALUES (?, ?, ?, ?, ?)",
                (fname, sha1_bytes, size, usn, now),
            )
            usn += 1

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                last_usn int NOT NULL,
                total_bytes int NOT NULL,
                total_nonempty_files int NOT NULL
            )
            """
        )
        cur.execute("DELETE FROM meta")
        cur.execute(
            """
            INSERT INTO meta (last_usn, total_bytes, total_nonempty_files)
            SELECT
                COALESCE(MAX(usn), 0),
                COALESCE(SUM(size), 0),
                COALESCE(SUM(CASE WHEN size > 0 THEN 1 ELSE 0 END), 0)
            FROM media
            """
        )
        cur.execute("PRAGMA user_version = 4")
        conn.commit()
        conn.close()

        _copy(tmp_media, MEDIA_DB)
        _chmod(MEDIA_DB, "644")
    finally:
        _safe_unlink(tmp_media)


class AnkiSyncPusherSafe:
    def push_cards(self, sentences: List[Dict[str, Any]], audio_dir: str, deck_name: str = "德语听力") -> Dict[str, Any]:
        timestamp = int(time.time())
        backup_path = COLLECTION_DB.with_name(f"{COLLECTION_DB.name}.backup_{timestamp}")
        temp_db = Path(tempfile.mktemp(suffix=".anki2"))
        cards_added = 0
        duplicates_skipped = 0
        media_entries: List[Path] = []
        container_stopped = False

        try:
            _assert_databases_available_for_push()
            _stop_container()
            container_stopped = True
            _copy(COLLECTION_DB, backup_path)
            _copy(COLLECTION_DB, temp_db)
            _chown_current_user(temp_db)

            conn = sqlite3.connect(str(temp_db))
            conn.create_collation("unicase", _collate_unicase)
            deck_id = _get_or_create_deck_id(deck_name, conn)
            base_usn = _max_usn(conn) + 1
            next_due = conn.execute(
                "SELECT COALESCE(MAX(due),0)+1 FROM cards WHERE did=? AND queue=0 AND type=0",
                (deck_id,),
            ).fetchone()[0]
            next_note_id = _next_row_id(conn, "notes")
            next_card_id = _next_row_id(conn, "cards")
            now = int(time.time())

            for i, item in enumerate(sentences):
                # 优先使用句子自带的 audio_dir（支持跨任务收藏集）
                item_audio_dir = item.get("audio_dir") or audio_dir
                src = Path(item_audio_dir) / item["audio_filename"]
                if not src.exists():
                    continue

                audio_filename = _copy_audio_to_media(src)
                media_entries.append(Path(audio_filename))
                front = f"[sound:{audio_filename}]"
                if conn.execute("SELECT 1 FROM notes WHERE sfld = ?", (front.lower(),)).fetchone():
                    duplicates_skipped += 1
                    continue
                back = item.get("german_text", "")
                zh = (item.get("chinese_text") or "").strip()
                if zh:
                    back = f"{back}\n\n{zh}"
                flds = f"{front}\x1f{back}"
                usn = base_usn + i

                conn.execute(
                    """
                    INSERT INTO notes
                    (id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '')
                    """,
                    (next_note_id, _guid(), BASIC_NOTE_TYPE_ID, now, usn, "deutsch-lernen", flds, front.lower(), _crc32_checksum(front)),
                )
                conn.execute(
                    """
                    INSERT INTO cards
                    (id, nid, did, ord, mod, usn, type, queue, due, ivl, factor, reps, lapses, left, odue, odid, flags, data)
                    VALUES (?, ?, ?, 0, ?, ?, 0, 0, ?, 0, 0, 0, 0, 0, 0, 0, 0, '{}')
                    """,
                    (next_card_id, next_note_id, deck_id, now, usn, next_due),
                )
                next_note_id += 1
                next_card_id += 1
                next_due += 1
                cards_added += 1

            _refresh_col_metadata(conn)
            media_usn_start = _max_usn(conn) + 1
            conn.commit()
            conn.close()

            _copy(temp_db, COLLECTION_DB)
            _chmod(COLLECTION_DB, "600")

            if cards_added:
                _register_media(media_entries, media_usn_start)

            _start_container()
            return {"success": True, "count": cards_added, "deck_name": deck_name, "message": f"成功推送 {cards_added} 张卡片到牌组「{deck_name}」"}
        except Exception as e:
            if container_stopped:
                try:
                    _start_container()
                except Exception:
                    pass
            return {"success": False, "count": 0, "deck_name": deck_name, "message": f"推送失败: {e}"}
        finally:
            _safe_unlink(temp_db)

    def get_current_collection_info(self) -> Dict[str, Any]:
        tmp = Path(tempfile.mktemp(suffix=".anki2"))
        try:
            _copy(COLLECTION_DB, tmp)
            _chown_current_user(tmp)
            conn = sqlite3.connect(str(tmp))
            conn.create_collation("unicase", _collate_unicase)
            info = {
                "total_notes": conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0],
                "total_cards": conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0],
                "decks": [{"id": r[0], "name": r[1]} for r in conn.execute("SELECT id,name FROM decks ORDER BY name")],
                "notetypes": [{"id": r[0], "name": r[1]} for r in conn.execute("SELECT id,name FROM notetypes ORDER BY name")],
            }
            conn.close()
            return info
        except Exception as e:
            return {"error": str(e)}
        finally:
            _safe_unlink(tmp)


def push_cards_to_server(sentences: List[Dict[str, Any]], audio_dir: str, deck_name: str = "德语听力") -> Dict[str, Any]:
    return AnkiSyncPusherSafe().push_cards(sentences, audio_dir, deck_name)


def get_server_info() -> Dict[str, Any]:
    return AnkiSyncPusherSafe().get_current_collection_info()
