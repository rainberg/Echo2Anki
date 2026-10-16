import csv
import hashlib
import re
import shutil
import sqlite3
import subprocess
import time
import zlib
from pathlib import Path


CONTAINER_NAME = "anki-sync-standalone"
DATA_DIR = Path("/var/lib/docker/volumes/anki-cloud_app-data/_data/anki_user")
COLLECTION_DB = DATA_DIR / "collection.anki2"
MEDIA_DB = DATA_DIR / "media.db"
MEDIA_DIR = DATA_DIR / "collection.media"
EXPORT_DIR = Path("/opt/anki-app/exports/today_export_20260427_Europe_Berlin")
CSV_PATH = EXPORT_DIR / "notes_today.csv"
EXPORT_MEDIA_DIR = EXPORT_DIR / "media"
DECK_NAME = "德语听力"
NOTE_TYPE_ID = 1623434819882
SOUND_RE = re.compile(r"\[sound:([^\]]+)\]")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def split_text_fields(german_col: str, chinese_col: str) -> tuple[str, str]:
    german_col = (german_col or "").strip()
    chinese_col = (chinese_col or "").strip()
    if chinese_col:
        return german_col, chinese_col
    if "\n\n" in german_col:
        de, zh = german_col.split("\n\n", 1)
        return de.strip(), zh.strip()
    return german_col, ""


def load_latest_35() -> list[dict]:
    rows = []
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            m = SOUND_RE.search((r.get("audio_field") or "").strip())
            if not m:
                continue
            audio_filename = m.group(1)
            de, zh = split_text_fields(r.get("german", ""), r.get("chinese", ""))
            rows.append(
                {
                    "note_id": int(r["note_id"]),
                    "audio_filename": audio_filename,
                    "german_text": de,
                    "chinese_text": zh,
                }
            )

    latest_by_audio: dict[str, dict] = {}
    for r in rows:
        old = latest_by_audio.get(r["audio_filename"])
        if old is None or r["note_id"] > old["note_id"]:
            latest_by_audio[r["audio_filename"]] = r
    out = list(latest_by_audio.values())
    out.sort(key=lambda x: x["note_id"])
    return out


def collate_unicase(a, b):
    la = (a or "").lower()
    lb = (b or "").lower()
    if la < lb:
        return -1
    if la > lb:
        return 1
    return 0


def get_or_create_deck_id(conn: sqlite3.Connection, deck_name: str) -> int:
    row = conn.execute("SELECT id FROM decks WHERE name = ?", (deck_name,)).fetchone()
    if row:
        return int(row[0])
    deck_id = int(time.time() * 1000)
    conn.execute(
        "INSERT INTO decks (id, name, mtime_secs, usn, common, kind) VALUES (?, ?, ?, ?, ?, ?)",
        (deck_id, deck_name, int(time.time()), -1, "", ""),
    )
    return deck_id


def crc32_checksum(text: str) -> int:
    return zlib.crc32(text.strip().lower().encode("utf-8")) & 0xFFFFFFFF


def register_media(imported_audio: list[str], usn_start: int) -> None:
    conn = sqlite3.connect(str(MEDIA_DB))
    cur = conn.cursor()
    now = int(time.time())
    usn = usn_start
    for fname in imported_audio:
        path = MEDIA_DIR / fname
        if not path.exists():
            continue
        csum = hashlib.sha1(path.read_bytes()).digest()
        size = path.stat().st_size
        cur.execute(
            "INSERT OR IGNORE INTO media (fname, csum, size, usn, mtime) VALUES (?, ?, ?, ?, ?)",
            (fname, csum, size, usn, now),
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


def main() -> None:
    rows = load_latest_35()
    print(f"latest_candidates={len(rows)}")
    if not rows:
        return

    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(f"/opt/anki-app/backups/reimport_35_{ts}")
    backup_dir.mkdir(parents=True, exist_ok=True)

    run(["sudo", "docker", "stop", CONTAINER_NAME])
    try:
        run(["sudo", "cp", "-a", str(COLLECTION_DB), str(backup_dir / "collection.anki2.pre_import")])
        run(["sudo", "cp", "-a", str(MEDIA_DB), str(backup_dir / "media.db.pre_import")])

        conn = sqlite3.connect(str(COLLECTION_DB))
        conn.create_collation("unicase", collate_unicase)
        cur = conn.cursor()

        deck_id = get_or_create_deck_id(conn, DECK_NAME)
        base_usn = max(
            cur.execute("SELECT COALESCE(MAX(usn),0) FROM notes").fetchone()[0],
            cur.execute("SELECT COALESCE(MAX(usn),0) FROM cards").fetchone()[0],
        ) + 1
        next_due = cur.execute(
            "SELECT COALESCE(MAX(due),0)+1 FROM cards WHERE did=? AND queue=0 AND type=0",
            (deck_id,),
        ).fetchone()[0]
        next_note_id = cur.execute("SELECT COALESCE(MAX(id),0)+1 FROM notes").fetchone()[0]
        next_card_id = cur.execute("SELECT COALESCE(MAX(id),0)+1 FROM cards").fetchone()[0]

        existing_audio = set()
        for (flds,) in cur.execute("SELECT flds FROM notes WHERE flds LIKE '%[sound:%'"):
            if not flds:
                continue
            for m in SOUND_RE.finditer(flds):
                existing_audio.add(m.group(1))

        inserted = 0
        skipped_existing = 0
        missing_audio = 0
        imported_audio: list[str] = []
        now = int(time.time())

        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        for i, r in enumerate(rows):
            fname = r["audio_filename"]
            if fname in existing_audio:
                skipped_existing += 1
                continue
            src = EXPORT_MEDIA_DIR / fname
            dst = MEDIA_DIR / fname
            if not src.exists():
                missing_audio += 1
                continue
            if not dst.exists():
                shutil.copy2(src, dst)
                dst.chmod(0o644)
            imported_audio.append(fname)

            front = f"[sound:{fname}]"
            back = r["german_text"]
            if r["chinese_text"]:
                back = f"{back}\n\n{r['chinese_text']}"
            flds = f"{front}\x1f{back}"
            usn = base_usn + i

            cur.execute(
                """
                INSERT INTO notes (id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, data)
                VALUES (?, hex(randomblob(8)), ?, ?, ?, ?, ?, ?, ?, 0, '')
                """,
                (next_note_id, NOTE_TYPE_ID, now, usn, "deutsch-lernen", flds, front.lower(), crc32_checksum(front)),
            )
            cur.execute(
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
            inserted += 1

        conn.commit()
        ic = cur.execute("PRAGMA integrity_check;").fetchone()[0]
        conn.close()

        if imported_audio:
            register_media(imported_audio, base_usn + inserted + 1)

        print(f"inserted={inserted}")
        print(f"skipped_existing={skipped_existing}")
        print(f"missing_audio={missing_audio}")
        print(f"integrity_check={ic}")
        print(f"backup_dir={backup_dir}")
    finally:
        run(["sudo", "docker", "start", CONTAINER_NAME])


if __name__ == "__main__":
    main()
