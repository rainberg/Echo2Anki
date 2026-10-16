#!/bin/bash
echo "=== Dependency Check ==="
echo "1. deep-translator:"
/opt/anki-venv/bin/pip show deep-translator 2>&1 | head -2

echo "2. V1 scripts:"
for f in ankiweb_push.py anki_sync_push.py normalize_audio.py whisper_timestamps.py align_and_cut.py cohere_asr.py openai_whisper_api.py; do
  if [ -f "/opt/anki-app/$f" ]; then echo "  $f: EXISTS"; else echo "  $f: MISSING"; fi
done

echo "3. pg_trgm extension:"
PGPASSWORD=anki_db_2026_secure psql -U anki -h localhost -d anki -c "SELECT extname FROM pg_extension WHERE extname='pg_trgm';"

echo "4. Database tables:"
PGPASSWORD=anki_db_2026_secure psql -U anki -h localhost -d anki -c "\dt"

echo "5. Backend files:"
ls /opt/anki-app/backend/app/routers/

echo "6. Frontend views:"
ls /opt/anki-app/frontend/src/views/

echo "7. Frontend API:"
ls /opt/anki-app/frontend/src/api/

echo "8. Services status:"
sudo systemctl is-active anki-api.service
sudo systemctl is-active nginx
sudo systemctl is-active anki-streamlit 2>/dev/null || echo "anki-streamlit: not found"

echo "9. Worker integration check - does worker call billing?"
grep -c "reserve_credits\|settle_credits\|refund" /opt/anki-app/backend/app/worker.py 2>/dev/null || echo "0"

echo "10. TaskDetailView has add-to-collection?"
grep -c "addCollectionItems\|addToCollection" /opt/anki-app/frontend/src/views/TaskDetailView.vue 2>/dev/null || echo "0"
