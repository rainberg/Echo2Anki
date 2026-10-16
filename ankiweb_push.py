import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_CACHE_DIR = Path(os.environ.get("ANKIWEB_CACHE_DIR", "/var/lib/ankiweb-push"))
DEFAULT_COLLECTION_PATH = DEFAULT_CACHE_DIR / "collection.anki2"
DEFAULT_DECK_NAME = os.environ.get("ANKIWEB_DECK_NAME", "Deutsch Listening")
DEFAULT_NOTE_TYPE = os.environ.get("ANKIWEB_NOTE_TYPE", "Basic")


class AnkiWebPushError(RuntimeError):
    pass


def _require_anki():
    try:
        from anki.collection import Collection
        from anki.notes import Note
        from anki.sync import SyncCollectionResponse, SyncStatus

        return Collection, Note, SyncCollectionResponse, SyncStatus
    except ModuleNotFoundError as exc:
        raise AnkiWebPushError(
            "The official 'anki' Python package is not installed. "
            "Install it in the runtime environment with: python -m pip install anki"
        ) from exc


def _credentials(username: Optional[str], password: Optional[str]) -> tuple[str, str]:
    username = username or os.environ.get("ANKIWEB_USERNAME", "")
    password = password or os.environ.get("ANKIWEB_PASSWORD", "")
    if not username or not password:
        raise AnkiWebPushError(
            "Missing AnkiWeb credentials. Set ANKIWEB_USERNAME and ANKIWEB_PASSWORD, "
            "or pass username/password explicitly."
        )
    return username, password


def _copy_audio_to_temp(src: Path) -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="ankiweb-media-"))
    dst = tmp_dir / src.name
    shutil.copy2(src, dst)
    return dst


class AnkiWebOfficialPusher:
    """
    Experimental pusher that uses Anki's official Python package.

    AnkiWeb does not expose a public add-note REST API. The safer path is to
    maintain a local Anki collection cache, modify it through Collection APIs,
    then let Anki's own sync implementation merge changes with AnkiWeb.
    """

    def __init__(
        self,
        collection_path: Path | str = DEFAULT_COLLECTION_PATH,
        endpoint: Optional[str] = None,
        note_type_name: str = DEFAULT_NOTE_TYPE,
    ) -> None:
        self.collection_path = Path(collection_path)
        self.endpoint = endpoint
        self.note_type_name = note_type_name

    def push_cards(
        self,
        sentences: List[Dict[str, Any]],
        audio_dir: str,
        deck_name: str = DEFAULT_DECK_NAME,
        username: Optional[str] = None,
        password: Optional[str] = None,
        allow_initial_download: bool = True,
    ) -> Dict[str, Any]:
        Collection, Note, SyncCollectionResponse, SyncStatus = _require_anki()
        username, password = _credentials(username, password)

        self.collection_path.parent.mkdir(parents=True, exist_ok=True)
        audio_base = Path(audio_dir)
        temp_media_dirs: list[Path] = []
        col = None

        try:
            col = Collection(str(self.collection_path))
            auth = col.sync_login(username=username, password=password, endpoint=self.endpoint)

            status = col.sync_status(auth)
            if status.required == SyncStatus.FULL_SYNC:
                if not allow_initial_download:
                    raise AnkiWebPushError("AnkiWeb requires a full sync before pushing.")
                col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
                col.close()
                col = Collection(str(self.collection_path))
                auth = col.sync_login(username=username, password=password, endpoint=self.endpoint)
            elif status.required == SyncStatus.NORMAL_SYNC:
                out = col.sync_collection(auth=auth, sync_media=True)
                if out.required in (
                    SyncCollectionResponse.FULL_SYNC,
                    SyncCollectionResponse.FULL_DOWNLOAD,
                ):
                    if not allow_initial_download:
                        raise AnkiWebPushError("AnkiWeb requires a full download before pushing.")
                    col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
                    col.close()
                    col = Collection(str(self.collection_path))
                    auth = col.sync_login(username=username, password=password, endpoint=self.endpoint)
                elif out.required == SyncCollectionResponse.FULL_UPLOAD:
                    raise AnkiWebPushError(
                        "AnkiWeb reports the remote collection is empty. Refusing full upload automatically."
                    )

            deck_id = col.decks.add_normal_deck_with_name(deck_name).id
            notetype = col.models.by_name(self.note_type_name)
            if not notetype:
                raise AnkiWebPushError(
                    f"Note type '{self.note_type_name}' was not found in the synced collection. "
                    "Create it once in Anki Desktop, or set ANKIWEB_NOTE_TYPE to an existing note type."
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
                keys = note.keys()
                if "Front" in keys and "Back" in keys:
                    note["Front"] = f"[sound:{media_filename}]"
                    back = item.get("german_text", "")
                    zh = (item.get("chinese_text") or "").strip()
                    note["Back"] = f"{back}\n\n{zh}" if zh else back
                elif {"Audio", "German", "Chinese"}.issubset(set(keys)):
                    note["Audio"] = f"[sound:{media_filename}]"
                    note["German"] = item.get("german_text", "")
                    note["Chinese"] = item.get("chinese_text", "")
                else:
                    raise AnkiWebPushError(
                        f"Unsupported note type fields for '{self.note_type_name}': {keys}. "
                        "Use Basic (Front/Back) or a type with Audio/German/Chinese fields."
                    )

                for tag in item.get("tags", ["deutsch-lernen", "web-push"]):
                    note.add_tag(tag)

                check = note.fields_check()
                if str(check).lower().find("duplicate") >= 0:
                    skipped += 1
                    continue

                col.add_note(note, deck_id)
                added += 1

            sync_out = col.sync_collection(auth=auth, sync_media=True)
            col.sync_media(auth)

            return {
                "success": True,
                "count": added,
                "skipped": skipped,
                "deck_name": deck_name,
                "sync_required": int(sync_out.required),
                "message": f"Added {added} cards to AnkiWeb via local collection sync.",
            }
        except Exception as exc:
            return {
                "success": False,
                "count": 0,
                "deck_name": deck_name,
                "message": f"AnkiWeb push failed: {exc}",
            }
        finally:
            if col is not None:
                try:
                    col.close()
                except Exception:
                    pass
            for temp_dir in temp_media_dirs:
                shutil.rmtree(temp_dir, ignore_errors=True)


def push_cards_to_ankiweb(
    sentences: List[Dict[str, Any]],
    audio_dir: str,
    deck_name: str = DEFAULT_DECK_NAME,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    return AnkiWebOfficialPusher().push_cards(
        sentences=sentences,
        audio_dir=audio_dir,
        deck_name=deck_name,
        username=username,
        password=password,
    )
