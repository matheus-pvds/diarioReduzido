from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from processor import GeminiClient
import os
import requests
import bs4
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

app = Flask(__name__)
# Definindo GMT-3 de forma absoluta para garantir compatibilidade em ambientes serverless
BRT = timezone(timedelta(hours=-3))

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('POSTGRES_URL', 'sqlite:///local.db').replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Model (Removida a duplicidade de colunas)
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(BRT))
    model = db.Column(db.String(100))
    pdf_link = db.Column(db.String(500))

# Database Model for Application Configuration (Removida a duplicidade de colunas)
class AppConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(BRT))

with app.app_context():
    db.create_all()
    if not AppConfig.query.filter_by(key='last_checked_timestamp').first():
        db.session.add(AppConfig(key='last_checked_timestamp', value=datetime(1970, 1, 1, tzinfo=BRT).isoformat()))
        db.session.commit()

def fetch_daily_diary():
    url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
    try:
        response = requests.get(url, timeout=30)
        soup = bs4.BeautifulSoup(response.text, "html.parser")
        botao_pdf = soup.select_one('a.btn-primary.arquivo-pdf')
        print(f"Botão encontrado: {botao_pdf}")
        
        if botao_pdf and botao_pdf.get('href'):
            link = urljoin('https://www.valadares.mg.gov.br', botao_pdf['href'])
        else:
            link = None
            
        print(f"Link do PDF: {link}")
        return link
    except Exception as e:
        print(f"Erro ao buscar diário: {e}")
        return None

def perform_update_logic():
    now = datetime.now(BRT)
    print(f"[{now.strftime('%H:%M:%S')}] Iniciando verificação e processamento de diário...")
    
    last_post = Post.query.order_by(Post.id.desc()).first()
    last_link = last_post.pdf_link if last_post else ""

    print(f"[{now.strftime('%H:%M:%S')}] Verificando novo diário...")
    current_link = fetch_daily_diary()
    
    if current_link and current_link != last_link:
        print(f"Novo diário encontrado: {current_link}")
        
        try:
            pdf_content = requests.get(current_link, timeout=60).content
            
            # Instancia o cliente corrigido que faz a chamada Inline
            gemini = GeminiClient()
            summary, model_name = gemini.process_pdf(pdf_content)
            
            new_post = Post(
                title=f"Resumo Diário - {now.strftime('%d/%m/%Y %H:%M')}",
                content=summary,
                model=model_name,
                pdf_link=current_link
            )
            db.session.add(new_post)
            db.session.commit()
            
            return {"status": "success", "message": "Blog atualizado!"}
        except Exception as e:
            print(f"Erro durante o processamento: {e}")
            db.session.rollback()
            return {"status": "error", "message": str(e)}
    else:
        print("Nenhum diário novo disponível ou link inalterado.")
        return {"status": "no_change", "message": "Nenhum diário novo disponível."}

@app.route('/')
def index():
    now = datetime.now(BRT)
    last_check = AppConfig.query.filter_by(key='last_checked_timestamp').first()
    
    if last_check:
        last_time = datetime.fromisoformat(last_check.value)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=BRT)
    else:
        last_time = datetime(1970, 1, 1, tzinfo=BRT)

    if (now - last_time) > timedelta(hours=1):
        print(f"[{now.strftime('%H:%M:%S')}] Serverless check: Hora de verificar atualizações...")
        perform_update_logic()
        
        if last_check:
            last_check.value = now.isoformat()
            db.session.commit()

    post = Post.query.order_by(Post.id.desc()).first()
    return render_template('index.html', post=post)

if __name__ == '__main__':
    app.run(debug=False, port=5000)
