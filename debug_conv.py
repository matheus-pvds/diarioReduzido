import requests, re

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# Get converter
resp = s.get('https://www.valadares.mg.gov.br/ajaxpro/converter.ashx', timeout=30)
text = resp.text

# Search for the key method that converts JSON values to .NET types
# Look for "Date" or "DateTime" or "ticks" 
lines = text.split('\n')
for i, line in enumerate(lines):
    if 'Date' in line and ('value' in line or 'convert' in line or 'deserial' in line):
        print(f'Line {i}: {line.strip()[:300]}')
