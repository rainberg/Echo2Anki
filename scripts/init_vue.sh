#!/bin/bash
set -e

sudo mkdir -p /opt/anki-app/frontend
sudo chown ubuntu:ubuntu /opt/anki-app/frontend

cd /opt/anki-app/frontend

npm create vite@latest . -- --template vue 2>&1 || true

npm install vue-router@4 pinia @vicons/ionicons5 axios naive-ui 2>&1 | tail -5

echo "Vue 3 project initialized"
