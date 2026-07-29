import urllib.request
req = urllib.request.Request('http://localhost:8000/api/parametric/cohorts', headers={'x-role': 'group_manager', 'x-user-email': 'random@email.com'})
print(urllib.request.urlopen(req).read().decode('utf-8'))
