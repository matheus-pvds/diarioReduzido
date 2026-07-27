import requests, bs4, re
from urllib.parse import urljoin

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# Check the main diario index page 
resp = s.get('https://www.valadares.mg.gov.br/diario-eletronico', timeout=30)
soup = bs4.BeautifulSoup(resp.text, 'html.parser')

# Find all links
for link in soup.find_all('a'):
    href = link.get('href', '')
    text = link.get_text(strip=True)
    if 'caderno' in href or 'diario' in href or 'arquivo' in href:
        print(f'{text} -> {href}')

# Find the "listagem" div or similar
for div in soup.find_all(['div', 'ul', 'table']):
    id_ = div.get('id', '')
    cls = ' '.join(div.get('class', []))
    if 'list' in id_.lower() or 'list' in cls.lower() or 'result' in id_.lower() or 'result' in cls.lower():
        print(f'\nContainer: id={id_} class={cls}')
        print(f'Content: {str(div)[:500]}')
