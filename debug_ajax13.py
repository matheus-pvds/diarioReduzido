import requests, json, bs4, re
from urllib.parse import urljoin
from datetime import date, datetime, timezone, timedelta

url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
resp = s.get(url, timeout=30)

# Get all script sources to check AjaxPro version
soup = bs4.BeautifulSoup(resp.text, 'html.parser')

# Get the converter script to understand its JSON format
converter_url = None
for script in soup.find_all('script'):
    src = script.get('src') or ''
    if 'converter.ashx' in src:
        converter_url = urljoin('https://www.valadares.mg.gov.br', src)
        break

if converter_url:
    converter_resp = s.get(converter_url, timeout=30)
    converter_text = converter_resp.text
    print(f'Converter script length: {len(converter_text)}')
    # Look for date serialization format
    for m in re.finditer(r'Date[^}]{0,200}', converter_text):
        print(f'Date related: {m.group()[:200]}')
        print('---')
else:
    print('Converter not found')

# Also try the most basic possible AjaxPro call
# Find the handler
handler = None
for script in soup.find_all('script'):
    src = script.get('src') or ''
    if 'ajaxpro/diel_diel_lis,' in src:
        handler = src.split('?')[0]
        break
handler_url = urljoin('https://www.valadares.mg.gov.br', handler)
print(f'\nHandler: {handler_url}')

# Try GetUrlAssinaturaVisualizacao which is a simpler method (takes one int param)
payload = {"params": [1]}
body = json.dumps(payload)
headers = {
    'X-AjaxPro-Method': 'GetUrlAssinaturaVisualizacao',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}
ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
print(f'\nGetUrlAssinaturaVisualizacao: {ajax_resp.text[:300]}')
