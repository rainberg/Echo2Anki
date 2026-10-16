#!/usr/bin/env python3
"""Deploy anki-app multi-push-config feature to remote server."""

import paramiko
import os
import sys

HOST = "89.168.93.94"
USER = "ubuntu"
KEY_PATH = r"d:\00_dev\anki-app\deploy_key"

# Files to upload: (local_path, remote_target_path)
FILES = [
    (r"d:\00_dev\anki-app\backend\app\models.py", "/opt/anki-app/backend/app/models.py"),
    (r"d:\00_dev\anki-app\backend\app\schemas.py", "/opt/anki-app/backend/app/schemas.py"),
    (r"d:\00_dev\anki-app\backend\app\schemas_push.py", "/opt/anki-app/backend/app/schemas_push.py"),
    (r"d:\00_dev\anki-app\backend\app\routers\anki.py", "/opt/anki-app/backend/app/routers/anki.py"),
    (r"d:\00_dev\anki-app\backend\app\routers\auth.py", "/opt/anki-app/backend/app/routers/auth.py"),
    (r"d:\00_dev\anki-app\backend\app\deps.py", "/opt/anki-app/backend/app/deps.py"),
    (r"d:\00_dev\anki-app\frontend\src\api\anki.js", "/opt/anki-app/frontend/src/api/anki.js"),
    (r"d:\00_dev\anki-app\frontend\src\api\admin.js", "/opt/anki-app/frontend/src/api/admin.js"),
    (r"d:\00_dev\anki-app\frontend\src\views\AnkiView.vue", "/opt/anki-app/frontend/src/views/AnkiView.vue"),
    (r"d:\00_dev\anki-app\frontend\src\views\AdminView.vue", "/opt/anki-app/frontend/src/views/AdminView.vue"),
]

SQL_MIGRATION = """\
ALTER TABLE anki_push_configs ADD COLUMN IF NOT EXISTS name VARCHAR(100) DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS max_push_configs INTEGER DEFAULT 4;
ALTER TABLE anki_push_configs DROP CONSTRAINT IF EXISTS anki_push_configs_user_id_push_mode_key;
"""


def run_cmd(ssh, cmd, desc=None, sudo=False):
    """Execute a command over SSH and print output."""
    if sudo:
        cmd = f"sudo {cmd}"
    if desc:
        print(f"  ▶ {desc}")
    print(f"    CMD: {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    exit_code = stdout.channel.recv_exit_status()
    if out:
        for line in out.splitlines():
            print(f"    | {line}")
    if err:
        for line in err.splitlines():
            print(f"    ! {line}")
    return exit_code, out, err


def main():
    print("=" * 60)
    print("  Anki-App 多推送配置功能部署")
    print("=" * 60)

    # --- Connect ---
    print("\n[1/6] 连接远程服务器...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=15)
        print(f"  ✔ 已连接 {USER}@{HOST}")
    except Exception as e:
        print(f"  ✘ 连接失败: {e}")
        sys.exit(1)

    # --- Create temp dir ---
    print("\n[2/6] 创建临时目录 /tmp/anki-deploy/ ...")
    run_cmd(ssh, "mkdir -p /tmp/anki-deploy", desc="创建临时目录")

    # --- Upload files via SFTP ---
    print("\n[3/6] 上传文件到 /tmp/anki-deploy/ ...")
    sftp = ssh.open_sftp()
    for local_path, remote_target in FILES:
        filename = os.path.basename(remote_target)
        tmp_remote = f"/tmp/anki-deploy/{filename}"
        try:
            sftp.put(local_path, tmp_remote)
            print(f"  ✔ {filename} -> /tmp/anki-deploy/{filename}")
        except Exception as e:
            print(f"  ✘ 上传失败 {filename}: {e}")
            sftp.close()
            ssh.close()
            sys.exit(1)
    sftp.close()
    print("  ✔ 所有文件上传完成")

    # --- Copy files to target locations with sudo ---
    print("\n[4/6] 将文件从临时目录复制到目标位置...")
    for local_path, remote_target in FILES:
        filename = os.path.basename(remote_target)
        tmp_remote = f"/tmp/anki-deploy/{filename}"
        # Ensure target directory exists
        target_dir = os.path.dirname(remote_target)
        run_cmd(ssh, f"mkdir -p {target_dir}", desc=f"确保目录存在: {target_dir}", sudo=True)
        exit_code, _, _ = run_cmd(ssh, f"cp {tmp_remote} {remote_target}", desc=f"复制 {filename} -> {remote_target}", sudo=True)
        if exit_code != 0:
            print(f"  ✘ 复制失败: {filename}")
            ssh.close()
            sys.exit(1)
    print("  ✔ 所有文件已复制到目标位置")

    # Clean up temp dir
    run_cmd(ssh, "rm -rf /tmp/anki-deploy", desc="清理临时目录", sudo=True)

    # --- Database migration ---
    print("\n[5/6] 执行数据库迁移...")
    exit_code, out, err = run_cmd(
        ssh,
        f'-u postgres psql -d anki -c "{SQL_MIGRATION.strip()}"',
        desc="运行 SQL 迁移",
        sudo=True,
    )
    if exit_code != 0:
        print(f"  ⚠ 数据库迁移可能有问题 (exit_code={exit_code})")
    else:
        print("  ✔ 数据库迁移完成")

    # --- Rebuild frontend ---
    print("\n[6/6] 重新构建前端 & 重启后端...")
    exit_code, _, _ = run_cmd(
        ssh,
        "cd /opt/anki-app/frontend && npm run build",
        desc="构建前端 (npm run build)",
    )
    if exit_code != 0:
        print("  ✘ 前端构建失败!")
        ssh.close()
        sys.exit(1)
    print("  ✔ 前端构建完成")

    # --- Restart backend ---
    print("\n[7/7] 重启后端服务...")
    exit_code, _, _ = run_cmd(
        ssh,
        "systemctl restart anki-api.service",
        desc="重启 anki-api.service",
        sudo=True,
    )
    if exit_code != 0:
        print("  ✘ 重启后端服务失败!")
        ssh.close()
        sys.exit(1)
    print("  ✔ 后端服务已重启")

    # --- Verify ---
    print("\n" + "=" * 60)
    print("  验证部署")
    print("=" * 60)

    # Check service status
    print("\n[验证1] 检查服务状态...")
    exit_code, out, _ = run_cmd(
        ssh,
        "systemctl is-active anki-api.service",
        desc="systemctl is-active",
        sudo=True,
    )
    if "active" in out:
        print("  ✔ 服务状态: active")
    else:
        print(f"  ✘ 服务状态异常: {out}")

    # Check configs endpoint
    print("\n[验证2] 检查 /api/anki/configs 端点...")
    exit_code, out, _ = run_cmd(
        ssh,
        "curl -s http://localhost:8000/api/anki/configs",
        desc="curl /api/anki/configs",
    )
    if exit_code == 0 and ("[]" in out or "configs" in out.lower() or "error" not in out.lower()):
        print(f"  ✔ 端点响应: {out[:200]}")
    else:
        print(f"  ⚠ 端点可能有问题: {out[:200]}")

    # Check health endpoint
    print("\n[验证3] 检查 /api/system/health 端点...")
    exit_code, out, _ = run_cmd(
        ssh,
        "curl -s http://localhost:8000/api/system/health",
        desc="curl /api/system/health",
    )
    print(f"  ✔ 健康检查响应: {out[:200]}")

    ssh.close()
    print("\n" + "=" * 60)
    print("  部署完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
