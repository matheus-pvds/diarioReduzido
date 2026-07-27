import requests, re

url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
resp = s.get(url, timeout=30)

# Find all scripts
for m in re.finditer(r'<script[^>]*>(.*?)</script>', resp.text, re.DOTALL):
    text = m.group(1)
    if '.GetDiario' in text or 'GetDiario(' in text:
        print('=== GetDiario call found ===')
        print(text)
        print('=== end ===')
