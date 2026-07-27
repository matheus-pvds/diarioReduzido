import requests, json, bs4, re
from urllib.parse import urljoin

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

# Try GetMaiorDataDiario (simpler, fewer params)
# JavaScript: diel_diel_lis.GetMaiorDataDiario(cdCaderno, dtInicioFiltro, dtFimFiltro, strPalavraChave, nuEdicao, callback)
# 5 params: int, DateTime?, DateTime?, string, float

# Try with different body formats for this simpler method
tests = [
    # Object format with named params
    json.dumps({"cdCaderno": 1, "dtInicioFiltro": None, "dtFimFiltro": None, "strPalavraChave": "", "nuEdicao": -1.0}),
    # Object with empty string for dates instead of null
    json.dumps({"cdCaderno": 1, "dtInicioFiltro": "", "dtFimFiltro": "", "strPalavraChave": "", "nuEdicao": -1.0}),
    # params array format
    json.dumps({"params": [1, None, None, "", -1.0]}),
    # Simple positional (will likely fail but let's see)
    json.dumps([1, None, None, "", -1.0]),
]

headers = {
    'X-AjaxPro-Method': 'GetMaiorDataDiario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}

for i, body in enumerate(tests):
    try:
        ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
        raw = ajax_resp.text[:600]
        print(f'\nTest {i}: {body[:100]}')
        print(f'  Status: {ajax_resp.status_code}')
        if 'r.error' in raw:
            m = re.search(r'"Message":"([^"]+)"', raw)
            print(f'  Error: {m.group(1) if m else raw[:200]}')
        else:
            print(f'  Response: {raw[:300]}')
    except Exception as e:
        print(f'  Exception: {e}')
