import requests, json, re, bs4
from urllib.parse import urljoin
from datetime import date, datetime, timezone, timedelta

url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
resp = s.get(url, timeout=30)

# Use extract_ajaxpro_handler logic
soup = bs4.BeautifulSoup(resp.text, 'html.parser')
handler = None
for script in soup.find_all('script'):
    src = script.get('src') or ''
    if 'ajaxpro/diel_diel_lis,' in src:
        handler = src.split('?')[0]
        break
print(f'Handler: {handler}')
handler_url = urljoin('https://www.valadares.mg.gov.br', handler)
print(f'Handler URL: {handler_url}')

dt_start = datetime.combine(date(2026, 7, 21), datetime.min.time(), tzinfo=timezone(timedelta(hours=-3)))
dt_end = datetime.combine(date(2026, 7, 21), datetime.max.time(), tzinfo=timezone(timedelta(hours=-3)))
start_ms = int(dt_start.timestamp() * 1000)
end_ms = int(dt_end.timestamp() * 1000)

# test payload
payload = {
    'Page': 0, 'cdCaderno': 1, 'pagerLength': 50,
    'dtSolicitadaInicio': f'/Date({start_ms})/',
    'dtSolicitadaFim': f'/Date({end_ms})/',
    'strPalavraChave': '', 'nuEdicao': -1, 'chkPesquisaExata': False,
}
body = json.dumps(payload)
headers = {
    'X-AjaxPro-Method': 'GetDiario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}
ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
print(f'Status: {ajax_resp.status_code}')
print(f'Full response:\n{ajax_resp.text[:2000]}')
