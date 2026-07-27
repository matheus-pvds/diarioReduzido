import requests, re

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

resp = s.get('https://www.valadares.mg.gov.br/ajaxpro/converter.ashx', timeout=30)
txt = resp.text

# Find the toServerString method - this is the KEY function that serializes
# JavaScript values to the wire format that the server understands
# Look for "toServerString" or the main serialize function
for m in re.finditer(r'[a-zA-Z0-9_]+\s*[=:]\s*function\s*\([^)]*\)[^{]*\{[^}]*\}', txt):
    fn = m.group()
    if 'convert' in fn.lower() or 'date' in fn.lower() or 'string' in fn.lower():
        print(f'{fn[:300]}\n---')

# Also look for the AjaxPro.serialize function
for m in re.finditer(r'AjaxPro[^;]{0,500}', txt):
    print(f'{m.group()[:300]}\n---')
