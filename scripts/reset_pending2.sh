#!/bin/bash
PGPASSWORD=anki_db_2026_secure psql -U anki -h localhost -d anki -c "UPDATE tasks SET stage='failed', error='Reset during Phase 2 deployment' WHERE stage='pending';"
echo "Done"
