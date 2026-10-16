#!/usr/bin/env python3
import hashlib, os, json, sys, time
sys.path.insert(0, "/opt/anki-app")

from task_worker import TaskWorker, read_status, list_all_tasks

fpath = "/tmp/anki-v2/20260521.mp3"
if not os.path.exists(fpath):
    print(f"File not found: {fpath}")
    sys.exit(1)

worker = TaskWorker()
task_id = worker.submit(
    source_path=fpath,
    upload_name="20260521.mp3",
    engine="cohere",
    model_size="small",
    api_key="",
)
print(f"Submit result: {task_id}")

time.sleep(5)

status = read_status(task_id)
print(f"Status after 5s: {json.dumps(status, indent=2, ensure_ascii=False)}")

v2_dir = f"/var/lib/anki-v2/tasks/{task_id}"
print(f"V2 task dir exists: {os.path.exists(v2_dir)}")
if os.path.exists(v2_dir):
    print(f"V2 task dir contents: {os.listdir(v2_dir)}")

time.sleep(10)
status = read_status(task_id)
print(f"Status after 15s: stage={status.get('stage')}, progress={status.get('progress')}")
