import requests, json, re, bs4
from urllib.parse import urljoin
from datetime import date, datetime, timezone, timedelta

url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
resp = s.get(url, timeout=30)

soup = bs4.BeautifulSoup(resp.text, 'html.parser')
handler = None
for script in soup.find_all('script'):
    src = script.get('src') or ''
    if 'ajaxpro/diel_diel_lis,' in src:
        handler = src.split('?')[0]
        break
handler_url = urljoin('https://www.valadares.mg.gov.br', handler)

BRT = timezone(timedelta(hours=-3))
dt_start = datetime(2026, 7, 24, 0, 0, 0, tzinfo=BRT)
dt_end = datetime(2026, 7, 24, 23, 59, 59, tzinfo=BRT)

def to_ticks(dt):
    epoch = datetime(1, 1, 1, tzinfo=timezone.utc)
    return int((dt - epoch).total_seconds() * 10000000)

start_ms = int(dt_start.timestamp() * 1000)
end_ms = int(dt_end.timestamp() * 1000)

# The key insight: AjaxPro sends dates as Microsoft JSON date format:
# {"__type":"Date","ticks":637500000000000000}
# But on the WIRE, AjaxPro might send a different format
# Let me try the ACTUAL format used by the AjaxPro client-side library

# Look at converter.ashx to find the date serialization format
conv = s.get('https://www.valadares.mg.gov.br/ajaxpro/converter.ashx', timeout=30)
txt = conv.text

# Search for how dates are serialized for the server
for m in re.finditer(r'toServerDate|toServerString|serializeDate|_date|_convert[^{]*{[^}]*}', txt, re.IGNORECASE):
    start = max(0, m.start()-100)
    end = min(len(txt), m.end()+200)
    snippet = txt[start:end]
    print(f'Found at {m.start()}: ...{snippet}...')
    print('---')

# Try a different format: maybe the issue is that the AjaxPro 
# expects the method parameters to be sent as a specific structure
# Let me try the exact format that the JavaScript generates

# In AjaxPro 7+, the expected format for method calls with params is:
# {"params":[p1,p2,...],"method":"GetDiario"}
# But maybe this version uses the old format:
# [p1,p2,p3]  - just an array in the body with header indicating the method

# The error "Unable to cast JavaScriptArray to JavaScriptObject" 
# when sending just an array means the server expects an object
# The DBNull error when sending {"params":[...]} means the method IS 
# found but parameters have issues

# Let me try NOT using "params" key but using direct parameter names
# This time with the dates as proper __type Date objects
payload = {
    "Page": 0,
    "cdCaderno": "1",
    "pagerLength": 50,
    "dtSolicitadaInicio": f"/Date({start_ms})/",
    "dtSolicitadaFim": f"/Date({end_ms})/",
    "strPalavraChave": "",
    "nuEdicao": -1.0,
    "chkPesquisaExata": False,
}

headers = {
    'X-AjaxPro-Method': 'GetDiario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}

body = json.dumps(payload)
print(f'Sending body: {body[:200]}...')
ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
print(f'Status: {ajax_resp.status_code}')
if 'r.error' in ajax_resp.text:
    m = re.search(r'"Message":"([^"]+)"', ajax_resp.text)
    print(f'Error: {m.group(1) if m else ajax_resp.text[:200]}')
elif 'Rows' in ajax_resp.text:
    print(f'SUCCESS! Response: {ajax_resp.text[:500]}')
else:
    print(f'Response: {ajax_resp.text[:500]}')
