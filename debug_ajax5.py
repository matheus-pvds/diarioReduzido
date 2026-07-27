import requests, json, re, bs4
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

# AjaxPro uses ticks (100-nanosecond intervals since Jan 1, 0001)
# DateTime(2026,7,21).Ticks = 639479232000000000
# But easier: use .NET epoch
# .NET ticks: Jan 1, 0001
# Unix epoch: Jan 1, 1970 = 621355968000000000 ticks
# ticks = unix_ms * 10000 + 621355968000000000

def to_ticks(dt):
    epoch = datetime(1, 1, 1, tzinfo=timezone.utc)
    delta = dt - epoch
    return int(delta.total_seconds() * 10000000)

dt_start = datetime(2026, 7, 21, 0, 0, 0, tzinfo=BRT)
dt_end = datetime(2026, 7, 21, 23, 59, 59, tzinfo=BRT)
start_ticks = to_ticks(dt_start)
end_ticks = to_ticks(dt_end)
print(f'Start ticks: {start_ticks}')
print(f'End ticks: {end_ticks}')

# AjaxPro date format: {"__type":"Date","ticks":xxxx}
payloads = [
    # Try with null dates (no filter dates)
    {
        'Page': 0, 'cdCaderno': 1, 'pagerLength': 50,
        'dtSolicitadaInicio': None,
        'dtSolicitadaFim': None,
        'strPalavraChave': '', 'nuEdicao': -1.0, 'chkPesquisaExata': False,
    },
    # Try with AjaxPro date objects
    {
        'Page': 0, 'cdCaderno': 1, 'pagerLength': 50,
        'dtSolicitadaInicio': {'__type': 'Date', 'ticks': start_ticks},
        'dtSolicitadaFim': {'__type': 'Date', 'ticks': end_ticks},
        'strPalavraChave': '', 'nuEdicao': -1.0, 'chkPesquisaExata': False,
    },
    # Try string dates dd/MM/yyyy
    {
        'Page': 0, 'cdCaderno': 1, 'pagerLength': 50,
        'dtSolicitadaInicio': '21/07/2026',
        'dtSolicitadaFim': '21/07/2026',
        'strPalavraChave': '', 'nuEdicao': -1.0, 'chkPesquisaExata': False,
    },
]

headers = {
    'X-AjaxPro-Method': 'GetDiario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}

for i, payload in enumerate(payloads):
    body = json.dumps(payload)
    ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
    raw = ajax_resp.text[:500]
    print(f'\nPayload {i}: status={ajax_resp.status_code}')
    # Check for error
    if 'r.error' in raw:
        print(f'  ERROR: {raw[:300]}')
    elif 'Rows' in raw:
        print(f'  ROWS FOUND! Response: {raw[:300]}')
    else:
        print(f'  Response: {raw[:300]}')
