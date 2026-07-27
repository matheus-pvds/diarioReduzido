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

def to_ticks(dt):
    epoch = datetime(1, 1, 1, tzinfo=timezone.utc)
    return int((dt - epoch).total_seconds() * 10000000)

# Try different dates to see if it's a data issue
test_dates = [
    date(2026, 7, 24),  # recent weekday
    date(2026, 7, 27),  # today (Monday)
    date(2026, 7, 21),  # the date user tried
    date(2026, 7, 20),  # Monday
    date(2026, 7, 17),  # Friday
]

headers = {
    'X-AjaxPro-Method': 'GetDiario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}

for d in test_dates:
    dt_start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=BRT)
    dt_end = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=BRT)
    start_ticks = to_ticks(dt_start)
    end_ticks = to_ticks(dt_end)
    
    payload = {
        "params": [
            0, 1, 50,
            {"__type": "Date", "ticks": start_ticks},
            {"__type": "Date", "ticks": end_ticks},
            "", -1.0, False
        ]
    }
    
    body = json.dumps(payload)
    ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
    raw = ajax_resp.text[:800]
    
    if 'Rows' in raw:
        print(f'{d}: SUCCESS - has results!')
        # Extract JSON
        text = raw.strip().lstrip(';').lstrip('/').strip()
        if text.startswith('null'):
            text = text[4:].lstrip(';').strip()
        import json as j
        data = j.loads(text)
        rows = data.get('value', {}).get('Rows', [])
        print(f'  Rows: {len(rows)}')
        for r in rows[:1]:
            print(f'  Keys: {list(r.keys())}')
            print(f'  URL: {r.get("URLABRIRARQUIVO", "")}')
            print(f'  NMARQUIVO: {r.get("NMARQUIVO", "")}')
            print(f'  NMEXTENSAOARQUIVO: {r.get("NMEXTENSAOARQUIVO", "")}')
    elif 'r.error' in raw:
        # Extract error message
        import re as re2
        m = re2.search(r'"Message":"([^"]+)"', raw)
        err = m.group(1) if m else raw[:100]
        print(f'{d}: ERROR - {err}')
    else:
        print(f'{d}: OTHER - {raw[:100]}')
