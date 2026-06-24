from flask import Flask, render_template, jsonify, request, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from processor import GeminiClient
import os
import requests
import bs4
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
from werkzeug.security import generate_password_hash, check_password_hash
from forms import LoginForm

app = Flask(__name__)
# Configuração de chave secreta para sessão e proteção CSRF
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'diario-reduzido-secret-key-987654')
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

# Database Model for Users
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

with app.app_context():
    db.create_all()
    # Cria o usuário padrão para login inicial se não houver nenhum
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
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

    post_id = request.args.get('id', type=int)
    if post_id:
        post = Post.query.get(post_id)
    else:
        post = Post.query.order_by(Post.id.desc()).first()

    previous_posts = []
    if session.get('logged_in'):
        # Get all posts ordered by date descending
        previous_posts = Post.query.order_by(Post.id.desc()).all()

    form = LoginForm()
    return render_template('index.html', post=post, previous_posts=previous_posts, form=form)

@app.route('/login', methods=['POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            session['logged_in'] = True
            session['username'] = user.username
            flash('Login efetuado com sucesso!', 'success')
        else:
            flash('Usuário ou senha inválidos.', 'danger')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field}: {error}", 'danger')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=False, port=5000)
