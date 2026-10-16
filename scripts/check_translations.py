#!/usr/bin/env python3
import json, os

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
    if not segs:
        continue
    has_zh = sum(1 for s in segs if s.get("chinese_text", "").strip())
    total = len(segs)
    upload_key = m.get("upload_key", "")
    fname = upload_key.split(":")[0] if upload_key else d
    print(f"{d} ({fname}): {has_zh}/{total} have chinese_text")
    if has_zh > 0:
        sample = [s for s in segs if s.get("chinese_text", "").strip()][:2]
        for s in sample:
            print(f"  DE: {s.get('text','')[:50]}")
            print(f"  ZH: {s.get('chinese_text','')[:50]}")
