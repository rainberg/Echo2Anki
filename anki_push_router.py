import os
from typing import Any, Dict, List

from anki_sync_push_safe import push_cards_to_server as push_cards_direct


def push_cards_to_server(sentences: List[Dict[str, Any]], audio_dir: str, deck_name: str) -> Dict[str, Any]:
    mode = os.environ.get("ANKI_PUSH_MODE", "direct").strip().lower()
    if mode in {"sync", "sync_client", "client"}:
        from anki_sync_client_push import push_cards_to_server_via_sync

        username = os.environ.get("ANKI_SYNC_USERNAME")
        password = os.environ.get("ANKI_SYNC_PASSWORD")
        result = push_cards_to_server_via_sync(
            sentences=sentences,
            audio_dir=audio_dir,
            deck_name=deck_name,
            username=username,
            password=password,
        )
        result["push_mode"] = "sync_client"
        return result

    result = push_cards_direct(sentences, audio_dir, deck_name)
    result["push_mode"] = "direct"
    return result
