import urllib.request, json, time
URL = 'http://127.0.0.1:5001/api/meta/routes'
for i in range(5):
    try:
        with urllib.request.urlopen(URL) as resp:
            data = resp.read().decode()
        print('ROUTES_RESPONSE_START')
        print(data[:2000])
        print('ROUTES_RESPONSE_END')
        break
    except Exception as e:
        print('Attempt', i+1, 'failed:', e)
        time.sleep(1)
else:
    print('Failed to fetch routes after retries')
