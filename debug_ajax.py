import requests, json, re
from urllib.parse import urljoin
from datetime import date, datetime, timezone, timedelta

url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
resp = s.get(url, timeout=30)

handler = None
for m in re.finditer(r'src=["\']([^"\']*ajaxpro[^"\']*)["\']', resp.text):
    handler = m.group(1).split('?')[0]
    break
handler_url = urljoin('https://www.valadares.mg.gov.br', handler)
print(f'Handler: {handler_url}')

dt_start = datetime.combine(date(2026, 7, 24), datetime.min.time(), tzinfo=timezone(timedelta(hours=-3)))
dt_end = datetime.combine(date(2026, 7, 24), datetime.max.time(), tzinfo=timezone(timedelta(hours=-3)))
start_ms = int(dt_start.timestamp() * 1000)
end_ms = int(dt_end.timestamp() * 1000)

payload_original = {
    'Page': 0, 'cdCaderno': 1, 'pagerLength': 50,
    'dtSolicitadaInicio': f'/Date({start_ms})/',
    'dtSolicitadaFim': f'/Date({end_ms})/',
    'strPalavraChave': '', 'nuEdicao': -1, 'chkPesquisaExata': False,
}

headers = {
    'X-AjaxPro-Method': 'GetDiario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}

body = json.dumps(payload_original)
ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
print(f'Status: {ajax_resp.status_code}')
print(f'Full response:\n{ajax_resp.text[:1500]}')
