import paramiko
import sys

def ssh_exec(cmd):
    key = paramiko.RSAKey.from_private_key_file(r'd:\00_dev\anki-app\deploy_key')
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('89.168.93.94', username='ubuntu', pkey=key)
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    client.close()
    return out, err

if __name__ == '__main__':
    cmd = sys.argv[1]
    out, err = ssh_exec(cmd)
    if out:
        print(out)
    if err:
        print("STDERR:", err, file=sys.stderr)
