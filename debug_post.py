import requests, bs4, re
from urllib.parse import urljoin
from datetime import date, datetime, timezone, timedelta

url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
resp = s.get(url, timeout=30)

soup = bs4.BeautifulSoup(resp.text, 'html.parser')

# Get VIEWSTATE and EVENTVALIDATION
def extract_field(name):
    el = soup.find('input', {'name': name})
    return el.get('value', '') if el else ''

viewstate = extract_field('__VIEWSTATE')
eventvalidation = extract_field('__EVENTVALIDATION')
viewstategen = extract_field('__VIEWSTATEGENERATOR')

print(f'__VIEWSTATE: {viewstate[:80]}...')
print(f'__VIEWSTATEGENERATOR: {viewstategen}')
print(f'__EVENTVALIDATION: {eventvalidation[:80]}...')

# Try POSTing back with a date filter
# In ASP.NET, the __doPostBack function triggers server events
# But the search is client-side via AjaxPro, not server-side PostBack
# Let me try anyway

target_date = '21/07/2026'
form_data = {
    '__VIEWSTATE': viewstate,
    '__VIEWSTATEGENERATOR': viewstategen,
    '__EVENTVALIDATION': eventvalidation,
    'txt_dtDiario_menor': target_date,
    'txt_dtDiario_maior': target_date,
    'txt_palChave': '',
    'txt_nu_edicao': '',
    'chk_pesquisaExata': 'on',
    'ddl_quantidade_registros': '5',
    'ctl00$Conteudo$btnBuscar': 'Buscar',  # maybe a search button
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Content-Type': 'application/x-www-form-urlencoded',
}

post_resp = s.post(url, data=form_data, headers=headers, timeout=30)
print(f'\nPOST status: {post_resp.status_code}')
print(f'Response length: {len(post_resp.text)}')

# Look for PDF links in the response
post_soup = bs4.BeautifulSoup(post_resp.text, 'html.parser')
pdf_links = post_soup.select('a.arquivo-pdf, a[href*="abrir_arquivo"], a.btn-primary')
print(f'\nPDF links found: {len(pdf_links)}')
for link in pdf_links[:5]:
    href = link.get('href', '')
    text = link.get_text(strip=True)
    print(f'  {text}: {href[:100]}')

# Also look for any results
listagem = post_soup.find(id='listagem')
if listagem:
    print(f'\nListagem content length: {len(listagem.get_text(strip=True))}')
    print(f'Listagem HTML: {str(listagem)[:500]}')
else:
    print('\nNo listagem div found')
