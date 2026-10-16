#!/usr/bin/env python3
"""Deploy anki-app updates to remote server via SSH (paramiko)."""

import os
import sys
import time
import paramiko
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────
REMOTE_HOST = "89.168.93.94"
REMOTE_USER = "ubuntu"
SSH_KEY_PATH = r"d:\00_dev\anki-app\deploy_key"

LOCAL_BASE = r"d:\00_dev\anki-app"
REMOTE_BACKEND_BASE = "/opt/anki-app/backend"
REMOTE_FRONTEND_BASE = "/opt/anki-app/frontend"
REMOTE_TMP_DIR = "/tmp/anki-deploy"

# Backend files: (local_path, remote_path)
BACKEND_FILES = [
    (f"{LOCAL_BASE}\\backend\\app\\routers\\recharge.py", f"{REMOTE_BACKEND_BASE}/app/routers/recharge.py"),
    (f"{LOCAL_BASE}\\backend\\app\\routers\\system.py",   f"{REMOTE_BACKEND_BASE}/app/routers/system.py"),
    (f"{LOCAL_BASE}\\backend\\app\\models.py",            f"{REMOTE_BACKEND_BASE}/app/models.py"),
    (f"{LOCAL_BASE}\\backend\\app\\main.py",              f"{REMOTE_BACKEND_BASE}/app/main.py"),
]

# Frontend source files: (local_path, remote_path)
FRONTEND_FILES = [
    (f"{LOCAL_BASE}\\frontend\\src\\api\\recharge.js",       f"{REMOTE_FRONTEND_BASE}/src/api/recharge.js"),
    (f"{LOCAL_BASE}\\frontend\\src\\api\\system.js",         f"{REMOTE_FRONTEND_BASE}/src/api/system.js"),
    (f"{LOCAL_BASE}\\frontend\\src\\views\\BillingView.vue", f"{REMOTE_FRONTEND_BASE}/src/views/BillingView.vue"),
    (f"{LOCAL_BASE}\\frontend\\src\\views\\AdminView.vue",   f"{REMOTE_FRONTEND_BASE}/src/views/AdminView.vue"),
]


def log_step(msg: str):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def log_ok(msg: str):
    print(f"  ✅ {msg}")


def log_err(msg: str):
    print(f"  ❌ {msg}")


def log_info(msg: str):
    print(f"  ℹ️  {msg}")


def create_ssh_client() -> paramiko.SSHClient:
    """Create and return a connected SSH client."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    key_path = SSH_KEY_PATH
    if not os.path.isfile(key_path):
        raise FileNotFoundError(f"SSH key not found: {key_path}")

    # Try loading as RSA key first, then Ed25519
    pkey = None
    for loader in (paramiko.RSAKey, paramiko.Ed25519Key):
        try:
            pkey = loader.from_private_key_file(key_path)
            log_info(f"Loaded key as {loader.__name__}")
            break
        except (paramiko.SSHException, ValueError):
            continue
    if pkey is None:
        raise ValueError(f"Cannot load SSH key from {key_path}")

    log_info(f"Connecting to {REMOTE_USER}@{REMOTE_HOST} ...")
    client.connect(
        hostname=REMOTE_HOST,
        username=REMOTE_USER,
        pkey=pkey,
        timeout=15,
    )
    log_ok("SSH connection established")
    return client


def run_remote_cmd(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> tuple:
    """Run a command on the remote server, return (exit_code, stdout, stderr)."""
    log_info(f"Running: {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    return exit_code, out, err


def upload_via_tmp(sftp: paramiko.SFTPClient, client: paramiko.SSHClient, local: str, remote: str, errors: list):
    """Upload a file via /tmp staging dir, then sudo cp to final destination."""
    filename = os.path.basename(local)
    # Use flat tmp path to avoid Windows Path issues with backslashes
    tmp_path = f"{REMOTE_TMP_DIR}/{filename}"

    # Upload to tmp (flat naming, no subdirs needed)
    try:
        sftp.put(local, tmp_path)
        log_ok(f"Uploaded to tmp: {filename} → {tmp_path}")
    except Exception as e:
        log_err(f"上传到临时目录失败 {filename}: {e}")
        errors.append(f"Upload to tmp failed: {local}")
        return

    # sudo cp from tmp to final destination
    exit_code, out, err = run_remote_cmd(
        client, f"sudo cp {tmp_path} {remote}", timeout=10
    )
    if exit_code == 0:
        log_ok(f"sudo cp: {tmp_path} → {remote}")
    else:
        log_err(f"sudo cp 失败: {err}")
        errors.append(f"sudo cp failed: {remote}")


def main():
    errors = []

    # ── Step 0: Verify local files exist ───────────────────────────────────
    log_step("Step 0: 验证本地文件是否存在")
    all_files = BACKEND_FILES + FRONTEND_FILES
    for local, remote in all_files:
        if not os.path.isfile(local):
            log_err(f"本地文件不存在: {local}")
            errors.append(f"Missing local file: {local}")
        else:
            log_ok(f"存在: {Path(local).name}")
    if errors:
        log_err("存在缺失的本地文件，终止部署！")
        sys.exit(1)

    # ── Connect ────────────────────────────────────────────────────────────
    log_step("Step 1: 建立 SSH 连接")
    try:
        client = create_ssh_client()
    except Exception as e:
        log_err(f"SSH 连接失败: {e}")
        sys.exit(1)

    sftp = client.open_sftp()

    # ── Prepare tmp dir ────────────────────────────────────────────────────
    log_step("Step 1b: 准备远程临时目录")
    run_remote_cmd(client, f"rm -rf {REMOTE_TMP_DIR} && mkdir -p {REMOTE_TMP_DIR}", timeout=10)

    # ── Step 2: Upload backend files ───────────────────────────────────────
    log_step("Step 2: 上传后端文件")
    for local, remote in BACKEND_FILES:
        upload_via_tmp(sftp, client, local, remote, errors)

    # ── Step 3: Upload frontend source files ───────────────────────────────
    log_step("Step 3: 上传前端源文件")
    for local, remote in FRONTEND_FILES:
        upload_via_tmp(sftp, client, local, remote, errors)

    # ── Cleanup tmp ────────────────────────────────────────────────────────
    log_step("Step 3b: 清理临时目录")
    run_remote_cmd(client, f"rm -rf {REMOTE_TMP_DIR}", timeout=10)

    sftp.close()
    if errors:
        log_err(f"有 {len(errors)} 个上传错误，但继续尝试后续步骤...")

    # ── Step 4: Build frontend on remote ───────────────────────────────────
    log_step("Step 4: 远程构建前端 (npm run build)")
    exit_code, out, err = run_remote_cmd(
        client,
        "cd /opt/anki-app/frontend && npm run build",
        timeout=180,
    )
    if exit_code == 0:
        log_ok("前端构建成功")
        if out:
            for line in out.splitlines()[-5:]:
                log_info(f"  {line}")
    else:
        log_err(f"前端构建失败 (exit={exit_code})")
        if err:
            for line in err.splitlines()[-10:]:
                log_err(f"  {line}")
        errors.append("Frontend build failed")

    # ── Step 5: Restart backend service ────────────────────────────────────
    log_step("Step 5: 重启后端服务 (anki-api.service)")
    exit_code, out, err = run_remote_cmd(
        client,
        "sudo systemctl restart anki-api.service",
        timeout=30,
    )
    if exit_code == 0:
        log_ok("anki-api.service 重启命令已执行")
    else:
        log_err(f"重启失败 (exit={exit_code}): {err}")
        errors.append("Restart anki-api failed")

    # Wait a moment for service to come up
    log_info("等待服务启动 (5秒)...")
    time.sleep(5)

    # ── Step 6: Verification ───────────────────────────────────────────────
    log_step("Step 6: 验证部署")

    # 6a: /api/recharge/info
    exit_code, out, err = run_remote_cmd(
        client, "curl -s http://localhost:8000/api/recharge/info", timeout=10
    )
    if exit_code == 0 and out:
        log_ok(f"/api/recharge/info → {out[:200]}")
    else:
        log_err(f"/api/recharge/info 失败: exit={exit_code}, out={out}, err={err}")
        errors.append("Verify /api/recharge/info failed")

    # 6b: /api/system/health
    exit_code, out, err = run_remote_cmd(
        client, "curl -s http://localhost:8000/api/system/health", timeout=10
    )
    if exit_code == 0 and out:
        log_ok(f"/api/system/health → {out[:200]}")
    else:
        log_err(f"/api/system/health 失败: exit={exit_code}, out={out}, err={err}")
        errors.append("Verify /api/system/health failed")

    # 6c: service status
    exit_code, out, err = run_remote_cmd(
        client, "sudo systemctl status anki-api.service", timeout=10
    )
    if "active (running)" in out or "active (running)" in err:
        log_ok("anki-api.service 状态: active (running)")
    else:
        log_err(f"anki-api.service 未运行: {out[:200]}")
        errors.append("anki-api.service not active")

    # ── Summary ────────────────────────────────────────────────────────────
    log_step("部署总结")
    if errors:
        log_err(f"部署完成，但有 {len(errors)} 个错误：")
        for e in errors:
            log_err(f"  - {e}")
    else:
        log_ok("🎉 所有步骤成功完成！部署无错误。")

    client.close()


if __name__ == "__main__":
    main()
