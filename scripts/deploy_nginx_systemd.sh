#!/bin/bash
set -e

echo "=== Phase 1.8: Nginx + Systemd Configuration ==="

echo "[1/4] Writing Nginx config..."

sudo tee /etc/nginx/sites-available/anki.3mudi.com > /dev/null << 'NGINXEOF'
server {
    server_name anki.3mudi.com;

    client_max_body_size 500m;
    client_body_timeout 86400;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript image/svg+xml;
    gzip_min_length 256;

    location /sync/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }

    location /msync/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }

    location = /sync-health {
        proxy_pass http://127.0.0.1:8080/health;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /subtitle-media/ {
        alias /var/lib/anki-streamlit-subtitle/tasks/;
        autoindex off;
        types { audio/mpeg mp3; audio/mp4 m4a; audio/ogg ogg; audio/wav wav; }
        add_header Cache-Control "private, max-age=3600";
        add_header Accept-Ranges bytes;
        try_files $uri =404;
    }

    location /v2-media/ {
        alias /var/lib/anki-v2/tasks/;
        autoindex off;
        types { audio/mpeg mp3; audio/mp4 m4a; audio/ogg ogg; audio/wav wav; }
        add_header Cache-Control "private, max-age=3600";
        add_header Accept-Ranges bytes;
        try_files $uri =404;
    }

    location /media/ {
        alias /var/lib/anki-v2/tasks/;
        autoindex off;
        types { audio/mpeg mp3; audio/mp4 m4a; audio/ogg ogg; audio/wav wav; }
        add_header Cache-Control "private, max-age=3600";
        add_header Accept-Ranges bytes;
        try_files $uri =404;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
    }

    location /legacy/ {
        rewrite ^/legacy(/.*)$ $1 break;
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    location /legacy {
        return 302 /legacy/;
    }

    location /assets/ {
        root /opt/anki-app/frontend/dist;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        root /opt/anki-app/frontend/dist;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    listen [::]:443 ssl ipv6only=on;
    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/anki.3mudi.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/anki.3mudi.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

server {
    if ($host = anki.3mudi.com) {
        return 301 https://$host$request_uri;
    }

    listen 80;
    listen [::]:80;
    server_name anki.3mudi.com;
    return 404;
}
NGINXEOF

echo "[2/4] Writing FastAPI systemd service..."

sudo tee /etc/systemd/system/anki-api.service > /dev/null << 'SYSTEMDEOF'
[Unit]
Description=Anki Audio Processing API (FastAPI)
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/anki-app/backend
Environment=PATH=/opt/anki-venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/opt/anki-venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SYSTEMDEOF

echo "[3/4] Enabling and starting services..."

sudo systemctl daemon-reload
sudo systemctl enable anki-api.service

pkill -f 'uvicorn app.main' 2>/dev/null || true
sleep 1
sudo systemctl start anki-api.service
sleep 2
sudo systemctl status anki-api.service --no-pager || true

echo "[4/4] Testing Nginx config and reloading..."

sudo nginx -t 2>&1
sudo systemctl reload nginx 2>&1 || sudo systemctl restart nginx 2>&1

echo ""
echo "=== Testing API ==="
sleep 2
curl -s http://127.0.0.1:8000/api/health
echo ""
echo "=== Testing API via Nginx ==="
curl -s https://anki.3mudi.com/api/health
echo ""
echo "=== Phase 1.8 Complete ==="
