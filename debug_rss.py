import requests, bs4, re
from urllib.parse import urljoin

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# Check several alternative endpoints
base = 'https://www.valadares.mg.gov.br'
paths = [
    '/rss/diario-oficial',
    '/rss',
    '/diario-eletronico/rss',
    '/diario-eletronico/atom',
    '/diario-eletronico/feed',
    '/diario-eletronico',
    '/diario-eletronico/caderno/governador-valadares-mg/1/2026/7/21',
    '/diario-eletronico/caderno/governador-valadares-mg/1?data=21/07/2026',
    '/diario-eletronico/caderno/governador-valadares-mg/1?dt=21/07/2026',
]

for path in paths:
    try:
        url = urljoin(base, path)
        r = s.get(url, timeout=15)
        print(f'{path}: {r.status_code} ({len(r.text)} bytes)')
        # Check content type
        ct = r.headers.get('Content-Type', '')
        if 'xml' in ct or 'rss' in ct:
            print(f'  Content-Type: {ct}')
            print(f'  First 300 chars: {r.text[:300]}')
    except Exception as e:
        print(f'{path}: ERROR {e}')
