#!/usr/bin/env python3
import hashlib, os, json, sys
from pathlib import Path

sys.path.insert(0, "/opt/anki-app")

fpath = "/tmp/anki-v2/20260521.mp3"
if not os.path.exists(fpath):
    print(f"File not found: {fpath}")
    sys.exit(1)

h = hashlib.sha256()
with open(fpath, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
        h.update(chunk)
fhash = h.hexdigest()
print(f"File hash: {fhash}")
print(f"Task ID: {fhash[:16]}")

sub_root = Path("/var/lib/anki-streamlit-subtitle/tasks")
if sub_root.exists():
    for mp in sorted(sub_root.glob("*/manifest.json")):
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
            uk = data.get("upload_key", "")
            tid = data.get("task_id", "")
            name = data.get("upload_name", "")
            sub_hash = uk.split(":")[-1] if uk else ""
            match = "MATCH!" if sub_hash.startswith(fhash[:16]) else ""
            print(f"  Subtitle: {tid} | {name} | hash_prefix={sub_hash[:16]} {match}")
        except Exception as exc:
            print(f"  Error reading {mp}: {exc}")

task_dir = f"/var/lib/anki-v2/tasks/{fhash[:16]}"
print(f"Task dir exists: {os.path.exists(task_dir)}")

print("\n--- Testing submit ---")
from task_worker import TaskWorker, find_task_by_hash, list_all_tasks

existing = find_task_by_hash(fhash)
print(f"find_task_by_hash result: {existing}")

all_tasks = list_all_tasks()
print(f"Total tasks: {len(all_tasks)}")
for t in all_tasks[:5]:
    print(f"  {t.get('task_id','')} | {t.get('upload_name','')} | {t.get('stage','')} | hash={t.get('file_hash','')[:16]}")

worker = TaskWorker()
task_id = worker.submit(
    source_path=fpath,
    upload_name="20260521.mp3",
    engine="cohere",
    model_size="small",
    api_key="",
)
print(f"Submit result: {task_id}")

import time
time.sleep(3)

from task_worker import read_status
status = read_status(task_id)
print(f"Status after 3s: {json.dumps(status, indent=2)}")
