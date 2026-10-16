import urllib.request, json
req = urllib.request.Request('http://localhost:9000/api/auth/captcha/generate')
resp = urllib.request.urlopen(req)
result = json.loads(resp.read())
print('Keys:', list(result.keys()))
for k, v in result.items():
    if isinstance(v, str) and len(v) > 50:
        print(k + ': ' + v[:60] + '... (len=' + str(len(v)) + ')')
    else:
        print(k + ':', v)
