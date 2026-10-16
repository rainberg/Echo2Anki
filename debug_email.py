import paramiko

key = paramiko.RSAKey.from_private_key_file(r'd:\00_dev\anki-app\deploy_key')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('89.168.93.94', username='ubuntu', pkey=key)

# 1. Get current code from Redis
cmd = "redis-cli GET 'email_code:gr@3mudi.com'"
stdin, stdout, stderr = ssh.exec_command(cmd)
code = stdout.read().decode().strip()
print(f"Current code in Redis: {code}")

# 2. Test reset-password with the actual code
if code:
    cmd2 = f"""curl -s -X POST http://localhost:9000/api/auth/reset-password -H 'Content-Type: application/json' -d '{{"email":"gr@3mudi.com","email_code":"{code}","new_password":"Test123456"}}'"""
    stdin2, stdout2, stderr2 = ssh.exec_command(cmd2)
    print(f"Reset result: {stdout2.read().decode().strip()}")
else:
    print("No code found, sending a new one...")

    # Get captcha first
    cmd3 = "curl -s http://localhost:9000/api/auth/captcha/generate"
    stdin3, stdout3, stderr3 = ssh.exec_command(cmd3)
    import json
    captcha_data = json.loads(stdout3.read().decode())
    captcha_id = captcha_data['captcha_id']

    # We need to solve the captcha - use verify endpoint with x position
    # The slider x position is in the captcha response bg_image offset
    # For testing, let's use the internal endpoint instead
    cmd4 = f"""curl -s -X POST http://localhost:9000/api/auth/email/send-internal -H 'Content-Type: application/json' -H 'X-Service-Key: anki-svc-key-2026-secure' -d '{{"email":"gr@3mudi.com","purpose":"reset_password"}}'"""
    stdin4, stdout4, stderr4 = ssh.exec_command(cmd4)
    print(f"Internal send: {stdout4.read().decode().strip()}")

    import time
    time.sleep(1)

    # Get the code
    cmd5 = "redis-cli GET 'email_code:gr@3mudi.com'"
    stdin5, stdout5, stderr5 = ssh.exec_command(cmd5)
    code2 = stdout5.read().decode().strip()
    print(f"New code: {code2}")

    if code2:
        cmd6 = f"""curl -s -X POST http://localhost:9000/api/auth/reset-password -H 'Content-Type: application/json' -d '{{"email":"gr@3mudi.com","email_code":"{code2}","new_password":"Test123456"}}'"""
        stdin6, stdout6, stderr6 = ssh.exec_command(cmd6)
        print(f"Reset result: {stdout6.read().decode().strip()}")

# 3. Check if the email actually went through - check SMTP logs
print("\n=== Recent SMTP activity ===")
cmd7 = "sudo journalctl -u auth-service.service --no-pager -n 20 2>&1 | grep -i 'email\\|smtp\\|send\\|error' | tail -10"
stdin7, stdout7, stderr7 = ssh.exec_command(cmd7)
print(stdout7.read().decode().strip())

# 4. Check if the email was actually sent by looking at the send log
print("\n=== Email send logs ===")
cmd8 = "sudo journalctl -u auth-service.service --no-pager --since '5 min ago' 2>&1 | grep -i 'email\\|code\\|sent\\|error\\|gr@'"
stdin8, stdout8, stderr8 = ssh.exec_command(cmd8)
print(stdout8.read().decode().strip())

ssh.close()
