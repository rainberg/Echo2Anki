#!/bin/bash
echo "=== Check subtitle app for translation storage ==="
sudo grep -n "chinese\|translat\|翻译\|zh_text\|chinese_text" /opt/anki-app/app_subtitle.py | head -30
echo ""
echo "=== Check for separate translation files ==="
for dir in /var/lib/anki-streamlit-subtitle/tasks/*/; do
    hash=$(basename "$dir")
    files=$(sudo ls "$dir" 2>/dev/null | grep -v ".mp3" | tr '\n' ' ')
    if [ -n "$files" ]; then
        echo "$hash: $files"
    fi
done
echo ""
echo "=== Check V2 Streamlit for translations ==="
for dir in /var/lib/anki-v2/tasks/*/; do
    hash=$(basename "$dir")
    files=$(sudo ls "$dir" 2>/dev/null | grep -v ".mp3" | tr '\n' ' ')
    if [ -n "$files" ]; then
        echo "$hash: $files"
    fi
done
echo ""
echo "=== Sample V2 manifest with translation check ==="
sudo cat /var/lib/anki-v2/tasks/1cd32e199b9f70e0/manifest.json | python3 -c "
import sys,json
d=json.load(sys.stdin)
segs=d.get('segments',[])
has_zh=sum(1 for s in segs if s.get('chinese_text','').strip())
print(f'Total: {len(segs)}, With chinese_text: {has_zh}')
if has_zh:
    for s in segs[:2]:
        print(f'  DE: {s.get(\"text\",\"\")[:50]}')
        print(f'  ZH: {s.get(\"chinese_text\",\"\")[:50]}')
" 2>/dev/null
