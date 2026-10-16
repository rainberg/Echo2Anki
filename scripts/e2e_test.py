import json
import urllib.request

AUTH_BASE = 'http://localhost:9000'
API_BASE = 'http://localhost:8000'

def fetch(url, data=None, token=None, method=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body.decode('utf-8', errors='replace')

print('=== Step 1: Login as e2e_test user ===')
login_data = json.dumps({'account': 'e2e_test@3mudi.com', 'password': 'test123456', 'app': 'anki'}).encode()
status, login_result = fetch(f'{AUTH_BASE}/api/auth/login/password', data=login_data)
if status != 200:
    print(f'  Login failed: {status} {login_result}')
    exit(1)
access_token = login_result['access_token']
user_info = login_result['user']
user_id = user_info['id']
print(f'  Login OK! user_id={user_id}, credits={user_info["credits"]}')

print('=== Step 2: Topup credits via Auth Service (user self-topup) ===')
topup_data = json.dumps({'amount': '100.00', 'description': 'E2E test topup'}).encode()
status, topup_result = fetch(f'{AUTH_BASE}/api/credits/topup', data=topup_data, token=access_token)
if status == 200:
    print(f'  Topup OK! credits={topup_result["credits"]}')
else:
    print(f'  Topup failed: {status} {topup_result}')
    exit(1)

print('=== Step 3: Verify token (check credits) ===')
status, verify_result = fetch(f'{AUTH_BASE}/api/auth/verify', token=access_token)
print(f'  Verify: credits={verify_result.get("credits")}, reserved={verify_result.get("credits_reserved")}')

print('=== Step 4: Backend /api/auth/me (sync credits) ===')
status, me_result = fetch(f'{API_BASE}/api/auth/me', token=access_token)
if status == 200:
    print(f'  /me OK! credits={me_result["credits"]}')
else:
    print(f'  /me failed: {status} {me_result}')
    exit(1)

print('=== Step 5: Credits reserve ===')
reserve_data = json.dumps({'amount': '5.00', 'reference_id': 'e2e:test:reserve4', 'description': 'E2E test reserve'}).encode()
status, reserve_result = fetch(f'{AUTH_BASE}/api/credits/reserve', data=reserve_data, token=access_token)
if status == 200:
    print(f'  Reserve OK! credits={reserve_result["credits"]}, reserved={reserve_result["credits_reserved"]}')
else:
    print(f'  Reserve failed: {status} {reserve_result}')
    exit(1)

print('=== Step 6: Credits settle (actual=3, refund=2) ===')
settle_data = json.dumps({'reserved_amount': '5.00', 'actual_amount': '3.00', 'reference_id': 'e2e:test:settle4', 'description': 'E2E test settle'}).encode()
status, settle_result = fetch(f'{AUTH_BASE}/api/credits/settle', data=settle_data, token=access_token)
if status == 200:
    print(f'  Settle OK! credits={settle_result["credits"]}, refund={settle_result.get("refund")}')
else:
    print(f'  Settle failed: {status} {settle_result}')
    exit(1)

print('=== Step 7: Backend /api/auth/me after credits change ===')
status, me2 = fetch(f'{API_BASE}/api/auth/me', token=access_token)
if status == 200:
    print(f'  /me OK! credits={me2["credits"]} (expected: 97.00 = 100 - 3)')
else:
    print(f'  /me failed: {status} {me2}')

print('=== Step 8: Backend /api/billing/balance ===')
status, balance = fetch(f'{API_BASE}/api/billing/balance', token=access_token)
if status == 200:
    print(f'  Balance OK! credits={balance["credits"]}, total_used={balance["total_used"]}')
else:
    print(f'  Balance failed: {status} {balance}')

print('=== Step 9: Credits refund test ===')
refund_data = json.dumps({'amount': '1.00', 'reference_id': 'e2e:test:refund1', 'description': 'E2E test refund'}).encode()
status, refund_result = fetch(f'{AUTH_BASE}/api/credits/refund', data=refund_data, token=access_token)
if status == 200:
    print(f'  Refund OK! credits={refund_result["credits"]}')
else:
    print(f'  Refund failed: {status} {refund_result}')

print('=== Step 10: Final Backend /api/auth/me ===')
status, me3 = fetch(f'{API_BASE}/api/auth/me', token=access_token)
if status == 200:
    print(f'  /me OK! credits={me3["credits"]} (expected: 98.00 = 97 + 1)')
else:
    print(f'  /me failed: {status} {me3}')

print()
print('=== ALL E2E TESTS COMPLETED ===')
