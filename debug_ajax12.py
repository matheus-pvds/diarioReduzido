import requests, json, bs4
from urllib.parse import urljoin
from datetime import date, datetime, timezone, timedelta

url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
resp = s.get(url, timeout=30)

print(f'Status: {resp.status_code}')
print(f'Cookies:')
for cookie in resp.cookies:
    print(f'  {cookie.name}={cookie.value}')

# Also look for Set-Cookie headers from response
for cookie in resp.cookies:
    print(f'  Cookie: {cookie.name}={cookie.value}')

# Also check response headers
print(f'\nResponse headers:')
for h, v in resp.headers.items():
    if 'cookie' in h.lower() or 'set-' in h.lower():
        print(f'  {h}: {v}')

soup = bs4.BeautifulSoup(resp.text, 'html.parser')
handler = None
for script in soup.find_all('script'):
    src = script.get('src') or ''
    if 'ajaxpro/diel_diel_lis,' in src:
        handler = src.split('?')[0]
        break
handler_url = urljoin('https://www.valadares.mg.gov.br', handler)
print(f'\nHandler: {handler_url}')

BRT = timezone(timedelta(hours=-3))
dt_start = datetime(2026, 7, 24, 0, 0, 0, tzinfo=BRT)
dt_end = datetime(2026, 7, 24, 23, 59, 59, tzinfo=BRT)

def to_ticks(dt):
    epoch = datetime(1, 1, 1, tzinfo=timezone.utc)
    return int((dt - epoch).total_seconds() * 10000000)

# Try with method param in URL
# Also try with only the handler URL (no extra path)
payload = {"params": [0, 1, 50, 
    {"__type": "Date", "ticks": to_ticks(dt_start)},
    {"__type": "Date", "ticks": to_ticks(dt_end)},
    "", -1.0, False]}

headers = {
    'X-AjaxPro-Method': 'GetDiario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}

body = json.dumps(payload)
ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
print(f'\nAjaxPro status: {ajax_resp.status_code}')
raw = ajax_resp.text[:1000]
print(f'Response: {raw}')

# After this session cookie, maybe need __VIEWSTATE or EVENTVALIDATION?
# Let me check the page for these
import re
vs = re.search(r'__VIEWSTATE[^>]+value="([^"]+)"', resp.text)
ev = re.search(r'__EVENTVALIDATION[^>]+value="([^"]+)"', resp.text)
print(f'\n__VIEWSTATE: {"found" if vs else "missing"}')
print(f'__EVENTVALIDATION: {"found" if ev else "missing"}')
