#!/usr/bin/env python3
"""Deploy anki-app public library homepage feature to remote server."""

import paramiko
import os
import sys
import time

REMOTE_HOST = "89.168.93.94"
REMOTE_USER = "ubuntu"
SSH_KEY_PATH = r"d:\00_dev\anki-app\deploy_key"
TMP_DIR = "/tmp/anki-deploy"

# Frontend files to upload: (local_path, remote_path)
FRONTEND_FILES = [
    (r"d:\00_dev\anki-app\frontend\src\router\index.js", "/opt/anki-app/frontend/src/router/index.js"),
    (r"d:\00_dev\anki-app\frontend\src\App.vue", "/opt/anki-app/frontend/src/App.vue"),
    (r"d:\00_dev\anki-app\frontend\src\views\PublicView.vue", "/opt/anki-app/frontend/src/views/PublicView.vue"),
    (r"d:\00_dev\anki-app\frontend\src\views\PublicDetailView.vue", "/opt/anki-app/frontend/src/views/PublicDetailView.vue"),
]

# Backend files to upload (SPA serving support)
BACKEND_FILES = [
    (r"d:\00_dev\anki-app\backend\app\main.py", "/opt/anki-app/backend/app/main.py"),
    (r"d:\00_dev\anki-app\backend\app\config.py", "/opt/anki-app/backend/app/config.py"),
]


def run_cmd(ssh, cmd, timeout=120):
    """Run a command via SSH and print output."""
    print(f"  > {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    exit_code = stdout.channel.recv_exit_status()
    if out:
        print(f"    stdout: {out}")
    if err:
        print(f"    stderr: {err}")
    return exit_code, out, err


def upload_files(ssh, files, label):
    """Upload a list of (local, remote) file pairs via SFTP to tmp, then sudo cp."""
    sftp = ssh.open_sftp()
    for local_path, remote_path in files:
        filename = os.path.basename(remote_path)
        # Use subdirectory in tmp to avoid name collisions
        tmp_subdir = f"{TMP_DIR}/{label}"
        run_cmd(ssh, f"mkdir -p {tmp_subdir}")
        tmp_remote = f"{tmp_subdir}/{filename}"
        print(f"  Uploading {local_path} -> {tmp_remote}")
        sftp.put(local_path, tmp_remote)

        # Copy to target with sudo
        target_dir = os.path.dirname(remote_path)
        run_cmd(ssh, f"sudo mkdir -p {target_dir}")
        run_cmd(ssh, f"sudo cp {tmp_remote} {remote_path}")
        run_cmd(ssh, f"sudo chown $(id -u):$(id -g) {remote_path}")
    sftp.close()


def main():
    # Load SSH key
    print("[1/7] Loading SSH key ...")
    try:
        pkey = paramiko.RSAKey.from_private_key_file(SSH_KEY_PATH)
    except paramiko.PasswordRequiredException:
        print("ERROR: SSH key requires a passphrase.")
        sys.exit(1)
    except paramiko.SSHException:
        try:
            pkey = paramiko.ECDSAKey.from_private_key_file(SSH_KEY_PATH)
        except Exception:
            try:
                pkey = paramiko.Ed25519Key.from_private_key_file(SSH_KEY_PATH)
            except Exception as e:
                print(f"ERROR: Cannot load SSH key: {e}")
                sys.exit(1)

    # Connect
    print(f"[2/7] Connecting to {REMOTE_USER}@{REMOTE_HOST} ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=REMOTE_HOST, username=REMOTE_USER, pkey=pkey, timeout=30)
    print("  Connected!")

    try:
        run_cmd(ssh, f"mkdir -p {TMP_DIR}")

        # Upload frontend files
        print("[3/7] Uploading frontend files ...")
        upload_files(ssh, FRONTEND_FILES, "frontend")
        print("  Frontend files uploaded!")

        # Upload backend files
        print("[4/7] Uploading backend files (SPA serving support) ...")
        upload_files(ssh, BACKEND_FILES, "backend")
        print("  Backend files uploaded!")

        # Rebuild frontend
        print("[5/7] Rebuilding frontend ...")
        exit_code, out, err = run_cmd(ssh, "cd /opt/anki-app/frontend && npm run build", timeout=300)
        if exit_code != 0:
            print(f"WARNING: npm run build exited with code {exit_code}")

        # Restart backend service
        print("[6/7] Restarting anki-api service ...")
        run_cmd(ssh, "sudo systemctl restart anki-api")
        time.sleep(3)
        # Check service status
        exit_code, out, err = run_cmd(ssh, "sudo systemctl is-active anki-api")
        if "active" in out:
            print("  ✅ anki-api service is active")
        else:
            print(f"  ❌ anki-api service status: {out}")
            run_cmd(ssh, "sudo journalctl -u anki-api -n 20 --no-pager")

        # Verification
        print("[7/7] Verification ...")

        print("Checking http://localhost:8000/ ...")
        exit_code, out, err = run_cmd(ssh, 'curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/')
        if out == "200":
            print("  ✅ Homepage returns 200")
        else:
            print(f"  ❌ Homepage returned {out} (expected 200)")

        print("Checking http://localhost:8000/api/public/shares?per_page=1 ...")
        exit_code, out, err = run_cmd(ssh, 'curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/public/shares?per_page=1')
        if out == "200":
            print("  ✅ Public API returns 200")
        else:
            print(f"  ❌ Public API returned {out} (expected 200, not 401)")

        # Cleanup
        run_cmd(ssh, f"rm -rf {TMP_DIR}")

    finally:
        ssh.close()
        print("\nDone. SSH connection closed.")


if __name__ == "__main__":
    main()
