import requests, bs4, re
from urllib.parse import urljoin
from datetime import date, datetime, timezone, timedelta

url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# First request to get a session
resp = s.get(url, timeout=30)
print(f'Initial cookies:')
for cookie in s.cookies:
    print(f'  {cookie.name}={cookie.value!r} domain={cookie.domain} path={cookie.path}')

# The session ID might be empty. Let me try to set a manual session
# by visiting a different page first
resp2 = s.get('https://www.valadares.mg.gov.br/', timeout=30)
print(f'\nAfter homepage:')
for cookie in s.cookies:
    print(f'  {cookie.name}={cookie.value!r} domain={cookie.domain} path={cookie.path}')

# Now try the diario page again
resp3 = s.get(url, timeout=30)
print(f'\nAfter diario page again:')
for cookie in s.cookies:
    print(f'  {cookie.name}={cookie.value!r} domain={cookie.domain} path={cookie.path}')

# Check the session cookie value
sess_cookie = [c for c in s.cookies if c.name == 'ASP.NET_SessionId']
if sess_cookie:
    print(f'\nASP.NET_SessionId value: {sess_cookie[0].value!r}')
else:
    print('\nNo ASP.NET_SessionId cookie found')

# Try AjaxPro now with the established session
soup = bs4.BeautifulSoup(resp3.text, 'html.parser')
handler = None
for script in soup.find_all('script'):
    src = script.get('src') or ''
    if 'ajaxpro/diel_diel_lis,' in src:
        handler = src.split('?')[0]
        break
handler_url = urljoin('https://www.valadares.mg.gov.br', handler)
print(f'Handler: {handler_url}')

BRT = timezone(timedelta(hours=-3))
dt_start = datetime(2026, 7, 24, 0, 0, 0, tzinfo=BRT)
dt_end = datetime(2026, 7, 24, 23, 59, 59, tzinfo=BRT)

def to_ticks(dt):
    epoch = datetime(1, 1, 1, tzinfo=timezone.utc)
    return int((dt - epoch).total_seconds() * 10000000)

payload = {"params": [0, 1, 50,
    {"__type": "Date", "ticks": to_ticks(dt_start)},
    {"__type": "Date", "ticks": to_ticks(dt_end)},
    "", -1.0, False]}

headers = {
    'X-AjaxPro-Method': 'GetDiario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}

ajax_resp = s.post(handler_url, data=json.dumps(payload), headers=headers, timeout=30)
print(f'\nAjaxPro status: {ajax_resp.status_code}')
print(f'Response: {ajax_resp.text[:500]}')
