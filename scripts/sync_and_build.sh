#!/bin/bash
set -e

echo "=== Syncing Frontend Source Files ==="

cd /opt/anki-app/frontend

cp /tmp/index.html .
cp /tmp/vite.config.js .
cp /tmp/package.json .

rm -rf src
cp -r /tmp/frontend_src src

rm -rf public
cp -r /tmp/frontend_public public

echo "Source files synced."
echo ""

echo "=== Installing Dependencies ==="
npm install --production=false 2>&1 | tail -5

echo ""
echo "=== Building Frontend ==="
npx vite build 2>&1 | tail -15

echo ""
echo "=== Copying PWA files ==="
cp -f public/manifest.json dist/manifest.json 2>/dev/null || true
cp -f public/sw.js dist/sw.js 2>/dev/null || true

echo ""
echo "=== Build Result ==="
ls -la dist/index.html
ls dist/assets/ | head -5
echo ""
echo "=== Frontend build complete ==="
