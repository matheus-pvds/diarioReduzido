import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()
from app import app, search_diary_by_date, fetch_daily_diary, extract_ajaxpro_handler, _parse_datatable_js
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
    'Page': 0, 'cdCaderno': 1, 'Size': 10,
    'dtDiario_menor': {'__type': 'System.DateTime', 'Year': 2026, 'Month': 7, 'Day': 24, 'Hour': 0, 'Minute': 0, 'Second': 0, 'Millisecond': 0},
    'dtDiario_maior': {'__type': 'System.DateTime', 'Year': 2026, 'Month': 7, 'Day': 24, 'Hour': 23, 'Minute': 59, 'Second': 59, 'Millisecond': 999},
    'dsPalavraChave': '', 'nuEdicao': -1.0, 'chkPesquisaExata': False,
}
body = json.dumps(payload)
headers = {
    'X-AjaxPro-Method': 'GetDiario',
    'Content-Type': 'text/plain; charset=utf-8',
    'Referer': url,
}
ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=30)
print(f"AjaxPro status: {ajax_resp.status_code}")
raw = ajax_resp.text
print(f"Raw response (first 300): {raw[:300]}")

# Try to parse it
text = raw
if text.startswith('//') or text.startswith('/*'):
    text = text.lstrip('/;').lstrip('/*')
    if text.startswith('null'):
        text = text[4:]
text = text.strip().lstrip(';').strip()

# Parse with production code
rows = _parse_datatable_js(raw)
print(f"DataTable: {len(rows)} rows")
for r in rows[:2]:
    print(f"  Edition #{r.get('NUEDICAO')} - {r.get('DTPUBLICACAO')} - URL: {r.get('URLABRIRARQUIVO') or r.get('NMARQUIVO','') + r.get('NMEXTENSAOARQUIVO','')}")

# Test search function

# Test search function
print("\n=== Testing search_diary_by_date ===")
with app.app_context():
    result = search_diary_by_date(date(2026, 7, 24))
print(f"24/07: {result}")

# Test fetch_daily_diary
print("\n=== Testing fetch_daily_diary ===")
pdf = fetch_daily_diary()
print(f"Today's PDF: {pdf}")

# Test search function
print("\n=== Testing search_diary_by_date ===")
with app.app_context():
    result = search_diary_by_date(date(2026, 7, 24))
print(f"24/07: {result}")
