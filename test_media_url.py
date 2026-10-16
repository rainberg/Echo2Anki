#!/usr/bin/env python3
import sys, json, os
from pathlib import Path

sys.path.insert(0, "/opt/anki-app")
from task_worker import read_manifest, _task_source

V2_TASK_ROOT = "/var/lib/anki-v2/tasks"
SUBTITLE_TASK_ROOT = "/var/lib/anki-streamlit-subtitle/tasks"
V2_MEDIA_URL_PREFIX = "/v2-media"
SUBTITLE_MEDIA_URL_PREFIX = "/subtitle-media"

def media_url_for_path(path, task_id, source="v2"):
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
    except Exception as exc:
        print(f"  ERROR resolving: {exc}")
        print(f"  resolved={Path(path).resolve()}")
        print(f"  task_root={task_root}")
        return ""
    parts = [task_id] + [p for p in rel.parts if p not in ("", ".")]
    url = f"{prefix}/" + "/".join(parts)
    return url

# Test with subtitle beta tasks
sub_root = Path(SUBTITLE_TASK_ROOT)
if sub_root.exists():
    for mp in sorted(sub_root.glob("*/manifest.json"))[:3]:
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
            tid = data.get("task_id", "")
            name = data.get("upload_name", "")
            norm_path = data.get("normalized_audio_path", "")
            segs = data.get("segments", [])
            if not segs:
                continue
            print(f"\n=== Subtitle task: {tid} ({name}) ===")
            print(f"  normalized_audio_path: {norm_path}")
            print(f"  file exists: {os.path.exists(norm_path)}")
            url = media_url_for_path(norm_path, tid, "subtitle")
            print(f"  media URL: {url}")
        except Exception as exc:
            print(f"  Error: {exc}")

# Test with v2 tasks
v2_root = Path(V2_TASK_ROOT)
if v2_root.exists():
    for sp in sorted(v2_root.glob("*/status.json"))[:3]:
        try:
            data = json.loads(sp.read_text(encoding="utf-8"))
            tid = data.get("task_id", "")
            name = data.get("upload_name", "")
            stage = data.get("stage", "")
            if stage != "done":
                continue
            manifest = read_manifest(tid)
            if not manifest:
                continue
            norm_path = manifest.get("normalized_audio_path", "")
            print(f"\n=== V2 task: {tid} ({name}) ===")
            print(f"  normalized_audio_path: {norm_path}")
            print(f"  file exists: {os.path.exists(norm_path)}")
            url = media_url_for_path(norm_path, tid, "v2")
            print(f"  media URL: {url}")
        except Exception as exc:
            print(f"  Error: {exc}")
