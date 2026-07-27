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
dt_start = datetime(2026, 7, 21, 0, 0, 0, tzinfo=BRT)
dt_end = datetime(2026, 7, 21, 23, 59, 59, tzinfo=BRT)

# Try positional array format (AjaxPro protocol)
payloads = [
    # Option 1: Positional params array 
    json.dumps({"params": [0, 1, 50, None, None, '', -1.0, False]}),
    # Option 2: Simple array
    json.dumps([0, 1, 50, None, None, '', -1.0, False]),
    # Option 3: Object with constructor format
    json.dumps({"Page": 0, "cdCaderno": 1, "pagerLength": 50,
                "dtSolicitadaInicio": None, "dtSolicitadaFim": None,
                "strPalavraChave": '', "nuEdicao": -1.0, "chkPesquisaExata": False}),
    # Option 4: Without cdCaderno (maybe it's not a param but hardcoded server-side)
    json.dumps({"params": [0, 50, None, None, '', -1.0, False]}),
    # Option 5: pagerLength as string
    json.dumps({"params": [0, 1, '50', None, None, '', -1.0, False]}),
    # Option 6: With date strings
    json.dumps({"params": [0, 1, 50, '21/07/2026', '21/07/2026', '', -1.0, False]}),
]

headers = {
    'X-AjaxPro-Method': 'GetDiario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}

for i, body in enumerate(payloads):
    ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
    raw = ajax_resp.text[:500]
    print(f'\nPayload {i}: body={body[:100]}')
    print(f'  Status: {ajax_resp.status_code}')
    if 'Rows' in raw:
        print(f'  SUCCESS! {raw[:400]}')
    elif 'r.error' in raw:
        print(f'  ERROR: {raw[:300]}')
    else:
        print(f'  Res: {raw[:300]}')
