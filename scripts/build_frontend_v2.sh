#!/bin/bash
set -e

echo "=== Building Frontend on Server ==="

cd /opt/anki-app/frontend

echo "[1/5] Creating package.json..."
cat > package.json << 'PKGEOF'
{
  "name": "anki-listening",
  "private": true,
  "version": "2.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "axios": "^1.7.0",
    "naive-ui": "^2.39.0",
    "pinia": "^2.2.0",
    "vue": "^3.5.0",
    "vue-router": "^4.4.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.1.0",
    "vite": "^5.4.0"
  }
}
PKGEOF

echo "[2/5] Installing dependencies..."
npm install --production=false 2>&1 | tail -3

echo "[3/5] Building..."
npx vite build 2>&1 | tail -10

echo "[4/5] Copying PWA files..."
mkdir -p dist
cp -f public/manifest.json dist/manifest.json 2>/dev/null || true
cp -f public/sw.js dist/sw.js 2>/dev/null || true

echo "[5/5] Verifying build..."
ls -la dist/index.html
ls -la dist/assets/ | head -5

echo ""
echo "=== Frontend build complete ==="
