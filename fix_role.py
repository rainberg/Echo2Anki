import paramiko

key = paramiko.RSAKey.from_private_key_file(r'd:\00_dev\anki-app\deploy_key')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('89.168.93.94', username='ubuntu', pkey=key)

# Fix anki local DB role to match auth-service
cmd = "sudo -u postgres psql -d anki -c \"UPDATE users SET role='admin' WHERE email='ooJerry@gmail.com';\""
stdin, stdout, stderr = ssh.exec_command(cmd)
print('Update:', stdout.read().decode().strip())
err = stderr.read().decode().strip()
if err and 'Permission denied' not in err:
    print('err:', err)

# Verify
cmd2 = "sudo -u postgres psql -d anki -t -c \"SELECT email, role FROM users WHERE email='ooJerry@gmail.com';\""
stdin2, stdout2, stderr2 = ssh.exec_command(cmd2)
print('Verify:', stdout2.read().decode().strip())

ssh.close()
