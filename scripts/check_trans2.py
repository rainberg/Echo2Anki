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
    translations = m.get("translations", [])
    if not segs:
        continue
    has_zh = sum(1 for s in segs if s.get("chinese_text", "").strip())
    upload_key = m.get("upload_key", "")
    fname = upload_key.split(":")[0] if upload_key else d
    print(f"{d} ({fname}):")
    print(f"  segments: {len(segs)}, translations: {len(translations)}, chinese_text in segs: {has_zh}")
    if translations:
        print(f"  sample translations:")
        for i, t in enumerate(translations[:3]):
            print(f"    [{i}] {t[:60]}")
    print()
