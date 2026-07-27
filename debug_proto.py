import requests, re

s = requests.Session()

# Get the prototype script which contains AjaxPro core
resp = s.get('https://www.valadares.mg.gov.br/ajaxpro/prototype.ashx', timeout=30)
txt = resp.text

# Find AjaxPro class definition
for m in re.finditer(r'AjaxPro\s*=\s*\{[^}]*\}', txt):
    print(f'AjaxPro obj: {m.group()[:500]}')

# Look for the serialize method
for m in re.finditer(r'serialize[^;]{0,800}', txt):
    print(f'Serialize: {m.group()[:500]}\n---')

# Look for how the JSON request body is constructed
for m in re.finditer(r'request\.body|send\(|postBody|params|method\s*:', txt, re.IGNORECASE):
    start = max(0, m.start()-200)
    end = min(len(txt), m.end()+300)
    print(f'Request body: ...{txt[start:end]}...\n---')
