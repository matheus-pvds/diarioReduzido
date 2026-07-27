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

# Try GetCalendario first to find dates with data
today = datetime(2026, 7, 27, tzinfo=BRT)
cal_payload = {
    "params": [
        {"__type": "Date", "ticks": to_ticks(today)},
        1,      # cdCaderno
        "",     # strPalavraChave
        None,   # dtInicioFiltro
        None,   # dtFimFiltro
        -1.0,   # nuEdicao
    ]
}

headers = {
    'X-AjaxPro-Method': 'GetCalendario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}

body = json.dumps(cal_payload)
ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
print(f'GetCalendario status: {ajax_resp.status_code}')
print(f'Response: {ajax_resp.text[:1000]}')
