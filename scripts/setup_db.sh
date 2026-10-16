#!/bin/bash
set -e

sudo -u postgres psql <<EOF
CREATE USER anki WITH PASSWORD 'anki_db_2026_secure';
CREATE DATABASE anki OWNER anki ENCODING 'UTF8';
GRANT ALL PRIVILEGES ON DATABASE anki TO anki;
EOF

sudo -u postgres psql -d anki <<EOF
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
EOF

echo "DB setup done"
