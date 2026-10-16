#!/bin/bash
set -e

echo "=== Step 1: Check current credits_reserved column ==="
EXIST=$(sudo -u postgres psql -d anki -t -A -c "SELECT COUNT(*) FROM information_schema.columns WHERE table_name='users' AND column_name='credits_reserved';")
echo "credits_reserved exists: $EXIST"

if [ "$EXIST" = "0" ]; then
    echo "Adding credits_reserved column..."
    sudo -u postgres psql -d anki -c "ALTER TABLE users ADD COLUMN credits_reserved NUMERIC(10,2) NOT NULL DEFAULT 0;"
    echo "Column added successfully."
else
    echo "Column already exists, skipping."
fi

echo ""
echo "=== Step 2: Create pg_trgm extension ==="
sudo -u postgres psql -d anki -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
echo "pg_trgm extension ready."

echo ""
echo "=== Step 3: Create GIN indexes for full-text search ==="
sudo -u postgres psql -d anki -c "CREATE INDEX IF NOT EXISTS idx_segments_german_trgm ON segments USING gin (german_text gin_trgm_ops);"
sudo -u postgres psql -d anki -c "CREATE INDEX IF NOT EXISTS idx_segments_chinese_trgm ON segments USING gin (chinese_text gin_trgm_ops);"
echo "GIN indexes created."

echo ""
echo "=== Migration complete ==="
sudo -u postgres psql -d anki -c "\d users" | grep credits
