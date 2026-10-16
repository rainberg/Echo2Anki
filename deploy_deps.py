import paramiko
import time

key = paramiko.RSAKey.from_private_key_file(r'd:\00_dev\anki-app\deploy_key')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('89.168.93.94', username='ubuntu', pkey=key)
sftp = ssh.open_sftp()

# Ensure tmp dir exists
ssh.exec_command('mkdir -p /tmp/anki-deploy')
time.sleep(0.5)

# Upload deps.py to flat tmp path
local = r'd:\00_dev\anki-app\backend\app\deps.py'
tmp = '/tmp/anki-deploy/deps.py'
sftp.put(local, tmp)

# Copy to target
stdin, stdout, stderr = ssh.exec_command('sudo cp /tmp/anki-deploy/deps.py /opt/anki-app/backend/app/deps.py')
stdout.read(); time.sleep(0.5)

# Restart backend
stdin, stdout, stderr = ssh.exec_command('sudo systemctl restart anki-api.service')
stdout.read(); time.sleep(2)

# Verify
stdin, stdout, stderr = ssh.exec_command('sudo systemctl is-active anki-api.service')
print('Service:', stdout.read().decode().strip())

sftp.close()
ssh.close()
