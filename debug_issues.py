import paramiko
import time

key = paramiko.RSAKey.from_private_key_file(r'd:\00_dev\anki-app\deploy_key')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('89.168.93.94', username='ubuntu', pkey=key)
sftp = ssh.open_sftp()

ssh.exec_command('mkdir -p /tmp/anki-deploy')
time.sleep(0.3)

files = [
    (r'd:\00_dev\anki-app\backend\app\routers\recharge.py', '/opt/anki-app/backend/app/routers/recharge.py'),
    (r'd:\00_dev\anki-app\frontend\src\api\recharge.js', '/opt/anki-app/frontend/src/api/recharge.js'),
    (r'd:\00_dev\anki-app\frontend\src\views\AdminView.vue', '/opt/anki-app/frontend/src/views/AdminView.vue'),
]

for local, remote in files:
    basename = local.split('\\')[-1]
    tmp = f'/tmp/anki-deploy/{basename}'
    sftp.put(local, tmp)
    stdin, stdout, stderr = ssh.exec_command(f'sudo cp {tmp} {remote}')
    stdout.read()
    print(f'Deployed: {basename}')

# Rebuild frontend
print('\nBuilding frontend...')
stdin, stdout, stderr = ssh.exec_command('cd /opt/anki-app/frontend && npm run build')
exit_status = stdout.channel.recv_exit_status()
print(f'Build exit: {exit_status}')

# Restart backend
print('Restarting backend...')
stdin, stdout, stderr = ssh.exec_command('sudo systemctl restart anki-api.service')
stdout.read(); time.sleep(2)

# Verify
stdin, stdout, stderr = ssh.exec_command('sudo systemctl is-active anki-api.service')
print(f'Service: {stdout.read().decode().strip()}')

# Test proof endpoint
print('\nTest proof endpoint (no token):')
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/recharge/proof/test.png')
print(f'HTTP: {stdout.read().decode().strip()} (should be 401)')

sftp.close()
ssh.close()
