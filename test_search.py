import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()
from app import app, search_diary_by_date, fetch_daily_diary, extract_ajaxpro_handler
from datetime import date, datetime, timezone, timedelta
import requests, json
from urllib.parse import urljoin

BRT = timezone(timedelta(hours=-3))

print("=== Testing extract_ajaxpro_handler ===")
url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
resp = s.get(url, timeout=30)
handler_path = extract_ajaxpro_handler(resp.text)
handler_url = urljoin('https://www.valadares.mg.gov.br', handler_path)
print(f"Handler URL: {handler_url}")
print(f"Has cookies: {bool(s.cookies)}")

# Test direct AjaxPro call with object payload
dt_start = datetime.combine(date(2026, 7, 24), datetime.min.time(), tzinfo=BRT)
dt_end = datetime.combine(date(2026, 7, 24), datetime.max.time(), tzinfo=BRT)
start_ms = int(dt_start.timestamp() * 1000)
end_ms = int(dt_end.timestamp() * 1000)
payload = {
    'Page': 0, 'cdCaderno': 1, 'pagerLength': 50,
    'dtSolicitadaInicio': f'/Date({start_ms})/',
    'dtSolicitadaFim': f'/Date({end_ms})/',
    'strPalavraChave': '', 'nuEdicao': -1.0, 'chkPesquisaExata': False,
}
body = json.dumps(payload)
headers = {
    'X-AjaxPro-Method': 'GetDiario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}
ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
print(f"AjaxPro status: {ajax_resp.status_code}")
raw = ajax_resp.text[:800]
print(f"Raw response: {raw}")

# Try to parse it
text = raw
if text.startswith('//') or text.startswith('/*'):
    text = text.lstrip('/;').lstrip('/*')
    if text.startswith('null'):
        text = text[4:]
text = text.strip().lstrip(';').strip()
try:
    data = json.loads(text)
    if data.get('value') and data['value'].get('Rows'):
        print(f"Rows found: {len(data['value']['Rows'])}")
        for r in data['value']['Rows'][:2]:
            print(f"  Edition #{r.get('NUEDICAO')} - {r.get('DTEDICAO')} - URL: {r.get('URLABRIRARQUIVO')}")
    else:
        print(f"Response structure: {list(data.keys()) if isinstance(data, dict) else type(data)}")
except Exception as e:
    print(f"Parse error: {e}")

# Test search function
print("\n=== Testing search_diary_by_date ===")
result = search_diary_by_date(date(2026, 7, 24))
print(f"24/07: {result}")

# Test fetch_daily_diary
print("\n=== Testing fetch_daily_diary ===")
pdf = fetch_daily_diary()
print(f"Today's PDF: {pdf}")

# Test search function
print("\n=== Testing search_diary_by_date ===")
result = search_diary_by_date(date(2026, 7, 24))
print(f"24/07: {result}")

# Test fetch_daily_diary
print("\n=== Testing fetch_daily_diary ===")
pdf = fetch_daily_diary()
print(f"Today's PDF: {pdf}")
