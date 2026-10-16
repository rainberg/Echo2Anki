#!/usr/bin/env python3
"""Debug the 404 issue on the remote server."""

import paramiko
import sys

REMOTE_HOST = "89.168.93.94"
REMOTE_USER = "ubuntu"
SSH_KEY_PATH = r"d:\00_dev\anki-app\deploy_key"


def run_cmd(ssh, cmd, timeout=30):
    print(f"  > {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    if out:
        print(f"    stdout: {out[:2000]}")
    if err:
        print(f"    stderr: {err[:2000]}")
    return out, err


def main():
    try:
        pkey = paramiko.RSAKey.from_private_key_file(SSH_KEY_PATH)
    except Exception:
        try:
            pkey = paramiko.Ed25519Key.from_private_key_file(SSH_KEY_PATH)
        except Exception:
            pkey = paramiko.ECDSAKey.from_private_key_file(SSH_KEY_PATH)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=REMOTE_HOST, username=REMOTE_USER, pkey=pkey, timeout=30)

    try:
        # Check what's running on port 8000
        print("=== What's running on port 8000? ===")
        run_cmd(ssh, "sudo ss -tlnp | grep 8000")

        # Check if nginx is involved
        print("\n=== Nginx config? ===")
        run_cmd(ssh, "sudo nginx -T 2>/dev/null | head -80")

        # Check the dist directory
        print("\n=== Frontend dist directory ===")
        run_cmd(ssh, "ls -la /opt/anki-app/frontend/dist/")

        # Check index.html content
        print("\n=== dist/index.html ===")
        run_cmd(ssh, "cat /opt/anki-app/frontend/dist/index.html")

        # Check how the backend serves static files
        print("\n=== Backend Django settings (STATIC/MEDIA)? ===")
        run_cmd(ssh, "grep -r 'STATIC\\|FRONTEND\\|DIST\\|SPA' /opt/anki-app/backend/*/settings.py 2>/dev/null || grep -r 'STATIC\\|FRONTEND\\|DIST\\|SPA' /opt/anki-app/backend/*.py 2>/dev/null || echo 'no settings found'")

        # Check Django urls
        print("\n=== Backend URL patterns ===")
        run_cmd(ssh, "cat /opt/anki-app/backend/*/urls.py 2>/dev/null || cat /opt/anki-app/backend/urls.py 2>/dev/null || echo 'no urls found'")

        # Try curl with more detail
        print("\n=== Curl verbose on localhost:8000 ===")
        run_cmd(ssh, "curl -sI http://localhost:8000/")

        # Check if there's a catch-all route in Django
        print("\n=== Django views for frontend ===")
        run_cmd(ssh, "grep -rn 'TemplateView\\|serve\\|static\\|dist\\|index.html' /opt/anki-app/backend/ 2>/dev/null | head -30")

        # Check supervisor/systemd
        print("\n=== Services running ===")
        run_cmd(ssh, "sudo systemctl list-units --type=service --state=running | grep -i anki 2>/dev/null; sudo supervisorctl status 2>/dev/null | grep anki")

    finally:
        ssh.close()


if __name__ == "__main__":
    main()
