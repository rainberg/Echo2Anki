import csv
import re
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from anki_sync_push import push_cards_to_server


EXPORT_DIR = Path("/opt/anki-app/exports/today_export_20260427_Europe_Berlin")
CSV_PATH = EXPORT_DIR / "notes_today.csv"
AUDIO_DIR = EXPORT_DIR / "media"
COLLECTION_DB = Path("/var/lib/docker/volumes/anki-cloud_app-data/_data/anki_user/collection.anki2")
DECK_NAME = "德语听力"
SOUND_RE = re.compile(r"\[sound:([^\]]+)\]")


def split_text_fields(german_col: str, chinese_col: str) -> tuple[str, str]:
    german_col = (german_col or "").strip()
    chinese_col = (chinese_col or "").strip()
    if chinese_col:
        return german_col, chinese_col
    if "\n\n" in german_col:
        de, zh = german_col.split("\n\n", 1)
        return de.strip(), zh.strip()
    return german_col, ""


def pick_latest_35() -> list[dict]:
    rows = []
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            m = SOUND_RE.search((r.get("audio_field") or "").strip())
            if not m:
                continue
            audio_filename = m.group(1)
            note_id = int(r["note_id"])
            de, zh = split_text_fields(r.get("german", ""), r.get("chinese", ""))
            rows.append(
                {
                    "note_id": note_id,
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


def existing_audio_refs() -> set[str]:
    tmp_copy = tempfile.mktemp(suffix=".anki2")
    try:
        subprocess.run(["sudo", "cp", str(COLLECTION_DB), tmp_copy], check=True)
        subprocess.run(["sudo", "chown", "ubuntu:ubuntu", tmp_copy], check=True)
        conn = sqlite3.connect(tmp_copy)
        cur = conn.cursor()
        out = set()
        for (flds,) in cur.execute("SELECT flds FROM notes WHERE flds LIKE '%[sound:%'"):
            if not flds:
                continue
            for m in SOUND_RE.finditer(flds):
                out.add(m.group(1))
        conn.close()
        return out
    finally:
        try:
            Path(tmp_copy).unlink(missing_ok=True)
        except Exception:
            pass


def main() -> None:
    latest = pick_latest_35()
    if not latest:
        print("no candidates from export csv")
        return

    exists = existing_audio_refs()
    to_push = [r for r in latest if r["audio_filename"] not in exists]
    skipped = [r for r in latest if r["audio_filename"] in exists]

    print(f"latest_candidates={len(latest)}")
    print(f"already_on_server={len(skipped)}")
    print(f"to_push={len(to_push)}")
    if skipped:
        print("skipped_audio=" + ",".join(x["audio_filename"] for x in skipped))

    if not to_push:
        print("nothing to push")
        return

    payload = [
        {
            "audio_filename": r["audio_filename"],
            "german_text": r["german_text"],
            "chinese_text": r["chinese_text"],
        }
        for r in to_push
    ]
    result = push_cards_to_server(payload, str(AUDIO_DIR), DECK_NAME)
    print("push_result=", result)


if __name__ == "__main__":
    main()
