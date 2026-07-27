import requests, json, re, bs4
from urllib.parse import urljoin
from datetime import date, datetime, timezone, timedelta

url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
resp = s.get(url, timeout=30)

soup = bs4.BeautifulSoup(resp.text, 'html.parser')

# Look for JavaScript that calls AjaxPro methods
for script in soup.find_all('script'):
    text = script.string or ''
    if 'GetDiario' in text:
        print('=== Found GetDiario script ===')
        print(text[:3000])
        print('=== end ===')
        break

# Also look for the function that formats the search parameters
for script in soup.find_all('script'):
    text = script.string or ''
    if 'dtSolicitadaInicio' in text or 'nuEdicao' in text:
        print('\n=== Found search params script ===')
        print(text[:2000])
        print('=== end ===')
        break
