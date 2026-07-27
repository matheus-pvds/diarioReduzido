import requests, bs4, re

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# Get the core AjaxPro script to understand deserialization
resp = s.get('https://www.valadares.mg.gov.br/ajaxpro/core.ashx', timeout=30)
text = resp.text

# Look for the deserialize method
for m in re.finditer(r'(function|var)\s+(\w+)[^;]*?deserializ[^;]{0,300}', text, re.IGNORECASE):
    print(f'Deserialize match: {m.group()}')

# Look for how dates are parsed
for m in re.finditer(r'(Date|date|ticks)[^;]{0,200}', text):
    print(f'Date match: {m.group()[:200]}')
