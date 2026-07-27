import requests, bs4, re
from urllib.parse import urljoin

url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
resp = s.get(url, timeout=30)

soup = bs4.BeautifulSoup(resp.text, 'html.parser')

# Look for any embedded data in the page that might contain PDF URLs
# Search for patterns like .pdf or abrir_arquivo
for link in soup.find_all('a'):
    href = link.get('href', '')
    if 'abrir_arquivo' in href and 'cdLocal=12' in href:
        print(f'PDF link: {href}')

# Also look for the calendar div content
cal = soup.find(id='calendario')
if cal:
    print(f'\nCalendario content: {str(cal)[:1000]}')

# Look for any archive URL patterns
for link in soup.find_all('a'):
    href = link.get('href', '')
    if 'arquivo' in href.lower() or 'diario' in href.lower() or 'edicao' in href.lower():
        text = link.get_text(strip=True)
        print(f'Link: {text} -> {href}')

# Check if there's a different URL pattern for old editions
print('\n\n=== Try alternative URL patterns ===')
# Maybe the site has a year-based archive
patterns = [
    '/diario-eletronico/caderno/governador-valadares-mg/1/2026',
    '/diario-eletronico/caderno/governador-valadares-mg/1/2026/7',
    '/diario-eletronico/arquivo',
    '/diario-eletronico/pesquisa',
]
for p in patterns:
    test_url = urljoin('https://www.valadares.mg.gov.br', p)
    try:
        tr = s.get(test_url, timeout=10)
        print(f'{p}: {tr.status_code} ({len(tr.text)} bytes)')
        if tr.status_code == 200 and len(tr.text) > 1000:
            ts = bs4.BeautifulSoup(tr.text, 'html.parser')
            links = ts.select('a[href*="abrir_arquivo"]')
            print(f'  PDF links: {len(links)}')
    except Exception as e:
        print(f'{p}: ERROR {e}')
