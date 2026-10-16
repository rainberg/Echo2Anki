#!/bin/bash
echo "=== Subtitle task dirs ==="
sudo ls -la /var/lib/anki-streamlit-subtitle/tasks/ 2>/dev/null
echo ""

echo "=== Each subtitle task detail ==="
for dir in /var/lib/anki-streamlit-subtitle/tasks/*/; do
    hash=$(basename "$dir")
    echo ""
    echo "--- Subtitle Task: $hash ---"
    sudo cat "$dir/manifest.json" 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(f'  upload_name: {d.get(\"upload_name\", \"?\")}')
    print(f'  file_hash: {d.get(\"file_hash\", \"?\")}')
    print(f'  engine: {d.get(\"engine\", \"?\")}')
    print(f'  model_size: {d.get(\"model_size\", \"?\")}')
    print(f'  segment_count: {d.get(\"segment_count\", len(d.get(\"segments\", [])))}')
    print(f'  created_at: {d.get(\"created_at\", \"?\")}')
    segs = d.get('segments', [])
    if segs:
        print(f'  first segment: [{segs[0].get(\"start\",\"?\")}-{segs[0].get(\"end\",\"?\")}] {segs[0].get(\"text\",\"\")[:60]}')
except Exception as e: print(f'  (parse error: {e})')
" 2>/dev/null || echo "  (no manifest)"

    echo "  Files:"
    sudo ls "$dir" 2>/dev/null | head -10
    clip_dir=$(sudo ls -d "$dir/subtitle_clips" "$dir/clips" 2>/dev/null | head -1)
    if [ -n "$clip_dir" ]; then
        clip_count=$(sudo ls "$clip_dir" 2>/dev/null | wc -l)
        echo "  Clips: $clip_count files in $clip_dir"
    fi
done

echo ""
echo "=== Total subtitle clips ==="
sudo find /var/lib/anki-streamlit-subtitle/tasks -name 'clip_*.mp3' -o -name 'subtitle_clip_*.mp3' 2>/dev/null | wc -l

echo ""
echo "=== Disk usage ==="
sudo du -sh /var/lib/anki-streamlit-subtitle/tasks/ 2>/dev/null
