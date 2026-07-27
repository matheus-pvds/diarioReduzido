from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from processor import GeminiClient
from asaas import create_customer, create_payment, process_webhook
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import json, os, requests, bs4, secrets, random, smtplib
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urljoin
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())
BRT = timezone(timedelta(hours=-3))

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('POSTGRES_URL', 'sqlite:///local.db').replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('VERCEL', 'false').lower() == 'true'
db = SQLAlchemy(app)

# --- SMTP config ---
SMTP_HOST = os.getenv('SMTP_HOST', '')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASS = os.getenv('SMTP_PASS', '')
SMTP_FROM = os.getenv('SMTP_FROM', '')

def send_email(to, subject, body):
    if not SMTP_HOST:
        print(f'SMTP não configurado. Email não enviado para {to}: {subject}')
        return False
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = SMTP_FROM
        msg['To'] = to
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f'Erro ao enviar email: {e}')
        return False

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(BRT))
    model = db.Column(db.String(100))
    pdf_link = db.Column(db.String(500))

class AppConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(BRT))

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_paid = db.Column(db.Boolean, default=False)
    requests_made = db.Column(db.Integer, default=0)
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(200))
    reset_token = db.Column(db.String(200))
    reset_token_expires = db.Column(db.DateTime(timezone=True))
    favorites = db.relationship('Favorite', backref='user', lazy=True)

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(BRT))

class LoginAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, index=True)
    timestamp = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(BRT))
    success = db.Column(db.Boolean, default=False)

COLUMN_RENAMES = {
    'user': [('password_hash', 'password')],
    'post': [('body', 'content'), ('text', 'content'), ('summary', 'content'), ('headline', 'title'), ('model_used', 'model')],
    'favorite': [('post_id_old', 'post_id')],
}

def migrate_columns():
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    for table_name, model in [('user', User), ('post', Post), ('favorite', Favorite),
                               ('login_attempt', LoginAttempt), ('app_config', AppConfig)]:
        existing = {c['name'] for c in inspector.get_columns(table_name)}
        for old_name, new_name in COLUMN_RENAMES.get(table_name, []):
            if old_name in existing and new_name not in existing:
                try:
                    db.session.execute(db.text(f'ALTER TABLE "{table_name}" RENAME COLUMN "{old_name}" TO "{new_name}"'))
                    existing = {c['name'] for c in inspector.get_columns(table_name)}
                except Exception:
                    pass
            elif old_name in existing and new_name in existing:
                try:
                    db.session.execute(db.text(f'UPDATE "{table_name}" SET "{new_name}" = "{old_name}" WHERE ("{new_name}" IS NULL OR "{new_name}" = \'\')'))
                    db.session.execute(db.text(f'ALTER TABLE "{table_name}" DROP COLUMN "{old_name}"'))
                    existing = {c['name'] for c in inspector.get_columns(table_name)}
                except Exception:
                    pass
        for col in model.__table__.columns:
            if col.name not in existing:
                col_type = col.type.compile(db.engine.dialect)
                default = ''
                if hasattr(col, 'default') and col.default is not None:
                    if callable(col.default.arg):
                        default = ''
                    else:
                        default = f" DEFAULT {col.default.arg!r}" if not isinstance(col.default.arg, (list, dict)) else ''
                try:
                    db.session.execute(db.text(f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {col_type}{default}'))
                except Exception:
                    pass
    db.session.commit()

with app.app_context():
    db.create_all()
    migrate_columns()
    admin_pass = os.getenv('ADMIN_PASSWORD', 'admin')
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', email=os.getenv('ADMIN_EMAIL', 'admin@diario.app'), password=generate_password_hash(admin_pass), email_verified=True))
    if not AppConfig.query.filter_by(key='last_checked_timestamp').first():
        db.session.add(AppConfig(key='last_checked_timestamp', value=datetime(1970, 1, 1, tzinfo=BRT).isoformat()))
    if not AppConfig.query.filter_by(key='is_checking').first():
        db.session.add(AppConfig(key='is_checking', value='false'))
    db.session.commit()

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com https://www.google.com https://www.gstatic.com; style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; img-src 'self' data:; font-src 'self' https://fonts.gstatic.com; connect-src 'self'; frame-src 'self' https://www.google.com"
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    return response

@app.context_processor
def inject_security():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return dict(csrf_token=session['csrf_token'])

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    return User.query.get(session.get('user_id')) if session.get('user_id') else None

def set_checking(value):
    c = AppConfig.query.filter_by(key='is_checking').first()
    if c:
        c.value = 'true' if value else 'false'
        db.session.commit()

def is_checking():
    c = AppConfig.query.filter_by(key='is_checking').first()
    return c and c.value == 'true'

def get_client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'

def validate_csrf():
    stored = session.get('csrf_token')
    token = request.form.get('csrf_token')
    return bool(stored and token and secrets.compare_digest(stored, token))

def check_rate_limit(ip, max_attempts=5, window_minutes=15):
    cutoff = datetime.now(BRT) - timedelta(minutes=window_minutes)
    LoginAttempt.query.filter(LoginAttempt.timestamp < cutoff).delete()
    db.session.commit()
    recent = LoginAttempt.query.filter(
        LoginAttempt.ip_address == ip,
        LoginAttempt.timestamp > cutoff,
        LoginAttempt.success == False
    ).count()
    if recent >= max_attempts:
        return False
    return True

def record_attempt(ip, success):
    db.session.add(LoginAttempt(ip_address=ip, success=success))
    db.session.commit()

RECAPTCHA_SITE_KEY = os.getenv('RECAPTCHA_SITE_KEY', '')
RECAPTCHA_SECRET_KEY = os.getenv('RECAPTCHA_SECRET_KEY', '')

def generate_captcha():
    if RECAPTCHA_SITE_KEY:
        return None
    a, b = random.randint(1, 12), random.randint(1, 12)
    op = random.choice(['+', '-'])
    if op == '-':
        a, b = max(a, b), min(a, b)
    session['captcha_answer'] = str(a + b if op == '+' else a - b)
    return f"{a} {op} {b}"

def validate_captcha(answer):
    if RECAPTCHA_SECRET_KEY:
        token = request.form.get('g-recaptcha-response', '')
        if not token:
            return False
        resp = requests.post('https://www.google.com/recaptcha/api/siteverify', data={
            'secret': RECAPTCHA_SECRET_KEY, 'response': token
        }, timeout=10)
        return resp.json().get('success', False)
    stored = session.pop('captcha_answer', None)
    return bool(stored and answer and stored.strip() == answer.strip())

def parse_title(text):
    prefix = "TITULO:"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith(prefix):
            title = stripped[len(prefix):].strip()
            content = text.replace(line, '', 1).strip()
            if not title:
                title = "Edição do Diário Oficial"
            return title, content
    return "Edição do Diário Oficial", text.strip()

def fetch_daily_diary():
    url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
    try:
        response = requests.get(url, timeout=30)
        soup = bs4.BeautifulSoup(response.text, "html.parser")
        botao_pdf = soup.select_one('a.btn-primary.arquivo-pdf')
        if botao_pdf and botao_pdf.get('href'):
            return urljoin('https://www.valadares.mg.gov.br', botao_pdf['href'])
        return None
    except Exception as e:
        print(f"Erro ao buscar diário: {e}")
        return None

def perform_update_logic():
    now = datetime.now(BRT)
    print(f"[{now.strftime('%H:%M:%S')}] Verificando novo diário...")
    last_post = Post.query.order_by(Post.id.desc()).first()
    last_link = last_post.pdf_link if last_post else ""
    current_link = fetch_daily_diary()
    if current_link and current_link != last_link:
        print(f"Novo diário encontrado: {current_link}")
        try:
            pdf_content = requests.get(current_link, timeout=60).content
            gemini = GeminiClient()
            raw_text, model_name = gemini.process_pdf(pdf_content)
            title, content = parse_title(raw_text)
            db.session.add(Post(
                title=title, content=content, model=model_name, pdf_link=current_link
            ))
            db.session.commit()
            return {"status": "success", "message": "Blog atualizado!"}
        except Exception as e:
            print(f"Erro durante o processamento: {e}")
            db.session.rollback()
            return {"status": "error", "message": str(e)}
    return {"status": "no_change", "message": "Nenhum diário novo disponível."}

def search_diary_by_date(target_date):
    dt_start = datetime.combine(target_date, datetime.min.time(), tzinfo=BRT)
    dt_end = datetime.combine(target_date, datetime.max.time(), tzinfo=BRT)
    start_ms = int(dt_start.timestamp() * 1000)
    end_ms = int(dt_end.timestamp() * 1000)
    payload = {
        'Page': 0, 'cdCaderno': 1, 'pagerLength': 50,
        'dtSolicitadaInicio': f'/Date({start_ms})/',
        'dtSolicitadaFim': f'/Date({end_ms})/',
        'strPalavraChave': '', 'nuEdicao': -1.0, 'chkPesquisaExata': False,
    }
    try:
        json_str = json.dumps(payload).replace('/', '\\/')
        response = requests.post(
            'https://www.valadares.mg.gov.br/ajaxpro/diel_diel_lis.ashx/GetDiario',
            data=json_str, headers={'Content-Type': 'application/json; charset=utf-8'}, timeout=30
        )
        data = response.json()
        if data.get('value') and data['value'].get('Rows'):
            for row in data['value']['Rows']:
                pdf_url = row.get('URLABRIRARQUIVO', '') or (
                    f'https://www.valadares.mg.gov.br/abrir_arquivo.aspx?cdLocal=12&arquivo={row["NMARQUIVO"]}{row["NMEXTENSAOARQUIVO"]}'
                )
                if pdf_url:
                    return pdf_url
    except Exception as e:
        print(f"Erro ao buscar diário por data: {e}")
    return None

@app.route('/')
def index():
    user = get_current_user()
    post = Post.query.order_by(Post.id.desc()).first()
    last_check = AppConfig.query.filter_by(key='last_checked_timestamp').first()
    now = datetime.now(BRT)
    should_check = True
    if last_check:
        last_time = datetime.fromisoformat(last_check.value)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=BRT)
        should_check = (now - last_time) > timedelta(hours=1)
    fav_ids = {f.post_id for f in user.favorites} if user else set()
    return render_template('index.html', post=post, user=user, should_check=should_check, user_fav_ids=fav_ids)

@app.route('/api/should-check')
def api_should_check():
    last_check = AppConfig.query.filter_by(key='last_checked_timestamp').first()
    now = datetime.now(BRT)
    if last_check:
        last_time = datetime.fromisoformat(last_check.value)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=BRT)
        return jsonify({'should_check': (now - last_time) > timedelta(hours=1)})
    return jsonify({'should_check': True})

@app.route('/api/perform-check')
def api_perform_check():
    if is_checking():
        return jsonify({'status': 'already_checking'})
    last_check = AppConfig.query.filter_by(key='last_checked_timestamp').first()
    now = datetime.now(BRT)
    if last_check:
        last_time = datetime.fromisoformat(last_check.value)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=BRT)
        if (now - last_time) <= timedelta(hours=1):
            return jsonify({'status': 'not_needed'})
    set_checking(True)
    try:
        return jsonify(perform_update_logic())
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        set_checking(False)
        if last_check:
            last_check.value = now.isoformat()
            db.session.commit()

@app.route('/api/status')
def api_status():
    post = Post.query.order_by(Post.id.desc()).first()
    checking = is_checking()
    post_data = None
    if post and not checking:
        post_data = {
            'id': post.id, 'title': post.title,
            'date': post.date.isoformat() if post.date else None,
            'pdf_link': post.pdf_link,
        }
    return jsonify({'checking': checking, 'post': post_data})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ip = get_client_ip()
        if not check_rate_limit(ip):
            return render_template('login.html', error='Muitas tentativas. Aguarde alguns minutos.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if not validate_csrf():
            return render_template('login.html', error='Token inválido. Recarregue a página.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if not validate_captcha(request.form.get('captcha')):
            record_attempt(ip, False)
            return render_template('login.html', error='Captcha incorreto.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        user = User.query.filter_by(username=request.form.get('username', '').strip()).first()
        if user and check_password_hash(user.password, request.form.get('password', '')):
            session['user_id'] = user.id
            record_attempt(ip, True)
            return redirect(request.args.get('next') or url_for('index'))
        record_attempt(ip, False)
        return render_template('login.html', error='Credenciais inválidas.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
    return render_template('login.html', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        ip = get_client_ip()
        if not check_rate_limit(ip):
            return render_template('login.html', registering=True, error='Muitas tentativas. Aguarde alguns minutos.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if not validate_csrf():
            return render_template('login.html', registering=True, error='Token inválido. Recarregue a página.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if not validate_captcha(request.form.get('captcha')):
            record_attempt(ip, False)
            return render_template('login.html', registering=True, error='Captcha incorreto.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if len(username) < 3 or len(username) > 80:
            return render_template('login.html', registering=True, error='Usuário deve ter 3-80 caracteres.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if not email or '@' not in email:
            return render_template('login.html', registering=True, error='E-mail inválido.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if len(password) < 4:
            return render_template('login.html', registering=True, error='Senha deve ter no mínimo 4 caracteres.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if password != confirm:
            return render_template('login.html', registering=True, error='Senhas não conferem.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if User.query.filter_by(username=username).first():
            return render_template('login.html', registering=True, error='Usuário já existe.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if User.query.filter_by(email=email).first():
            return render_template('login.html', registering=True, error='E-mail já cadastrado.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        token = secrets.token_urlsafe(48)
        user = User(username=username, email=email, password=generate_password_hash(password), verification_token=token)
        db.session.add(user)
        db.session.commit()
        base_url = request.host_url.rstrip('/')
        verify_link = f'{base_url}/verify-email/{token}'
        send_email(email, 'Confirme seu e-mail - Diário Reduzido',
            f'Olá {username},\n\nConfirme seu e-mail clicando no link abaixo:\n{verify_link}\n\nSe não foi você que criou esta conta, ignore esta mensagem.')
        session['user_id'] = user.id
        record_attempt(ip, True)
        return redirect(url_for('index'))
    return render_template('login.html', registering=True, captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

@app.route('/verify-email/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    if not user:
        return render_template('login.html', error='Link inválido ou expirado.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
    user.email_verified = True
    user.verification_token = None
    db.session.commit()
    return render_template('login.html', error='E-mail confirmado com sucesso!', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)

@app.route('/forgot', methods=['GET', 'POST'])
def forgot():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email or '@' not in email:
            return render_template('forgot.html', error='E-mail inválido.', recaptcha_site_key=RECAPTCHA_SITE_KEY)
        user = User.query.filter_by(email=email).first()
        if user:
            token = secrets.token_urlsafe(48)
            user.reset_token = token
            user.reset_token_expires = datetime.now(BRT) + timedelta(hours=1)
            db.session.commit()
            base_url = request.host_url.rstrip('/')
            reset_link = f'{base_url}/reset/{token}'
            send_email(email, 'Redefinir senha - Diário Reduzido',
                f'Olá {user.username},\n\nRedefina sua senha clicando no link abaixo:\n{reset_link}\n\nO link expira em 1 hora.\n\nSe não foi você, ignore esta mensagem.')
        return render_template('login.html', error='Se o e-mail existir, você receberá um link de redefinição.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
    return render_template('forgot.html', recaptcha_site_key=RECAPTCHA_SITE_KEY)

@app.route('/reset/<token>', methods=['GET', 'POST'])
def reset(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.now(BRT):
        return render_template('login.html', error='Link inválido ou expirado. Solicite um novo.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if len(password) < 4:
            return render_template('reset.html', token=token, error='Senha deve ter no mínimo 4 caracteres.', recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if password != confirm:
            return render_template('reset.html', token=token, error='Senhas não conferem.', recaptcha_site_key=RECAPTCHA_SITE_KEY)
        user.password = generate_password_hash(password)
        user.reset_token = None
        user.reset_token_expires = None
        db.session.commit()
        session['user_id'] = user.id
        return redirect(url_for('index'))
    return render_template('reset.html', token=token, recaptcha_site_key=RECAPTCHA_SITE_KEY)

@app.route('/archive')
@login_required
def archive():
    user = get_current_user()
    posts = Post.query.order_by(Post.date.desc()).all()
    fav_post_ids = {f.post_id for f in user.favorites} if user else set()
    return render_template('archive.html', posts=posts, user=user, fav_post_ids=fav_post_ids)

@app.route('/post/<int:id>')
def view_post(id):
    post = Post.query.get_or_404(id)
    user = get_current_user()
    fav_ids = {f.post_id for f in user.favorites} if user else set()
    return render_template('index.html', post=post, user=user, user_fav_ids=fav_ids)

@app.route('/search-date', methods=['POST'])
@login_required
def search_date():
    if not validate_csrf():
        return render_template('login.html', error='Token inválido. Faça login novamente.')
    user = get_current_user()
    date_str = request.form.get('date')
    fav_ids = {f.post_id for f in user.favorites} if user else set()
    if not date_str:
        return render_template('index.html', post=Post.query.order_by(Post.id.desc()).first(), user=user, error='Selecione uma data.', user_fav_ids=fav_ids)
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return render_template('index.html', post=Post.query.order_by(Post.id.desc()).first(), user=user, error='Data inválida.', user_fav_ids=fav_ids)
    if not user.is_paid and user.requests_made >= 1:
        return render_template('index.html', post=Post.query.order_by(Post.id.desc()).first(), user=user,
            error='Limite atingido. Faça uma doação para pedidos ilimitados.', user_fav_ids=fav_ids)
    pdf_link = search_diary_by_date(target_date)
    if not pdf_link:
        return render_template('index.html', post=Post.query.order_by(Post.id.desc()).first(), user=user,
            error=f'Nenhum diário encontrado para {target_date.strftime("%d/%m/%Y")}.', user_fav_ids=fav_ids)
    try:
        pdf_content = requests.get(pdf_link, timeout=60).content
        raw_text, model_name = GeminiClient().process_pdf(pdf_content)
        title, content = parse_title(raw_text)
        new_post = Post(
            title=title, content=content, model=model_name, pdf_link=pdf_link
        )
        db.session.add(new_post)
        user.requests_made += 1
        db.session.commit()
        return redirect(url_for('view_post', id=new_post.id))
    except Exception as e:
        print(f"Erro durante o processamento: {e}")
        db.session.rollback()
        return render_template('index.html', post=Post.query.order_by(Post.id.desc()).first(), user=user, error=str(e), user_fav_ids=fav_ids)

@app.route('/favorite/<int:post_id>', methods=['POST'])
@login_required
def toggle_favorite(post_id):
    user = get_current_user()
    Post.query.get_or_404(post_id)
    fav = Favorite.query.filter_by(user_id=user.id, post_id=post_id).first()
    if fav:
        db.session.delete(fav)
        db.session.commit()
        return jsonify({'favorited': False, 'count': len(user.favorites)})
    if not user.is_paid and len(user.favorites) >= 5:
        return jsonify({'error': 'Limite de 5 favoritos. Faça uma doação para favoritos ilimitados.'}), 400
    db.session.add(Favorite(user_id=user.id, post_id=post_id))
    db.session.commit()
    return jsonify({'favorited': True, 'count': len(user.favorites)})

@app.route('/favorites')
@login_required
def favorites():
    user = get_current_user()
    posts = [f.post for f in user.favorites]
    return render_template('archive.html', posts=posts, user=user, fav_post_ids={p.id for p in posts}, favorites_mode=True)

@app.route('/coffee')
def coffee_redirect():
    return redirect(url_for('plans'))

@app.route('/planos')
def plans():
    has_asaas = bool(os.getenv('ASAAS_API_KEY'))
    return render_template('coffee.html', has_asaas=has_asaas)

@app.route('/api/create-checkout', methods=['POST'])
@login_required
def create_checkout():
    if not validate_csrf():
        return jsonify({'error': 'Token inválido.'}), 400
    user = get_current_user()
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    cpf = request.form.get('cpf', '').strip()
    plan = request.form.get('plan', '')
    billing_type = request.form.get('billing_type', 'card')
    plans_map = {
        '1mes': (120.00, '1 Mês - Diário Reduzido'),
        '3meses': (60.00, '3 Meses - Diário Reduzido'),
        '6meses': (60.00, '6 Meses - Diário Reduzido'),
        '12meses': (108.00, 'Anual - Diário Reduzido'),
    }
    if plan not in plans_map or not name or not email or not cpf:
        return jsonify({'error': 'Dados inválidos.'}), 400
    if billing_type not in ('card', 'pix', 'boleto'):
        return jsonify({'error': 'Forma de pagamento inválida.'}), 400
    value, description = plans_map[plan]
    try:
        customer_id = create_customer(name, email, cpf)
        external_ref = f'{user.id}_{plan}'
        base_url = request.host_url.rstrip('/')
        callback_url = f'{base_url}/pagamento/sucesso'
        payment = create_payment(customer_id, value, description, external_ref, billing_type=billing_type, callback_url=callback_url)
        if billing_type == 'pix':
            return jsonify({
                'method': 'pix',
                'payment_id': payment.get('id', ''),
                'encoded_image': payment.get('encodedImage', payment.get('pixQrCode', '')),
                'payload': payment.get('payload', payment.get('pixCopiaECola', '')),
                'value': value,
            })
        url = payment.get('invoiceUrl', '') or payment.get('bankSlipUrl', '')
        if url:
            return jsonify({'method': billing_type, 'url': url})
        return jsonify({'error': 'URL de pagamento não disponível.', 'payment': payment}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/payment-status/<payment_id>')
@login_required
def payment_status(payment_id):
    try:
        data = get_payment(payment_id)
        return jsonify({'status': data.get('status', 'UNKNOWN')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/asaas-webhook', methods=['POST'])
def asaas_webhook():
    expected_token = os.getenv('ASAAS_WEBHOOK_SECRET')
    if expected_token:
        received = request.headers.get('asaas-access-token', '')
        if received != expected_token:
            return jsonify({'error': 'Token inválido'}), 403
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({'error': 'Payload inválido'}), 400
    user_id = process_webhook(payload)
    if user_id:
        target = User.query.get(user_id)
        if target:
            target.is_paid = True
            db.session.commit()
            print(f'Pagamento confirmado para usuário {user_id}')
    return jsonify({'status': 'ok'})

@app.route('/api/reprocess-latest', methods=['POST'])
@login_required
def reprocess_latest():
    user = get_current_user()
    if user.username != 'admin' and not user.is_paid:
        return jsonify({'error': 'Apenas admin ou usuários pagos podem reprocessar.'}), 403
    if not validate_csrf():
        return jsonify({'error': 'Token inválido.'}), 400
    post = Post.query.filter(Post.content.is_(None)).order_by(Post.id.desc()).first()
    if not post or not post.pdf_link:
        post = Post.query.order_by(Post.id.desc()).first()
        if not post:
            return jsonify({'error': 'Nenhum post encontrado.'}), 400
    try:
        pdf_content = requests.get(post.pdf_link, timeout=60).content
        raw_text, model_name = GeminiClient().process_pdf(pdf_content)
        title, content = parse_title(raw_text)
        post.title = title
        post.content = content
        post.model = model_name
        db.session.commit()
        print(f'Post {post.id} reprocessado com sucesso')
        return jsonify({'status': 'success', 'title': title})
    except Exception as e:
        db.session.rollback()
        print(f'Erro ao reprocessar: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/pagamento/sucesso')
def pagamento_sucesso():
    return render_template('pagamento.html', sucesso=True)

@app.route('/pagamento/falha')
def pagamento_falha():
    return render_template('pagamento.html', sucesso=False)

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true', port=5000)
