import os
import sqlite3
import sys
import time

REPO = r'C:\Users\SMDCTI\Desktop\PROJECTS\diarioReduzido'
sys.path.insert(0, REPO)

from app import _get_diario_batch, _parse_datatable_js_full

DB_PATH = os.path.join(REPO, 'diarios_local.db')
DIARIO_BASE = 'https://www.valadares.mg.gov.br'

conn = sqlite3.connect(DB_PATH)
conn.execute('''
    CREATE TABLE IF NOT EXISTS diario_downloads (
        num_diario   INTEGER PRIMARY KEY,
        guid         TEXT NOT NULL,
        dt_publicacao TEXT,
        url          TEXT NOT NULL
    )
''')

page = 0
size = 10
total = None
done = 0
start = time.time()

while True:
    raw = _get_diario_batch(page, size)
    if not raw or raw.startswith('null'):
        print(f'Fim em page={page} (resposta vazia).')
        break
    _, rows, page_total = _parse_datatable_js_full(raw)
    if total is None:
        total = page_total or 0
    if not rows:
        print(f'Fim em page={page} (sem linhas).')
        break
    for row in rows:
        num = int(row.get('NUEDICAO') or 0)
        guid = row.get('NMARQUIVO') or ''
        if not num or not guid:
            continue
        pub = row.get('DTPUBLICACAO')
        pub_date = pub.date().isoformat() if hasattr(pub, 'date') else (pub or '')
        url = f'{DIARIO_BASE}/abrir_arquivo.aspx?cdLocal=12&arquivo={guid}.pdf'
        conn.execute(
            'INSERT OR REPLACE INTO diario_downloads (num_diario, guid, dt_publicacao, url) VALUES (?,?,?,?)',
            (num, guid, pub_date, url),
        )
        done += 1
    conn.commit()
    page += 1
    if total and page * size >= total:
        print(f'Paginação completa: {total} edições.')
        break
    if page % 25 == 0:
        elapsed = time.time() - start
        print(f'page {page:4d}/{ (total or 0) // size + 1 } | {done} resolvidos | {elapsed:.0f}s', flush=True)
    time.sleep(0.25)

elapsed = time.time() - start
conn.commit()
print(f'Resolvidos: {done} diários em {elapsed:.0f}s.')
conn.close()
