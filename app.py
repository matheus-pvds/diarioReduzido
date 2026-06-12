from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from processor import GeminiClient
import os
import requests
import bs4
from datetime import datetime
from urllib.parse import urljoin

app = Flask(__name__)

# Database Configuration (Vercel provides POSTGRES_URL)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('POSTGRES_URL', 'sqlite:///local.db').replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Model
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    model = db.Column(db.String(100))
    pdf_link = db.Column(db.String(500))

with app.app_context():
    db.create_all()

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
            link = urljoin('https://www.valadares.mg.gov.br', botao_pdf['href'])
        else:
            link = None
            
        print(f"Link do PDF: {link}")
        return link
    except Exception as e:
        print(f"Erro ao buscar diário: {e}")
        return None

@app.route('/api/cron/update')
def update_diary_cron():
    """
    Endpoint to be triggered by Vercel Cron hourly.
    """
    # Security check for Vercel Cron (optional but recommended)
    # auth_header = request.headers.get('Authorization')
    # if auth_header != f"Bearer {os.getenv('CRON_SECRET')}":
    #     return "Unauthorized", 401

    now = datetime.now()
    
    # Get the last processed link from DB
    last_post = Post.query.order_by(Post.id.desc()).first()
    last_link = last_post.pdf_link if last_post else ""

    print(f"[{now.strftime('%H:%M:%S')}] Verificando novo diário...")
    current_link = fetch_daily_diary()
    
    if current_link and current_link != last_link:
        print(f"Novo diário encontrado: {current_link}")
        
        # Download PDF to /tmp (Vercel's only writable directory)
        pdf_path = '/tmp/diary.pdf'
        try:
            pdf_content = requests.get(current_link).content
            with open(pdf_path, 'wb') as f:
                f.write(pdf_content)
            
            # Process with Gemini
            gemini = GeminiClient()
            summary, model_name = gemini.process_pdf(pdf_path)
            
            # Save to SQL Database
            new_post = Post(
                title=f"Resumo Diário - {now.strftime('%d/%m/%Y')}",
                content=summary,
                model=model_name,
                pdf_link=current_link
            )
            db.session.add(new_post)
            db.session.commit()
            
            return jsonify({"status": "success", "message": "Blog atualizado!"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        return jsonify({"status": "no_change", "message": "Nenhum diário novo disponível."})

@app.route('/')
def index():
    # Fetch latest post from DB
    post = Post.query.order_by(Post.id.desc()).first()
    return render_template('index.html', post=post)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
