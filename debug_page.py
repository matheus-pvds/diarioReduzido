import requests, re

url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
resp = s.get(url, timeout=30)

print(f'Status: {resp.status_code}')
print(f'Content length: {len(resp.text)}')

# Find ALL script tags with ajaxpro
for m in re.finditer(r'src="([^"]*ajaxpro[^"]*)"', resp.text):
    print(f'AjaxPro script: {m.group(1)}')

# Look for AjaxPro methods in inline scripts
for m in re.finditer(r'<script[^>]*type="text/javascript"[^>]*>(.*?)</script>', resp.text, re.DOTALL | re.IGNORECASE):
    script = m.group(1)
    if 'ajaxpro' in script.lower() or 'GetDiario' in script:
        print(f'\nInline script with ajaxpro/GetDiario:')
        print(script[:2000])
        break

# Also search for prototype.ashx in scripts
for m in re.finditer(r'src="([^"]*prototype[^"]*)"', resp.text):
    print(f'Prototype script: {m.group(1)}')
