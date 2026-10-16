import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_CACHE_DIR = Path(os.environ.get("ANKI_SYNC_CLIENT_CACHE_DIR", "/var/lib/anki-sync-client-push"))
DEFAULT_COLLECTION_PATH = DEFAULT_CACHE_DIR / "collection.anki2"
DEFAULT_ENDPOINT = os.environ.get("ANKI_SYNC_ENDPOINT", "http://127.0.0.1:8080")
DEFAULT_USERNAME = os.environ.get("ANKI_SYNC_USERNAME", "")
DEFAULT_PASSWORD = os.environ.get("ANKI_SYNC_PASSWORD", "")
DEFAULT_DECK_NAME = os.environ.get("ANKI_SYNC_DECK_NAME", "Deutsch Listening")
DEFAULT_NOTE_TYPE = os.environ.get("ANKI_SYNC_NOTE_TYPE", "Basic")
DEFAULT_MEDIA_SYNC_TIMEOUT_SECS = int(os.environ.get("ANKI_SYNC_MEDIA_TIMEOUT_SECS", "300"))


class AnkiSyncClientPushError(RuntimeError):
    pass


class SimpleFileLock:
    def __init__(self, path: Path, timeout: int = 120) -> None:
        self.path = path
        self.timeout = timeout
        self.fd: Optional[int] = None

    def __enter__(self) -> "SimpleFileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + self.timeout
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode("ascii"))
                return self
            except FileExistsError:
                if time.time() >= deadline:
                    raise AnkiSyncClientPushError(f"Timed out waiting for sync client lock: {self.path}")
                time.sleep(1)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _require_anki():
    try:
        from anki.collection import Collection
        from anki.notes import Note
        from anki.sync import SyncStatus

        return Collection, Note, SyncStatus
    except ModuleNotFoundError as exc:
        raise AnkiSyncClientPushError(
            "The official 'anki' Python package is not installed in this runtime."
        ) from exc


def _credentials(username: Optional[str], password: Optional[str]) -> tuple[str, str]:
    username = username or DEFAULT_USERNAME
    password = password or DEFAULT_PASSWORD
    if not username or not password:
        raise AnkiSyncClientPushError(
            "Missing sync credentials. Set ANKI_SYNC_USERNAME and ANKI_SYNC_PASSWORD, "
            "or pass username/password explicitly."
        )
    return username, password


def _copy_audio_to_temp(src: Path) -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="anki-sync-client-media-"))
    dst = tmp_dir / src.name
    shutil.copy2(src, dst)
    return dst


def _wait_for_media_sync(col, timeout_secs: int = DEFAULT_MEDIA_SYNC_TIMEOUT_SECS) -> None:
    deadline = time.time() + timeout_secs
    while True:
        status = col.media_sync_status()
        if not status.active:
            return
        if time.time() >= deadline:
            raise AnkiSyncClientPushError(
                f"Timed out waiting for media sync to finish after {timeout_secs} seconds."
            )
        time.sleep(1)


class AnkiSyncClientPusher:
    """
    Push cards through the Anki sync protocol with an isolated local collection cache.

    This avoids direct writes to the server-side collection. The cache acts like
    another Anki client: sync down, modify through official Collection APIs, sync up.
    """

    def __init__(
        self,
        collection_path: Path | str = DEFAULT_COLLECTION_PATH,
        endpoint: str = DEFAULT_ENDPOINT,
        note_type_name: str = DEFAULT_NOTE_TYPE,
        lock_timeout: int = 120,
    ) -> None:
        self.collection_path = Path(collection_path)
        self.endpoint = endpoint
        self.note_type_name = note_type_name
        self.lock_path = self.collection_path.with_suffix(".lock")
        self.lock_timeout = lock_timeout

    def sync_only(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        sync_media: bool = False,
    ) -> Dict[str, Any]:
        return self._with_collection_sync(
            username=username,
            password=password,
            sync_media=sync_media,
            mutate=None,
        )

    def push_cards(
        self,
        sentences: List[Dict[str, Any]],
        audio_dir: str,
        deck_name: str = DEFAULT_DECK_NAME,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Dict[str, Any]:
        audio_base = Path(audio_dir)
        temp_media_dirs: list[Path] = []

        def mutate(col, Note) -> Dict[str, int]:
            deck_id = col.decks.add_normal_deck_with_name(deck_name).id
            notetype = col.models.by_name(self.note_type_name)
            if not notetype:
                raise AnkiSyncClientPushError(
                    f"Note type '{self.note_type_name}' was not found in the synced collection."
                )

            added = 0
            skipped = 0
            for item in sentences:
                # 优先使用句子自带的 audio_dir（支持跨任务收藏集）
                item_audio_base = Path(item["audio_dir"]) if item.get("audio_dir") else audio_base
                src = item_audio_base / item["audio_filename"]
                if not src.exists():
                    skipped += 1
                    continue

                temp_audio = _copy_audio_to_temp(src)
                temp_media_dirs.append(temp_audio.parent)
                media_filename = col.media.add_file(str(temp_audio))

                note = Note(col, notetype)
                keys = set(note.keys())
                if {"Front", "Back"}.issubset(keys):
                    note["Front"] = f"[sound:{media_filename}]"
                    back = item.get("german_text", "")
                    zh = (item.get("chinese_text") or "").strip()
                    note["Back"] = f"{back}\n\n{zh}" if zh else back
                elif {"Audio", "German", "Chinese"}.issubset(keys):
                    note["Audio"] = f"[sound:{media_filename}]"
                    note["German"] = item.get("german_text", "")
                    note["Chinese"] = item.get("chinese_text", "")
                else:
                    raise AnkiSyncClientPushError(
                        f"Unsupported note fields for '{self.note_type_name}': {sorted(keys)}"
                    )

                for tag in item.get("tags", ["deutsch-lernen", "sync-client-push"]):
                    note.add_tag(tag)

                check = note.fields_check()
                if "duplicate" in str(check).lower():
                    skipped += 1
                    continue

                col.add_note(note, deck_id)
                added += 1

            return {"added": added, "skipped": skipped}

        try:
            result = self._with_collection_sync(
                username=username,
                password=password,
                sync_media=True,
                mutate=mutate,
            )
            added = result.get("mutate", {}).get("added", 0)
            skipped = result.get("mutate", {}).get("skipped", 0)
            return {
                "success": True,
                "count": added,
                "skipped": skipped,
                "deck_name": deck_name,
                "message": f"Added {added} cards through Anki sync client cache.",
                **result,
            }
        except Exception as exc:
            return {
                "success": False,
                "count": 0,
                "deck_name": deck_name,
                "message": f"Sync-client push failed: {exc}",
            }
        finally:
            for temp_dir in temp_media_dirs:
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _with_collection_sync(
        self,
        username: Optional[str],
        password: Optional[str],
        sync_media: bool,
        mutate,
    ) -> Dict[str, Any]:
        Collection, Note, SyncStatus = _require_anki()
        username, password = _credentials(username, password)
        self.collection_path.parent.mkdir(parents=True, exist_ok=True)

        with SimpleFileLock(self.lock_path, self.lock_timeout):
            col = None
            try:
                col = Collection(str(self.collection_path))
                auth = col.sync_login(username=username, password=password, endpoint=self.endpoint)
                status = col.sync_status(auth)
                initial_required = int(status.required)

                if status.required == SyncStatus.FULL_SYNC:
                    col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
                    col.close()
                    col = Collection(str(self.collection_path))
                    auth = col.sync_login(username=username, password=password, endpoint=self.endpoint)
                elif status.required == SyncStatus.NORMAL_SYNC:
                    out = col.sync_collection(auth=auth, sync_media=False)
                    if int(out.required) != 0:
                        if out.required == SyncStatus.FULL_SYNC:
                            col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
                            col.close()
                            col = Collection(str(self.collection_path))
                            auth = col.sync_login(username=username, password=password, endpoint=self.endpoint)
                        else:
                            raise AnkiSyncClientPushError(f"Unexpected sync requirement before push: {out.required}")

                mutate_result = {}
                if mutate is not None:
                    mutate_result = mutate(col, Note)
                    out = col.sync_collection(auth=auth, sync_media=False)
                    if int(out.required) != 0:
                        raise AnkiSyncClientPushError(f"Unexpected sync requirement after push: {out.required}")

                if sync_media:
                    col.sync_media(auth)
                    _wait_for_media_sync(col)

                return {
                    "initial_required": initial_required,
                    "notes": col.db.scalar("select count(*) from notes"),
                    "cards": col.db.scalar("select count(*) from cards"),
                    "revlog": col.db.scalar("select count(*) from revlog"),
                    "mutate": mutate_result,
                }
            finally:
                if col is not None:
                    col.close()


def sync_client_only(
    username: Optional[str] = None,
    password: Optional[str] = None,
    sync_media: bool = False,
) -> Dict[str, Any]:
    return AnkiSyncClientPusher().sync_only(username=username, password=password, sync_media=sync_media)


def push_cards_to_server_via_sync(
    sentences: List[Dict[str, Any]],
    audio_dir: str,
    deck_name: str = DEFAULT_DECK_NAME,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    return AnkiSyncClientPusher().push_cards(
        sentences=sentences,
        audio_dir=audio_dir,
        deck_name=deck_name,
        username=username,
        password=password,
    )
