import urllib.request, sys
try:
    resp = urllib.request.urlopen('http://127.0.0.1:5500/')
    print('Status', resp.getcode())
    data = resp.read(200).decode('utf-8', errors='ignore')
    print(data[:200])
except Exception as e:
    print('Error', e)
