#!/bin/bash
echo "=== Check subtitle app data dir ==="
sudo grep -n "TASK_DIR\|task_dir\|DATA_DIR\|data_dir\|/var/lib\|uploads\|clips" /opt/anki-app/app_subtitle.py | head -20
echo ""

echo "=== Check subtitle app env ==="
sudo cat /etc/systemd/system/anki-streamlit-subtitle.service 2>/dev/null
echo ""

echo "=== Check if subtitle service is running ==="
sudo systemctl status anki-streamlit-subtitle.service 2>/dev/null | head -10
echo ""

echo "=== Find subtitle task data ==="
sudo find /var/lib -maxdepth 3 -type d -name "*subtitle*" -o -name "*sub*" 2>/dev/null
echo ""

echo "=== Check /var/lib/anki-subtitle ==="
sudo ls -la /var/lib/anki-subtitle/ 2>/dev/null
echo ""

echo "=== Check app_subtitle.py for data paths ==="
sudo head -100 /opt/anki-app/app_subtitle.py | grep -i "dir\|path\|data\|task\|var\|lib"
echo ""

echo "=== Check all /var/lib/anki* dirs ==="
sudo ls -la /var/lib/ | grep anki
echo ""

echo "=== Check subtitle app first 50 lines ==="
sudo head -50 /opt/anki-app/app_subtitle.py
