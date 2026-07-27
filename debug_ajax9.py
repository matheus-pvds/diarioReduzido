import requests, json, bs4
from urllib.parse import urljoin
from datetime import date, datetime, timezone, timedelta

url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
resp = s.get(url, timeout=30)

soup = bs4.BeautifulSoup(resp.text, 'html.parser')
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

# Try the Microsoft AJAX date format /Date(ms)/
start_ms = int(dt_start.timestamp() * 1000)
end_ms = int(dt_end.timestamp() * 1000)

# The error says DBNull -> Int32. Maybe chkPesquisaExata is interpreted 
# as a string not bool. Or maybe the C# method has nullable ints for 
# some params. Let me try various combinations.

# Let me also try: maybe the params should be passed WITHOUT the "params" wrapper
# and WITHOUT the method name, just directly as an array
# Let me also check if the method name should be in the body

tests = [
    # Direct array, no wrapper
    json.dumps([0, 1, 50, 
        {"__type": "Date", "ticks": to_ticks(dt_start)},
        {"__type": "Date", "ticks": to_ticks(dt_end)},
        "", -1.0, False]),
    # With "method" in body
    json.dumps({"method": "GetDiario", "params": [0, 1, 50,
        {"__type": "Date", "ticks": to_ticks(dt_start)},
        {"__type": "Date", "ticks": to_ticks(dt_end)},
        "", -1.0, False]}),
    # With method as underscore prefix (AjaxPro v2 style)
    json.dumps({"method": "GetDiario", "params": [0, 1, 50,
        {"__type": "Date", "ticks": to_ticks(dt_start)},
        {"__type": "Date", "ticks": to_ticks(dt_end)},
        "", -1.0, False]}),
    # Without chkPesquisaExata
    json.dumps({"params": [0, 1, 50,
        {"__type": "Date", "ticks": to_ticks(dt_start)},
        {"__type": "Date", "ticks": to_ticks(dt_end)},
        "", -1.0]}),
    # Try with /Date(ms)/ format
    json.dumps({"params": [0, 1, 50,
        f"/Date({start_ms})/",
        f"/Date({end_ms})/",
        "", -1.0, False]}),
    # Try with nuEdicao as null (no edition filter)
    json.dumps({"params": [0, 1, 50,
        {"__type": "Date", "ticks": to_ticks(dt_start)},
        {"__type": "Date", "ticks": to_ticks(dt_end)},
        "", None, False]}),
    # Try with pagerLength = 5 (the page default)
    json.dumps({"params": [0, 1, 5,
        {"__type": "Date", "ticks": to_ticks(dt_start)},
        {"__type": "Date", "ticks": to_ticks(dt_end)},
        "", -1.0, False]}),
]

headers = {
    'X-AjaxPro-Method': 'GetDiario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}

for i, body in enumerate(tests):
    ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
    raw = ajax_resp.text[:500]
    status = 'OK' if 'Rows' in raw else ('ERR' if 'r.error' in raw else '???')
    print(f'Test {i}: {status} - {raw[:150]}')
