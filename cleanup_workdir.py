#!/usr/bin/env python3
import os, json, sys
sys.path.insert(0, "/opt/anki-app")
from task_worker import list_all_tasks, STAGE_DONE

WORK_DIR = "/tmp/anki-v2"
V2_TASK_ROOT = "/var/lib/anki-v2/tasks"

print("=== WORK_DIR files ===")
if os.path.isdir(WORK_DIR):
    for f in sorted(os.listdir(WORK_DIR)):
        fpath = os.path.join(WORK_DIR, f)
        if os.path.isfile(fpath):
            print(f"  {f} ({os.path.getsize(fpath)/(1024*1024):.1f} MB)")

print("\n=== Done v2 tasks ===")
for t in list_all_tasks():
    if t.get("source") == "subtitle":
        continue
    if t.get("stage") == STAGE_DONE:
        tid = t.get("task_id", "")
        name = t.get("upload_name", "")
        sp = os.path.join(V2_TASK_ROOT, tid, "status.json")
        if os.path.exists(sp):
            with open(sp) as f:
                d = json.load(f)
            orig = d.get("original_upload_path", "")
            print(f"  {tid} | {name} | original_upload_path={orig}")

print("\n=== Cleaning WORK_DIR files for done tasks ===")
cleaned = 0
for t in list_all_tasks():
    if t.get("source") == "subtitle":
        continue
    if t.get("stage") == STAGE_DONE:
        name = t.get("upload_name", "")
        if name and os.path.isfile(os.path.join(WORK_DIR, name)):
            fpath = os.path.join(WORK_DIR, name)
            os.remove(fpath)
            print(f"  Removed: {name}")
            cleaned += 1

print(f"\nCleaned {cleaned} files from WORK_DIR")
print("\n=== WORK_DIR after cleanup ===")
if os.path.isdir(WORK_DIR):
    remaining = [f for f in os.listdir(WORK_DIR) if os.path.isfile(os.path.join(WORK_DIR, f))]
    if remaining:
        for f in sorted(remaining):
            print(f"  {f}")
    else:
        print("  (empty)")
