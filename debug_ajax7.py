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

dt_start = datetime(2026, 7, 21, 0, 0, 0, tzinfo=BRT)
dt_end = datetime(2026, 7, 21, 23, 59, 59, tzinfo=BRT)
start_ticks = to_ticks(dt_start)
end_ticks = to_ticks(dt_end)

# Now pass actual Date objects instead of null
payload = {
    "params": [
        0,                              # Page
        1,                              # cdCaderno
        50,                             # pagerLength
        {"__type": "Date", "ticks": start_ticks},  # dtSolicitadaInicio
        {"__type": "Date", "ticks": end_ticks},    # dtSolicitadaFim
        "",                              # strPalavraChave
        -1.0,                           # nuEdicao
        False                           # chkPesquisaExata
    ]
}

body = json.dumps(payload)
headers = {
    'X-AjaxPro-Method': 'GetDiario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}
print(f'Sending: {body[:200]}...')
ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
print(f'Status: {ajax_resp.status_code}')
print(f'Response:\n{ajax_resp.text[:2000]}')
