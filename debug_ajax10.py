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

start_ms = int(dt_start.timestamp() * 1000)
end_ms = int(dt_end.timestamp() * 1000)

# Try: chkPesquisaExata as int 0 instead of bool false
# Try: different cdCaderno values
# Try: string values for all params
tests = [
    # chkPesquisaExata as 0 (int)
    {"params": [0, 1, 50, {"__type": "Date", "ticks": to_ticks(dt_start)},
        {"__type": "Date", "ticks": to_ticks(dt_end)}, "", -1.0, 0]},
    # chkPesquisaExata as "false" (string)
    {"params": [0, 1, 50, {"__type": "Date", "ticks": to_ticks(dt_start)},
        {"__type": "Date", "ticks": to_ticks(dt_end)}, "", -1.0, "false"]},
    # nuEdicao as int not float
    {"params": [0, 1, 50, {"__type": "Date", "ticks": to_ticks(dt_start)},
        {"__type": "Date", "ticks": to_ticks(dt_end)}, "", -1, False]},
    # All params as strings
    {"params": ["0", "1", "50", {"__type": "Date", "ticks": to_ticks(dt_start)},
        {"__type": "Date", "ticks": to_ticks(dt_end)}, "", "-1.0", "false"]},
    # Without params wrapper - just flat object
    {"Page": 0, "cdCaderno": 1, "pagerLength": 50, "chkPesquisaExata": "false",
     "dtSolicitadaInicio": f"/Date({start_ms})/",
     "dtSolicitadaFim": f"/Date({end_ms})/",
     "strPalavraChave": "", "nuEdicao": -1.0},
    # cdCaderno as -1 (todos)
    {"params": [0, -1, 50, {"__type": "Date", "ticks": to_ticks(dt_start)},
        {"__type": "Date", "ticks": to_ticks(dt_end)}, "", -1.0, False]},
    # cdCaderno as string
    {"params": [0, "1", 50, {"__type": "Date", "ticks": to_ticks(dt_start)},
        {"__type": "Date", "ticks": to_ticks(dt_end)}, "", -1.0, False]},
]

headers = {
    'X-AjaxPro-Method': 'GetDiario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}

for i, payload in enumerate(tests):
    body = json.dumps(payload)
    ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
    raw = ajax_resp.text[:500]
    status = 'OK' if 'Rows' in raw else ('ERR' if 'r.error' in raw else '???')
    print(f'Test {i}: {status}')
    if 'Rows' in raw:
        text = raw.strip().lstrip(';').lstrip('/').strip()
        if text.startswith('null'):
            text = text[4:].lstrip(';').strip()
        data = json.loads(text)
        rows = data.get('value', {}).get('Rows', [])
        print(f'  Rows: {len(rows)}')
        if rows:
            print(f'  First row: {json.dumps(rows[0], indent=2)[:500]}')
    elif 'r.error' in raw:
        import re
        m = re.search(r'"Message":"([^"]+)"', raw)
        print(f'  Error: {m.group(1) if m else raw[:200]}')
    else:
        print(f'  Raw: {raw[:200]}')
