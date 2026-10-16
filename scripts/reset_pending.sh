#!/bin/bash
psql -U anki -d anki -c "UPDATE tasks SET stage='failed', error='Reset during Phase 2 deployment' WHERE stage='pending';"
echo "Pending tasks reset to failed"
