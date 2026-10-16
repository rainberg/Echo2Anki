#!/usr/bin/env python3
"""Check backend main.py on remote server."""

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
        print(f"    stdout: {out[:5000]}")
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
        print("=== main.py ===")
        run_cmd(ssh, "cat /opt/anki-app/backend/app/main.py")

        print("\n=== anki-api.service ===")
        run_cmd(ssh, "sudo cat /etc/systemd/system/anki-api.service")

    finally:
        ssh.close()


if __name__ == "__main__":
    main()
