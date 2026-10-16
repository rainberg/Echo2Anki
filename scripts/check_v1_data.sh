#!/bin/bash
echo "=== V2 Tasks ==="
sudo -u postgres psql -d anki -c "SELECT id, user_id, upload_name, file_duration_sec, stage, segment_count, engine, is_public, created_at FROM tasks ORDER BY created_at;"

echo ""
echo "=== V2 Segments count ==="
sudo -u postgres psql -d anki -c "SELECT COUNT(*) FROM segments;"

echo ""
echo "=== V1 Streamlit data check ==="
sudo ls -la /opt/anki-app/streamlit/ 2>/dev/null || echo "No streamlit dir"

echo ""
echo "=== V1 database check ==="
sudo -u postgres psql -l | grep -i anki || echo "No anki db found"

echo ""
echo "=== Check for V1 sqlite db ==="
sudo find /opt/anki-app -name "*.db" -o -name "*.sqlite" 2>/dev/null | head -10

echo ""
echo "=== Check uploads dir ==="
sudo find /opt/anki-app -type d -name "uploads" 2>/dev/null
sudo find /opt/anki-app -type d -name "clips" 2>/dev/null | head -10

echo ""
echo "=== Check /opt/anki-app root files ==="
sudo ls -la /opt/anki-app/ | grep -v node_modules | head -30

echo ""
echo "=== Check subtitle_component ==="
sudo ls -la /opt/anki-app/subtitle_component/ 2>/dev/null | head -20

echo ""
echo "=== Check V1 data structure ==="
sudo find /opt/anki-app -maxdepth 2 -name "*.json" -not -path "*/node_modules/*" -not -path "*/.git/*" 2>/dev/null | head -20
