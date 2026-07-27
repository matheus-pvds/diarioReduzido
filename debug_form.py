import requests, bs4, re
from urllib.parse import urljoin

url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
resp = s.get(url, timeout=30)

soup = bs4.BeautifulSoup(resp.text, 'html.parser')

# Find all form fields
form = soup.find('form', id='form1')
if form:
    print('=== Form found ===')
    for inp in form.find_all(['input', 'select', 'textarea']):
        name = inp.get('name', '')
        id_ = inp.get('id', '')
        val = inp.get('value', '')
        typ = inp.get('type', '')
        if name:
            val_display = val[:50] if val else '(empty)'
            print(f'  {name:40s} type={typ:15s} value={val_display}')

# Find the search form specifically
print('\n=== Search fields ===')
for field_id in ['txt_dtDiario_menor', 'txt_dtDiario_maior', 'txt_palChave', 'txt_nu_edicao', 'chk_pesquisaExata', 'ddl_cdCaderno', 'ddl_quantidade_registros']:
    el = soup.find(id=field_id)
    if el:
        tag = el.name
        name = el.get('name', '')
        val = el.get('value', '') if tag == 'input' else ''
        print(f'  {field_id}: tag={tag}, name={name}, value={val}')
        if tag == 'select':
            for opt in el.find_all('option'):
                sel = ' [SELECTED]' if opt.get('selected') else ''
                print(f'    option: value={opt.get("value")}{sel} text={opt.get_text(strip=True)}')
    else:
        print(f'  {field_id}: NOT FOUND')
