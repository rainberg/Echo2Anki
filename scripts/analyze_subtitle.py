#!/usr/bin/env python3
import json, os, sys

WORK_DIR = "/var/lib/anki-streamlit-subtitle/tasks"

for d in sorted(os.listdir(WORK_DIR)):
    full = os.path.join(WORK_DIR, d)
    if not os.path.isdir(full):
        continue
    mf = os.path.join(full, "manifest.json")
    if not os.path.exists(mf):
        continue
    with open(mf) as f:
        m = json.load(f)
    segs = m.get("segments", [])
    upload_key = m.get("upload_key", "")
    file_hash = ""
    if upload_key and ":" in upload_key:
        file_hash = upload_key.split(":")[2] if len(upload_key.split(":")) > 2 else ""
    has_clips = os.path.isdir(os.path.join(full, "subtitle_clips"))
    clip_count = len(os.listdir(os.path.join(full, "subtitle_clips"))) if has_clips else 0
    print(f"{d}: upload_name={m.get('upload_name','')}, upload_key_file={upload_key.split(':')[0] if upload_key else ''}, hash={file_hash[:16]}..., segs={len(segs)}, clips={clip_count}")
