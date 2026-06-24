"""
scrape_historico.py
-------------------
Scrapes all past gazette editions from the Governador Valadares diário eletronico
site via its internal AjaxPro API, registers each entry (edition number, publication
date/time, PDF link) in the local database, and stops at editions older than
January 1st of the previous calendar year.

Requires an active ASP.NET session (obtained by loading the page first).

Run from the project root:
    python scrape_historico.py
"""

import re
import json
import datetime
import requests
from bs4 import BeautifulSoup

# ── Bootstrap Flask app context so we can use the SQLAlchemy models ────────────
import os
os.environ.setdefault("GEMINI_API_KEY", "scraper-placeholder")

from app import app, db, Post

# ── Constants ──────────────────────────────────────────────────────────────────
BASE_URL    = "https://www.valadares.mg.gov.br"
CADERNO_URL = f"{BASE_URL}/diario-eletronico/caderno/governador-valadares-mg/1"
PAGE_SIZE   = 50

now         = datetime.datetime.now()
STOP_YEAR   = now.year - 1
CUTOFF_DATE = datetime.datetime(STOP_YEAR, 1, 1)

print(f"Corte: apenas edições em ou após {CUTOFF_DATE.strftime('%d/%m/%Y')}")

AJAX_HEADERS = {
    "X-AjaxPro-Method": "GetDiario",
    "Content-Type":     "text/plain; charset=utf-8",
    "Referer":          CADERNO_URL,
    "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

def discover_endpoint() -> str:
    """Scrape the main page to find the live AjaxPro endpoint URL."""
    res  = requests.get(CADERNO_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    soup = BeautifulSoup(res.text, "html.parser")
    for s in soup.find_all("script", src=True):
        if "ajaxpro/diel_diel_lis" in s["src"]:
            return BASE_URL + s["src"]
    raise RuntimeError("Endpoint AjaxPro não encontrado. Estrutura do site pode ter mudado.")

# ── Date replacement helper ────────────────────────────────────────────────────
def _repl_date(m: re.Match) -> str:
    parts  = [int(x) for x in m.group(1).split(",")]
    year   = parts[0]
    month  = parts[1] + 1   # AjaxPro sends 0-based months
    day    = parts[2]
    hour   = parts[3] if len(parts) > 3 else 0
    minute = parts[4] if len(parts) > 4 else 0
    second = parts[5] if len(parts) > 5 else 0
    ms     = parts[6] if len(parts) > 6 else 0
    dt     = datetime.datetime(year, month, day, hour, minute, second, ms * 1000)
    return f'"{dt.isoformat()}"'

# ── Fetch one page from the AjaxPro API ───────────────────────────────────────
def fetch_page(endpoint: str, page: int) -> list[dict]:
    payload = (
        f'{{"Page":{page},"cdCaderno":1,"Size":{PAGE_SIZE},'
        f'"dtDiario_menor":null,"dtDiario_maior":null,'
        f'"dsPalavraChave":"","nuEdicao":-1.0,"chkPesquisaExata":false}}'
    )
    res = requests.post(
        endpoint,
        headers=AJAX_HEADERS,
        data=payload,
        timeout=30,
    )

    text = res.text

    # Extract rows array: response is "new Ajax.Web.DataTable([cols],[[row1],[row2],...])"
    _, _, rest = text.partition(",[[")
    if not rest:
        return []
    rows_part, _, _ = rest.partition("]];")
    json_rows = "[" + re.sub(r"new Date\(([^)]+)\)", _repl_date, rows_part) + "]"

    try:
        raw_rows = json.loads(json_rows)
    except json.JSONDecodeError as exc:
        print(f"  [AVISO] Falha ao parsear JSON da página {page}: {exc}")
        return []

    rows = []
    for r in raw_rows:
        # Cols: CDDIARIOELETRONICO, NUEDICAO, DSDIARIO, CDCADERNO,
        #       DTPUBLICACAO, DTVISUALIZACAO, NMARQUIVO, NMEXTENSAOARQUIVO, ...
        cd       = int(r[0])
        edicao   = int(r[1])
        dt_pub   = datetime.datetime.fromisoformat(r[4]) if r[4] else None
        dt_vis   = datetime.datetime.fromisoformat(r[5]) if r[5] else None
        arquivo  = str(r[6])   # GUID like {AD5BE523-...}
        extensao = str(r[7])   # ".pdf"
        rows.append({
            "cd":       cd,
            "edicao":   edicao,
            "dt_pub":   dt_pub,
            "dt_vis":   dt_vis,
            "arquivo":  arquivo,
            "extensao": extensao,
        })
    return rows

# ── Build the final PDF download link ─────────────────────────────────────────
def build_pdf_link(arquivo: str, extensao: str) -> str:
    return f"{BASE_URL}/abrir_arquivo.aspx?cdLocal=12&arquivo={arquivo}{extensao}"

# ── Main scraping loop ─────────────────────────────────────────────────────────
def scrape_and_register():
    with app.app_context():
        endpoint = discover_endpoint()
        print(f"AjaxPro endpoint: {endpoint}\n")

        page          = 0
        total_new     = 0
        total_skipped = 0
        stop_reached  = False

        while not stop_reached:
            print(f"Paginando: página {page} …")
            rows = fetch_page(endpoint, page)

            if not rows:
                print("  Sem mais resultados.")
                break

            for row in rows:
                edition_date = row["dt_vis"] or row["dt_pub"]

                if edition_date and edition_date < CUTOFF_DATE:
                    print(
                        f"  Edição {row['edicao']} de "
                        f"{edition_date.strftime('%d/%m/%Y')} é anterior ao corte. Parando."
                    )
                    stop_reached = True
                    break

                pdf_link = build_pdf_link(row["arquivo"], row["extensao"])

                # Skip if already in the database
                if Post.query.filter_by(pdf_link=pdf_link).first():
                    total_skipped += 1
                    print(f"  [SKIP]  Edição {row['edicao']} já no banco.")
                    continue

                date_str = edition_date.strftime("%d/%m/%Y %H:%M") if edition_date else "Data desconhecida"
                new_post = Post(
                    title    = f"Nº {row['edicao']} – {date_str}",
                    content  = "",          # Filled on-demand when user requests summary
                    model    = "pendente",
                    pdf_link = pdf_link,
                    date     = edition_date,
                )
                db.session.add(new_post)
                total_new += 1
                print(f"  [+]  Edição {row['edicao']} em {date_str}")

            db.session.commit()
            page += 1

        print(
            f"\nConcluído. {total_new} nova(s) edição(ões) registrada(s). "
            f"{total_skipped} já existente(s) ignorada(s)."
        )

if __name__ == "__main__":
    scrape_and_register()
