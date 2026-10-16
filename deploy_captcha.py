import paramiko
import time

key = paramiko.RSAKey.from_private_key_file(r'd:\00_dev\anki-app\deploy_key')
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('89.168.93.94', username='ubuntu', pkey=key)
sftp = client.open_sftp()

files = [
    (r'd:\00_dev\anki-app\frontend\src\components\CaptchaSliderDialog.vue', '/opt/anki-app/frontend/src/components/CaptchaSliderDialog.vue'),
    (r'd:\00_dev\anki-app\frontend\src\views\LoginView.vue', '/opt/anki-app/frontend/src/views/LoginView.vue'),
    (r'd:\00_dev\anki-app\frontend\src\views\RegisterView.vue', '/opt/anki-app/frontend/src/views/RegisterView.vue'),
]

for local, remote in files:
    sftp.put(local, remote)
    print(f'  OK: {local.split(chr(92))[-1]}')

print('\nBuilding frontend...')
stdin, stdout, stderr = client.exec_command('cd /opt/anki-app/frontend && npm run build 2>&1', timeout=120)
out = stdout.read().decode()
if 'error' in out.lower() and 'warn' not in out.lower():
    print(f'  BUILD ERROR: {out[:500]}')
else:
    print('  Build OK')

stdin, stdout, stderr = client.exec_command('curl -s -o /dev/null -w "%{http_code}" https://anki.3mudi.com/')
print(f'  HTTPS: {stdout.read().decode().strip()}')

sftp.close()
client.close()
