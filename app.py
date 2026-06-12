from flask import Flask, render_template, jsonify
from processor import GeminiClient, post_to_blog
import os
import json
import requests
import bs4
import time
import threading
from datetime import datetime

app = Flask(__name__)

POSTS_FILE = os.path.join(os.path.dirname(__file__), 'posts.json')
LAST_PROCESSED_FILE = os.path.join(os.path.dirname(__file__), 'last_pdf.txt')

def fetch_daily_diary():
    """
    Logic ported from main.py to fetch the latest municipal gazette.
    """
    url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
    try:
        response = requests.get(url, timeout=30)
        soup = bs4.BeautifulSoup(response.text, "html.parser")
        # Use CSS selector to match multiple classes correctly
        botao_pdf = soup.select_one('a.btn-primary.arquivo-pdf')
        print(f"Botão encontrado: {botao_pdf}")
        
        if botao_pdf and botao_pdf.get('href'):
            # Resolve relative link to the root domain
            from urllib.parse import urljoin
            link = urljoin('https://www.valadares.mg.gov.br', botao_pdf['href'])
        else:
            link = None
            
        print(f"Link do PDF: {link}")
        return link
    except Exception as e:
        print(f"Erro ao buscar diário: {e}")
        return None

def background_scheduler():
    """
    Background task to check for new PDFs and update the blog.
    Runs hourly, but prioritizes checks after 09:00 AM.
    """
    print("Iniciando agendador em segundo plano...")
    # Realiza uma verificação imediata ao iniciar
    primeira_execucao = True
    
    while True:
        if not primeira_execucao:
            time.sleep(3600) # Espera uma hora nas rodadas seguintes
        primeira_execucao = False
        
        now = datetime.now()
        
        # Load last processed link
        last_link = ""
        if os.path.exists(LAST_PROCESSED_FILE):
            with open(LAST_PROCESSED_FILE, 'r') as f:
                last_link = f.read().strip()

        # Check if it's past 09:00 AM
        if now.hour >= 9:
            print(f"[{now.strftime('%H:%M:%S')}] Verificando novo diário...")
            current_link = fetch_daily_diary()
            
            if current_link and current_link != last_link:
                print(f"Novo diário encontrado: {current_link}")
                
                # Download PDF
                pdf_path = os.path.join(os.path.dirname(__file__), 'diary.pdf')
                try:
                    pdf_content = requests.get(current_link).content
                    with open(pdf_path, 'wb') as f:
                        f.write(pdf_content)
                    
                    # Process with Gemini
                    gemini = GeminiClient()
                    summary, model = gemini.process_pdf(pdf_path)
                    
                    # Post to blog
                    post_to_blog(f"Resumo Diário - {now.strftime('%d/%m/%Y')}", summary, model, current_link)
                    
                    # Update last processed link
                    with open(LAST_PROCESSED_FILE, 'w') as f:
                        f.write(current_link)
                    
                    print("Blog atualizado com sucesso!")
                except Exception as e:
                    print(f"Erro no processamento automático: {e}")
            else:
                print("Nenhum diário novo disponível ou já processado hoje.")
        
        # Sleep for an hour before next check
        # (Could be shorter if we want to be more proactive between 09:00 and 10:00)
        time.sleep(3600)

# Start background scheduler thread
daemon = threading.Thread(target=background_scheduler, daemon=True)
daemon.start()

@app.route('/')
def index():
    posts = []
    if os.path.exists(POSTS_FILE):
        with open(POSTS_FILE, 'r', encoding='utf-8') as f:
            posts = json.load(f)
    
    # Ensure we only show the latest post if any
    latest_post = posts[0] if posts else None
    return render_template('index.html', post=latest_post)

if __name__ == '__main__':
    # Use use_reloader=False when starting background threads in the same process
    app.run(debug=True, port=5000, use_reloader=False)
