#!/bin/bash
echo "=== V2 Streamlit Tasks Overview ==="
for dir in /var/lib/anki-v2/tasks/*/; do
    hash=$(basename "$dir")
    echo ""
    echo "--- Task: $hash ---"
    sudo cat "$dir/manifest.json" 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(f'  upload_name: {d.get(\"upload_name\", \"?\")}')
    print(f'  file_hash: {d.get(\"file_hash\", \"?\")}')
    print(f'  duration_sec: {d.get(\"file_duration_sec\", \"?\")}')
    print(f'  engine: {d.get(\"engine\", \"?\")}')
    print(f'  model_size: {d.get(\"model_size\", \"?\")}')
    print(f'  segment_count: {d.get(\"segment_count\", \"?\")}')
except: print('  (parse error)')
" 2>/dev/null || echo "  (no manifest)"
    sudo cat "$dir/status.json" 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(f'  stage: {d.get(\"stage\", \"?\")}')
    print(f'  progress: {d.get(\"progress\", \"?\")}')
    print(f'  error: {d.get(\"error\", \"\")}')
except: print('  (parse error)')
" 2>/dev/null || echo "  (no status)"
    clip_count=$(sudo ls "$dir/clips/" 2>/dev/null | wc -l)
    echo "  clips: $clip_count files"
    src_file=$(sudo ls "$dir"/*.mp3 "$dir"/*.wav "$dir"/*.m4a 2>/dev/null | head -1)
    echo "  source: $src_file"
done

echo ""
echo "=== Total clips ==="
sudo find /var/lib/anki-v2/tasks -name 'clip_*.mp3' | wc -l

echo ""
echo "=== Total disk usage ==="
sudo du -sh /var/lib/anki-v2/tasks/
