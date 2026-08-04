from flask import Flask, render_template, jsonify, request, session, redirect, url_for, abort
from flask_sqlalchemy import SQLAlchemy
from processor import GeminiClient
from asaas import create_customer, create_payment, process_webhook, tokenize_credit_card
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import json, os, requests, bs4, secrets, random, smtplib
from datetime import datetime, date, timedelta, timezone
import re, markdown, time, traceback
from urllib.parse import urljoin
from email.mime.text import MIMEText
import bs4

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())
BRT = timezone(timedelta(hours=-3))

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('POSTGRES_URL', 'sqlite:///local.db').replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres'):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 2,
        'max_overflow': 4,
        'pool_timeout': 20,
        'connect_args': {'connect_timeout': 10},
    }
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('VERCEL', 'false').lower() == 'true'
db = SQLAlchemy(app)

RUN_POST_MIGRATION = os.getenv('RUN_POST_MIGRATION', 'false').lower() == 'true'

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
        recipients = to if isinstance(to, (list, tuple)) else [to]
        recipients = [r for r in recipients if r]
        if not recipients:
            return False
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = SMTP_FROM
        if len(recipients) == 1:
            msg['To'] = recipients[0]
        else:
            msg['To'] = SMTP_FROM
            msg['Bcc'] = ', '.join(recipients)
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
    summary = db.Column(db.Text, nullable=True)
    commentary = db.Column(db.Text, nullable=True)
    date = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(BRT))
    publication_date = db.Column(db.Date, nullable=True)
    model = db.Column(db.String(100))
    pdf_link = db.Column(db.String(500))
    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan',
                               order_by='Comment.created_at')

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
    points = db.Column(db.Integer, default=0)
    paid_until = db.Column(db.DateTime(timezone=True), nullable=True)
    streak_count = db.Column(db.Integer, default=0)
    last_streak_date = db.Column(db.DateTime(timezone=True), nullable=True)
    streak_freezes = db.Column(db.Integer, default=0)
    theme = db.Column(db.String(50), default='newspaper')
    title = db.Column(db.String(100), nullable=True)
    purchased_themes = db.Column(db.Text, nullable=True)
    badge = db.Column(db.String(50), nullable=True)
    purchased_badges = db.Column(db.Text, nullable=True)
    first_purchase_done = db.Column(db.Boolean, default=False)
    font = db.Column(db.String(50), nullable=True)
    favorites = db.relationship('Favorite', backref='user', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)

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

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(BRT))
    edited_at = db.Column(db.DateTime(timezone=True), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]),
                              lazy=True, order_by='Comment.created_at')

PLAN_DAYS = { '1dia': 1, '1mes': 30, '3meses': 90, '6meses': 180, '12meses': 365 }
PLAN_VALUES = { '1dia': 10.00, '1mes': 30.00, '3meses': 40.00, '6meses': 60.00, '12meses': 108.00, 'freeze1': 5.00, 'freeze3': 12.00, 'freeze5': 18.00 }
FREE_MONTH_POINTS = 360

BADGES = {
    'star': ('Estrela', '\u2b50'),
    'fire': ('Fogo', '\U0001f525'),
    'diamond': ('Diamante', '\U0001f48e'),
    'crown': ('Coroa', '\U0001f451'),
    'trophy': ('Troféu', '\U0001f3c6'),
    'shield': ('Escudo', '\U0001f6e1\ufe0f'),
    'heart': ('Coração', '\u2764\ufe0f'),
    'moon': ('Lua', '\U0001f319'),
}

BADGE_PRICE = 5.00

PIX_PAYLOAD = '00020126580014br.gov.bcb.pix01363cfb8787-f766-49e9-b2d5-dc510a584ed45204000053039865802BR5924Matheus Pereira Venancio6009Sao Paulo62240520daqr1092695570836912630451DB'
PIX_QR_IMAGE = '/static/img/qrCode.png'

COMBOS = {
    'combo_starter': {
        'name': 'Combo Iniciante',
        'price': 24.00,
        'plan': '1mes',
        'themes': ['dark'],
        'freezes': 0,
        'badge': None,
        'desc': '1 mês de acesso + tema Dark',
        'savings': 7,
    },
    'combo_popular': {
        'name': 'Combo Trimestral+',
        'price': 38.00,
        'plan': '3meses',
        'themes': ['dark', 'sepia'],
        'freezes': 0,
        'badge': None,
        'desc': '3 meses + temas Dark e Sépia',
        'savings': 5,
    },
    'combo_annual_plus': {
        'name': 'Combo Anual Premium',
        'price': 98.00,
        'plan': '12meses',
        'themes': ['dark', 'sepia', 'matrix', 'ocean'],
        'freezes': 0,
        'badge': None,
        'desc': '1 ano + 4 temas exclusivos',
        'savings': 26,
    },
    'combo_freeze': {
        'name': 'Combo Congelamento',
        'price': 56.00,
        'plan': '3meses',
        'themes': [],
        'freezes': 5,
        'badge': None,
        'desc': '3 meses + 5 congelamentos de streak',
        'savings': 8,
    },
}

def get_theme_price(req_streak, user_streak=0):
    req_streak = int(req_streak)
    user_streak = int(user_streak)
    base = THEME_PRICES.get(req_streak, 5.00)
    if user_streak >= req_streak:
        return 0.0
    if user_streak <= 0:
        return base
    progress = min(user_streak / req_streak, 0.99)
    discounted = base * (1 - progress)
    return max(round(discounted, 2), 5.0)

STREAK_FONTS = {
    7: ('merriweather', 'Merriweather', "'Merriweather', serif"),
    14: ('lora', 'Lora', "'Lora', serif"),
    21: ('spectral', 'Spectral', "'Spectral', serif"),
    28: ('vollkorn', 'Vollkorn', "'Vollkorn', serif"),
    35: ('bitter', 'Bitter', "'Bitter', serif"),
    42: ('arvo', 'Arvo', "'Arvo', serif"),
    49: ('roboto-slab', 'Roboto Slab', "'Roboto Slab', serif"),
    56: ('zilla-slab', 'Zilla Slab', "'Zilla Slab', serif"),
    63: ('source-serif', 'Source Serif 4', "'Source Serif 4', serif"),
    70: ('eb-garamond', 'EB Garamond', "'EB Garamond', serif"),
    77: ('cormorant', 'Cormorant Garamond', "'Cormorant Garamond', serif"),
    84: ('libre-baskerville', 'Libre Baskerville', "'Libre Baskerville', serif"),
    91: ('cardo', 'Cardo', "'Cardo', serif"),
    98: ('tinos', 'Tinos', "'Tinos', serif"),
    105: ('pt-serif', 'PT Serif', "'PT Serif', serif"),
    112: ('karla', 'Karla', "'Karla', sans-serif"),
    119: ('inter', 'Inter', "'Inter', sans-serif"),
    126: ('nunito', 'Nunito', "'Nunito', sans-serif"),
    133: ('rubik', 'Rubik', "'Rubik', sans-serif"),
    140: ('worksans', 'Work Sans', "'Work Sans', sans-serif"),
    147: ('opensans', 'Open Sans', "'Open Sans', sans-serif"),
    154: ('lato', 'Lato', "'Lato', sans-serif"),
    161: ('montserrat', 'Montserrat', "'Montserrat', sans-serif"),
    168: ('raleway', 'Raleway', "'Raleway', sans-serif"),
    175: ('ubuntu', 'Ubuntu', "'Ubuntu', sans-serif"),
    182: ('firasans', 'Fira Sans', "'Fira Sans', sans-serif"),
    189: ('dmsans', 'DM Sans', "'DM Sans', sans-serif"),
    196: ('manrope', 'Manrope', "'Manrope', sans-serif"),
    203: ('outfit', 'Outfit', "'Outfit', sans-serif"),
    210: ('sora', 'Sora', "'Sora', sans-serif"),
    217: ('archivo', 'Archivo', "'Archivo', sans-serif"),
    224: ('space-grotesk', 'Space Grotesk', "'Space Grotesk', sans-serif"),
    231: ('josefin-sans', 'Josefin Sans', "'Josefin Sans', sans-serif"),
    238: ('barlow', 'Barlow', "'Barlow', sans-serif"),
    245: ('mulish', 'Mulish', "'Mulish', sans-serif"),
    252: ('quicksand', 'Quicksand', "'Quicksand', sans-serif"),
    259: ('asap', 'Asap', "'Asap', sans-serif"),
    266: ('maven-pro', 'Maven Pro', "'Maven Pro', sans-serif"),
    273: ('overpass', 'Overpass', "'Overpass', sans-serif"),
    280: ('epilogue', 'Epilogue', "'Epilogue', sans-serif"),
    287: ('urbanist', 'Urbanist', "'Urbanist', sans-serif"),
    294: ('exo-2', 'Exo 2', "'Exo 2', sans-serif"),
    301: ('oxanium', 'Oxanium', "'Oxanium', sans-serif"),
    308: ('rajdhani', 'Rajdhani', "'Rajdhani', sans-serif"),
    315: ('prompt', 'Prompt', "'Prompt', sans-serif"),
    322: ('figtree', 'Figtree', "'Figtree', sans-serif"),
    329: ('plus-jakarta', 'Plus Jakarta Sans', "'Plus Jakarta Sans', sans-serif"),
    336: ('chivo', 'Chivo', "'Chivo', sans-serif"),
    343: ('libre-franklin', 'Libre Franklin', "'Libre Franklin', sans-serif"),
    350: ('sourcesans', 'Source Sans 3', "'Source Sans 3', sans-serif"),
    357: ('dm-serif', 'DM Serif Display', "'DM Serif Display', serif"),
    364: ('playfair-display', 'Playfair Display', "'Playfair Display', serif"),
    365: ('crimson-pro', 'Crimson Pro', "'Crimson Pro', serif"),
}

ADMIN_FONT = ('unbounded', 'Unbounded', "'Unbounded', sans-serif")

def get_font_css(font_id):
    if font_id == 'admin':
        return ADMIN_FONT[2]
    for days, (fid, fname, fcss) in STREAK_FONTS.items():
        if fid == font_id:
            return fcss
    return "'Crimson Pro', serif"

def get_font_name(font_id):
    if not font_id or font_id == 'default':
        return 'Padrão'
    if font_id == 'admin':
        return ADMIN_FONT[1]
    for days, (fid, fname, fcss) in STREAK_FONTS.items():
        if fid == font_id:
            return fname
    return 'Padrão'

def get_unlocked_fonts(user):
    if not user:
        return [('default', 'Padrão', "'Crimson Pro', serif")]
    if user.username == 'admin':
        result = [('admin', ADMIN_FONT[1], ADMIN_FONT[2])]
        result.extend((fid, fname, fcss) for _, (fid, fname, fcss) in sorted(STREAK_FONTS.items()))
        return result
    streak = user.streak_count or 0
    result = [('default', 'Padrão', "'Crimson Pro', serif")]
    for days, (fid, fname, fcss) in sorted(STREAK_FONTS.items()):
        if streak >= days:
            result.append((fid, fname, fcss))
    return result

def get_all_font_urls():
    families = ['Playfair+Display:ital,wght@0,400..900;1,400..900',
                'Crimson+Pro:ital,wght@0,200..900;1,200..900',
                'Inconsolata:wght@200..900']
    return f"https://fonts.googleapis.com/css2?{'&'.join('family=' + f for f in families)}&display=swap"

def get_user_font_url(user):
    if not user:
        return get_all_font_urls()
    names = set()
    names.add('Playfair Display')
    names.add('Crimson Pro')
    names.add('Inconsolata')
    if user.font and user.font != 'default':
        for _, (fid, fname, _) in STREAK_FONTS.items():
            if fid == user.font:
                names.add(fname)
                break
    unlocked = get_unlocked_fonts(user)
    for fid, fname, _ in unlocked:
        if fid != 'default':
            names.add(fname)
    families = [n.replace(' ', '+') for n in sorted(names)]
    return f"https://fonts.googleapis.com/css2?{'&'.join('family=' + f for f in families)}&display=swap"

def get_purchasable_themes(user):
    if not user:
        return []
    if user.username == 'admin':
        return [(tid, tn, True) for tid, (tn, _) in STREAK_THEMES.items()]
    streak = user.streak_count or 0
    purchased = set()
    if user.purchased_themes:
        purchased = set(t.strip() for t in user.purchased_themes.split(',') if t.strip())
    result = []
    for req_streak, (theme_id, theme_name) in sorted(STREAK_THEMES.items()):
        already = streak >= req_streak or theme_id in purchased
        result.append((req_streak, theme_name, already))
    return result

def get_purchasable_badges(user):
    if not user:
        return []
    if user.username == 'admin':
        return [(bid, bn, be, True) for bid, (bn, be) in BADGES.items()]
    is_pioneer = False
    pioneer = AppConfig.query.filter_by(key='first_365_user_id').first()
    if pioneer and pioneer.value and str(user.id) == pioneer.value:
        is_pioneer = True
    purchased = set()
    if user.purchased_badges:
        purchased = set(b.strip() for b in user.purchased_badges.split(',') if b.strip())
    result = []
    if is_pioneer:
        result.append(('pioneer', PIONEER_BADGE[0], PIONEER_BADGE[1], True))
    for bid, (bname, bemoji) in sorted(BADGES.items()):
        owned = bid in purchased
        result.append((bid, bname, bemoji, owned))
    return result

COLUMN_RENAMES = {
    'user': [('password_hash', 'password')],
    'post': [('body', 'content'), ('text', 'content'), ('headline', 'title'), ('model_used', 'model')],
    'favorite': [('post_id_old', 'post_id')],
}

def ensure_constraints():
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    for table_name, model in [('user', User), ('post', Post), ('favorite', Favorite),
                               ('login_attempt', LoginAttempt), ('app_config', AppConfig),
                               ('comment', Comment)]:
        existing = {c['name'] for c in inspector.get_columns(table_name)}
        existing_ucs = {uc['name'] for uc in inspector.get_unique_constraints(table_name)}
        for col in model.__table__.columns:
            if col.name not in existing:
                continue
            null_info = [c for c in inspector.get_columns(table_name) if c['name'] == col.name]
            if null_info and null_info[0].get('nullable', True) != col.nullable:
                try:
                    db.session.execute(db.text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{col.name}" {"SET" if not col.nullable else "DROP"} NOT NULL'))
                except Exception:
                    db.session.rollback()
            if col.unique:
                constraint_name = f'{table_name}_{col.name}_key'
                if constraint_name not in existing_ucs:
                    try:
                        db.session.execute(db.text(f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" UNIQUE ("{col.name}")'))
                    except Exception:
                        db.session.rollback()

def migrate_columns():
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    for table_name, model in [('user', User), ('post', Post), ('favorite', Favorite),
                               ('login_attempt', LoginAttempt), ('app_config', AppConfig),
                               ('comment', Comment)]:
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
                    db.session.commit()
                except Exception:
                    db.session.rollback()
    db.session.commit()

def generate_summary(text, limit=350):
    if not text:
        return ''
    clean = re.sub(r'[#*`>\[\]]+', '', text)
    clean = re.sub(r'\n{2,}', '\n', clean).strip()
    sentences = re.split(r'(?<=[.!?])\s+', clean)
    key_sentences = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if any(kw in s.lower() for kw in ['nomeou', 'exonerou', 'contratou', 'nomeação', 'exoneração',
                                            'rescisão', 'editais', 'licitação', 'concorrência',
                                            'tornar público', 'comissão', 'portaria', 'decreto',
                                            'resultado', 'aprova', 'autoriza', 'designa',
                                            'institui', 'regulamenta']):
            key_sentences.append(s)
            if len(key_sentences) >= 2:
                break
    if not key_sentences:
        for s in sentences:
            s = s.strip()
            if any(c.isdigit() for c in s):
                key_sentences.append(s)
                if len(key_sentences) >= 2:
                    break
    if not key_sentences:
        for s in sentences[:5]:
            s = s.strip()
            if len(s) > 20:
                key_sentences.append(s)
                break
    result = ' '.join(key_sentences)
    if len(result) > limit:
        cut = result[:limit]
        boundary = max(cut.rfind('. '), cut.rfind('! '), cut.rfind('? '))
        if boundary > 0:
            result = cut[:boundary + 1]
        else:
            result = cut.rstrip() + '...'
    return result.strip()


def make_teaser(content, limit=200):
    return generate_summary(content, limit=limit)


def parse_content(text):
    prefix = "TITULO:"
    date_prefix = "DATA PUBLICACAO:"
    title = "Edição do Diário Oficial"
    pub_date = None
    content = text.strip()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith(prefix):
            t = stripped[len(prefix):].strip()
            if t:
                title = t
            content = content.replace(line, '', 1).strip()
        elif stripped.upper().startswith(date_prefix):
            raw = stripped[len(date_prefix):].strip()
            try:
                pub_date = datetime.strptime(raw, '%d/%m/%Y').date()
            except ValueError:
                try:
                    pub_date = datetime.strptime(raw, '%d-%m-%Y').date()
                except ValueError:
                    pass
            content = content.replace(line, '', 1).strip()
    commentary = ''
    marker = '### Conclusões da IA'
    idx = content.find(marker)
    if idx != -1:
        commentary = content[idx + len(marker):].strip()
        content = content[:idx].strip()
    return title, content, commentary, pub_date

def parse_title(text):
    title, content, _, _ = parse_content(text)
    return title, content

def migrate_existing_posts():
    posts = Post.query.filter(Post.commentary.is_(None)).all()
    count = 0
    for post in posts:
        raw = post.content
        if not raw:
            continue
        title, content, commentary, _ = parse_content(raw)
        if commentary and not post.commentary:
            post.commentary = commentary
            post.content = content
        if title and title != "Edição do Diário Oficial":
            post.title = title
        count += 1
    db.session.commit()
    print(f'Migration: {count} posts atualizados')
    return count

with app.app_context():
    db.create_all()
    migrate_columns()
    ensure_constraints()
    admin_pass = os.getenv('ADMIN_PASSWORD', 'admin')
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        db.session.add(User(username='admin', email=os.getenv('ADMIN_EMAIL', 'admin@diario.app'), password=generate_password_hash(admin_pass), email_verified=True, streak_freezes=999, is_paid=True, first_purchase_done=True))
    elif not admin_user.email:
        admin_user.email = os.getenv('ADMIN_EMAIL', 'admin@diario.app')
        admin_user.email_verified = True
    if not AppConfig.query.filter_by(key='last_checked_timestamp').first():
        db.session.add(AppConfig(key='last_checked_timestamp', value=datetime(1970, 1, 1, tzinfo=BRT).isoformat()))
    if not AppConfig.query.filter_by(key='is_checking').first():
        db.session.add(AppConfig(key='is_checking', value='false'))
    db.session.commit()
    if RUN_POST_MIGRATION:
        try:
            migrate_existing_posts()
        except Exception:
            pass

app._schema_checked = False

@app.before_request
def ensure_schema():
    if not app._schema_checked:
        with app.app_context():
            migrate_columns()
            if RUN_POST_MIGRATION:
                try:
                    migrate_existing_posts()
                except Exception:
                    pass
        app._schema_checked = True

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com https://www.google.com https://www.gstatic.com; style-src 'self' https://fonts.googleapis.com https://cdnjs.cloudflare.com 'unsafe-inline'; img-src 'self' data:; font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; connect-src 'self'; frame-src 'self' https://www.google.com"
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
    return db.session.get(User, session.get('user_id')) if session.get('user_id') else None

CHECK_STALE_MINUTES = 15

def set_checking(value):
    c = AppConfig.query.filter_by(key='is_checking').first()
    if c:
        c.value = datetime.now(BRT).isoformat() if value else 'false'
        db.session.commit()

def is_checking():
    c = AppConfig.query.filter_by(key='is_checking').first()
    if not c or c.value == 'false':
        return False
    try:
        ts = datetime.fromisoformat(c.value)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=BRT)
        if (datetime.now(BRT) - ts) > timedelta(minutes=CHECK_STALE_MINUTES):
            return False
    except ValueError:
        return False
    return True

def get_client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'

def validate_csrf():
    if app.config.get('TESTING'):
        return True
    stored = session.get('csrf_token')
    token = request.form.get('csrf_token')
    return bool(stored and token and secrets.compare_digest(stored, token))

def check_rate_limit(ip, max_attempts=10, window_minutes=15):
    if app.config.get('TESTING'):
        return True
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

def failed_attempt_count(ip):
    cutoff = datetime.now(BRT) - timedelta(minutes=15)
    return LoginAttempt.query.filter(
        LoginAttempt.ip_address == ip,
        LoginAttempt.timestamp > cutoff,
        LoginAttempt.success == False
    ).count()

def should_show_captcha(ip):
    return failed_attempt_count(ip) >= 5

RECAPTCHA_SITE_KEY = os.getenv('RECAPTCHA_SITE_KEY', '')
RECAPTCHA_SECRET_KEY = os.getenv('RECAPTCHA_SECRET_KEY', '')

def _captcha_disabled():
    return app.config.get('TESTING') or RECAPTCHA_SITE_KEY or app.debug or os.getenv('FLASK_ENV') == 'development' or os.getenv('FLASK_DEBUG', '').lower() == 'true'

def generate_captcha():
    if _captcha_disabled():
        return None
    a, b = random.randint(1, 12), random.randint(1, 12)
    op = random.choice(['+', '-'])
    if op == '-':
        a, b = max(a, b), min(a, b)
    session['captcha_answer'] = str(a + b if op == '+' else a - b)
    return f"{a} {op} {b}"

def validate_captcha(answer):
    if app.config.get('TESTING') or app.debug or os.getenv('FLASK_ENV') == 'development' or os.getenv('FLASK_DEBUG', '').lower() == 'true':
        return True
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

def is_weekend():
    return datetime.now(BRT).weekday() >= 5

def get_check_interval():
    if is_weekend():
        return 360
    post = Post.query.order_by(Post.id.desc()).first()
    if not post:
        return 15
    if not post.content or not post.content.strip():
        return 15
    post_date = post.date
    if not post_date:
        return 15
    if post_date.tzinfo is None:
        post_date = post_date.replace(tzinfo=BRT)
    if (datetime.now(BRT) - post_date) > timedelta(hours=24):
        return 15
    return 60

def render_md(text):
    return markdown.markdown(text or '', extensions=['extra'])

def check_premium_expiry(user):
    if user and user.is_paid and user.paid_until and user.paid_until < datetime.now(BRT):
        user.is_paid = False
        db.session.commit()

def get_premium_days_left(user):
    if not user or not user.is_paid or not user.paid_until:
        return 0
    delta = user.paid_until - datetime.now(BRT)
    return max(0, delta.days)

STREAK_THEMES = {
    3: ('dark', 'Modo Escuro'),
    30: ('sepia', 'Tons Sepia'),
    60: ('matrix', 'Matrix'),
    90: ('ocean', 'Oceano'),
    120: ('forest', 'Floresta'),
    150: ('sunset', 'Pôr do Sol'),
    180: ('midnight', 'Meia-Noite'),
    210: ('lavender', 'Lavanda'),
    240: ('sakura', 'Sakura'),
    270: ('mint', 'Menta'),
    300: ('ember', 'Brasa'),
    330: ('galaxy', 'Galáxia'),
    360: ('royal', 'Real'),
    365: ('coroado', 'O Coroado'),
}

THEME_PRICES = {
    3: 5.00,
    30: 5.00,
    60: 7.00,
    90: 9.00,
    120: 12.00,
    150: 15.00,
    180: 18.00,
    210: 22.00,
    240: 26.00,
    270: 30.00,
    300: 35.00,
    330: 40.00,
    360: 45.00,
    365: 50.00,
}

STREAK_BONUS_POINTS = {3: 10, 30: 25, 60: 50, 90: 100, 120: 100, 150: 150,
                       180: 150, 210: 200, 240: 200, 270: 250, 300: 300,
                       330: 350, 360: 400, 365: 500}

PIONEER_TITLE = ('O Pioneiro', '\U0001f3c6')
PIONEER_BADGE = ('Pioneiro', '\U0001f3c6')

STREAK_TITLES = {
    10: ('Leitor Iniciante', '\U0001f7e2'),
    20: ('Leitor Dedicado', '\U0001f535'),
    30: ('Cidadão Atento', '\U0001f7e1'),
    40: ('Observador Fiel', '\U0001f7e0'),
    50: ('Guardião da Memória', '\U0001f7e2'),
    60: ('Veterano da Leitura', '\U0001f535'),
    70: ('Mestre da Informação', '\U0001f7e1'),
    80: ('Sábio do Diário', '\U0001f7e0'),
    90: ('Cidadão Exemplar', '\U0001f7e2'),
    100: ('Centenário da Leitura', '\U0001f535'),
    110: ('Cronista do Tempo', '\U0001f7e1'),
    120: ('Arquivista Real', '\U0001f7e0'),
    130: ('Defensor da Transparência', '\U0001f7e2'),
    140: ('Pilar da Comunidade', '\U0001f535'),
    150: ('Lenda Viva', '\U0001f7e1'),
    160: ('Vigia da Verdade', '\U0001f7e0'),
    170: ('Coração do Diário', '\U0001f7e2'),
    180: ('Semestral da Leitura', '\U0001f535'),
    190: ('Incansável', '\U0001f7e1'),
    200: ('Bicentenário', '\U0001f7e0'),
    210: ('Farol da Informação', '\U0001f7e2'),
    220: ('Mural da História', '\U0001f535'),
    230: ('Raiz do Conhecimento', '\U0001f7e1'),
    240: ('Eterno Aprendiz', '\U0001f7e0'),
    250: ('Ponte do Saber', '\U0001f7e2'),
    260: ('Escudo da Memória', '\U0001f535'),
    270: ('Titã da Leitura', '\U0001f7e1'),
    280: ('A Sentinela', '\U0001f7e0'),
    290: ('Voz da Experiência', '\U0001f7e2'),
    300: ('Fênix da Leitura', '\U0001f535'),
    310: ('Guardião Supremo', '\U0001f7e1'),
    320: ('Mestre dos Mestres', '\U0001f7e0'),
    330: ('Lenda do Diário', '\U0001f7e2'),
    340: ('Imortal da Palavra', '\U0001f535'),
    350: ('Túlio do Conhecimento', '\U0001f7e1'),
    360: ('Templo do Conhecimento', '\U0001f7e0'),
    365: ('O Coroado', '\U0001f451'),
}

def get_user_title(user):
    if not user:
        return None
    if user.username == 'admin':
        return ('O Editor-Chefe', '\U0001f4ed')
    pioneer = AppConfig.query.filter_by(key='first_365_user_id').first()
    if pioneer and pioneer.value and str(user.id) == pioneer.value:
        return PIONEER_TITLE
    if user.title:
        for days, (tname, temoji) in STREAK_TITLES.items():
            if tname == user.title:
                return (tname, temoji)
    streak = user.streak_count or 0
    best = None
    best_days = 0
    for days, (title, emoji) in sorted(STREAK_TITLES.items()):
        if streak >= days and days >= best_days:
            best = (title, emoji)
            best_days = days
    return best

def get_unlocked_titles(user):
    if not user:
        return []
    if user.username == 'admin':
        return [(days, title, emoji) for days, (title, emoji) in STREAK_TITLES.items()]
    unlocked = []
    streak = user.streak_count or 0
    for days, (title, emoji) in sorted(STREAK_TITLES.items()):
        if streak >= days:
            unlocked.append((days, title, emoji))
    return unlocked

def get_unlocked_themes(user):
    themes = [('newspaper', 'Clássico (Newspaper)')]
    if not user:
        return themes
    if user.username == 'admin':
        for req_streak, (theme_id, theme_name) in sorted(STREAK_THEMES.items()):
            themes.append((theme_id, theme_name))
        return themes
    streak = user.streak_count or 0
    purchased = set()
    if user.purchased_themes:
        purchased = set(t.strip() for t in user.purchased_themes.split(',') if t.strip())
    for req_streak, (theme_id, theme_name) in sorted(STREAK_THEMES.items()):
        if streak >= req_streak or theme_id in purchased:
            themes.append((theme_id, theme_name))
    return themes

def update_streak(user):
    now = datetime.now(BRT)
    today = now.date()
    if user.last_streak_date:
        last = user.last_streak_date
        if last.tzinfo is None:
            last = last.replace(tzinfo=BRT)
        last_date = last.date()
        diff = (today - last_date).days
        if diff == 1:
            user.streak_count = (user.streak_count or 0) + 1
        elif diff > 1:
            freezes = user.streak_freezes or 0
            if freezes > 0:
                used = min(freezes, diff - 1)
                user.streak_freezes = freezes - used
            else:
                user.streak_count = 1
    elif user.last_streak_date is None:
        user.streak_count = 1
    user.last_streak_date = now
    streak = user.streak_count
    for req_streak, points in sorted(STREAK_BONUS_POINTS.items()):
        if streak == req_streak:
            user.points = (user.points or 0) + points
            break
    if streak >= 365 and user.username != 'admin':
        pioneer = AppConfig.query.filter_by(key='first_365_user_id').first()
        if not pioneer:
            db.session.add(AppConfig(key='first_365_user_id', value=str(user.id)))
    db.session.commit()

def fetch_daily_diary():
    url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
    try:
        s = requests.Session()
        s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        resp = s.get(url, timeout=30)
        soup = bs4.BeautifulSoup(resp.text, "html.parser")
        link = soup.select_one('a.btn-primary.arquivo-pdf')
        if link and link.get('href'):
            pdf_url = urljoin('https://www.valadares.mg.gov.br', link['href'])
            pub_date = _extract_date_from_url(pdf_url)
            return pdf_url, pub_date
        return None, None
    except Exception as e:
        print(f"Erro ao buscar diário: {e}")
        return None, None

def _extract_date_from_url(url):
    m = re.search(r'(\d{2})-(\d{2})-(\d{4})', url)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None

def extract_ajaxpro_handler(html):
    soup = bs4.BeautifulSoup(html, 'html.parser')
    for script in soup.find_all('script'):
        src = script.get('src') or ''
        if 'ajaxpro/diel_diel_lis,' in src:
            return src.split('?')[0]
    return None

def perform_update_logic():
    now = datetime.now(BRT)
    print(f"[{now.strftime('%H:%M:%S')}] Verificando novo diário...")
    last_post = Post.query.order_by(Post.id.desc()).first()
    last_link = last_post.pdf_link if last_post else ""
    current_link, pub_date = fetch_daily_diary()
    if current_link and current_link != last_link:
        print(f"Novo diário encontrado: {current_link}")
        try:
            pdf_content = requests.get(current_link, timeout=30).content
            gemini = GeminiClient()
            raw_text, model_name = gemini.process_pdf(pdf_content)
            title, content, commentary, ai_pub_date = parse_content(raw_text)
            new_post = Post(
                title=title, content=content, summary=generate_summary(content),
                commentary=commentary, model=model_name, pdf_link=current_link,
                publication_date=ai_pub_date or pub_date
            )
            db.session.add(new_post)
            db.session.commit()

            try:
                paid_emails = [pu.email for pu in User.query.filter_by(is_paid=True).all()
                               if pu.email and pu.email_verified]
                if paid_emails:
                    send_email(paid_emails, 'Novo Diário Reduzido disponível!',
                        f'Olá,\n\n'
                        f'Uma nova edição do Diário Reduzido já está disponível:\n'
                        f'"{title}"\n\n'
                        f'Acesse: https://odiarioreduzidogv.vercel.app/\n\n'
                        f'---\n'
                        f'Para cancelar o recebimento, entre em contato conosco.')
            except Exception as e:
                print(f'Erro ao enviar notificações: {e}')

            return {"status": "success", "message": "Blog atualizado!"}
        except Exception as e:
            print(f"Erro durante o processamento: {e}")
            db.session.rollback()
            return {"status": "error", "message": str(e)}
    return {"status": "no_change", "message": "Nenhum diário novo disponível."}

def _ajaxpro_datetime(dt):
    return {"__type": "System.DateTime", "Year": dt.year, "Month": dt.month,
            "Day": dt.day, "Hour": dt.hour, "Minute": dt.minute,
            "Second": dt.second, "Millisecond": dt.microsecond // 1000}

def _parse_datatable_js(text):
    m = re.search(r'new Ajax\.Web\.DataTable\(', text)
    if not m:
        return []
    start = m.end()
    depth = 0
    comma_pos = None
    for i, ch in enumerate(text[start:], start):
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                cols_end = i + 1
                break
    else:
        return []
    rest = text[cols_end:].lstrip().lstrip(',').lstrip()
    if not rest.startswith('['):
        return []
    depth = 0
    for i, ch in enumerate(rest):
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                rows_str = rest[:i + 1]
                break
    else:
        return []
    cols_text = text[start:cols_end]
    cols = re.findall(r'\["(\w+)","[^"]+"\]', cols_text)
    rows_str = re.sub(r'new Date\([^)]+\)', 'null', rows_str)
    raw_rows = json.loads(rows_str)
    return [dict(zip(cols, row)) for row in raw_rows]

def search_diary_by_date(target_date):
    url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
    base_pdf = 'https://www.valadares.mg.gov.br'
    try:
        s = requests.Session()
        s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        resp = s.get(url, timeout=30)
        handler_path = extract_ajaxpro_handler(resp.text)
        if not handler_path:
            raise Exception('AjaxPro handler not found')
        handler_url = urljoin(base_pdf, handler_path)
        dt_start = datetime.combine(target_date, datetime.min.time(), tzinfo=BRT)
        dt_end = datetime.combine(target_date, datetime.max.time(), tzinfo=BRT)
        payload = {
            'Page': 0, 'cdCaderno': 1, 'Size': 10,
            'dtDiario_menor': _ajaxpro_datetime(dt_start),
            'dtDiario_maior': _ajaxpro_datetime(dt_end),
            'dsPalavraChave': '', 'nuEdicao': -1.0, 'chkPesquisaExata': False,
        }
        body = json.dumps(payload)
        headers = {
            'X-AjaxPro-Method': 'GetDiario',
            'Content-Type': 'text/plain; charset=utf-8',
            'Referer': url,
        }
        ajax_resp = s.post(handler_url, data=body, headers=headers, timeout=60)
        raw = ajax_resp.text.strip().rstrip(';').strip()
        if raw.startswith('null'):
            err_part = raw[4:].lstrip(';').strip().rstrip('/*').strip()
            if err_part:
                try:
                    err = json.loads(err_part)
                    raise Exception(f"AjaxPro error: {err.get('Message', err_part)}")
                except json.JSONDecodeError:
                    pass
            return None
        rows = _parse_datatable_js(raw)
        for row in rows:
            pdf_url = row.get('URLABRIRARQUIVO', '')
            if not pdf_url:
                fname = row.get('NMARQUIVO', '') + row.get('NMEXTENSAOARQUIVO', '')
                if fname:
                    pdf_url = f'{base_pdf}/abrir_arquivo.aspx?cdLocal=12&arquivo={fname}'
            if pdf_url:
                return pdf_url
        return None
    except Exception as e:
        print(f"Erro ao buscar diário por data: {e}")
        return None

# --- stdlib-only version (no requests/bs4) ---

from http.cookiejar import CookieJar
from urllib.request import Request, urlopen
from html.parser import HTMLParser

class _AjaxHandlerParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.handler = None
    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            for name, val in attrs:
                if name == 'src' and val and 'ajaxpro/diel_diel_lis,' in val:
                    self.handler = val.split('?')[0]

def _stdlib_get(url, headers=None):
    hdrs = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    if headers:
        hdrs.update(headers)
    req = Request(url, headers=hdrs)
    cj = CookieJar()
    from urllib.request import HTTPCookieProcessor, build_opener
    opener = build_opener(HTTPCookieProcessor(cj))
    return opener.open(req).read().decode('utf-8'), cj

def _stdlib_post(url, data, headers=None):
    hdrs = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'text/plain; charset=utf-8'}
    if headers:
        hdrs.update(headers)
    req = Request(url, data=data.encode('utf-8'), headers=hdrs, method='POST')
    cj = CookieJar()
    from urllib.request import HTTPCookieProcessor, build_opener
    opener = build_opener(HTTPCookieProcessor(cj))
    return opener.open(req).read().decode('utf-8')

def search_diary_by_date_stdlib(target_date):
    url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
    base_pdf = 'https://www.valadares.mg.gov.br'
    try:
        html, _ = _stdlib_get(url)
        parser = _AjaxHandlerParser()
        parser.feed(html)
        handler_path = parser.handler
        if not handler_path:
            raise Exception('AjaxPro handler not found')
        handler_url = urljoin(base_pdf, handler_path)
        dt_start = datetime.combine(target_date, datetime.min.time(), tzinfo=BRT)
        dt_end = datetime.combine(target_date, datetime.max.time(), tzinfo=BRT)
        payload = {
            'Page': 0, 'cdCaderno': 1, 'Size': 10,
            'dtDiario_menor': _ajaxpro_datetime(dt_start),
            'dtDiario_maior': _ajaxpro_datetime(dt_end),
            'dsPalavraChave': '', 'nuEdicao': -1.0, 'chkPesquisaExata': False,
        }
        body = json.dumps(payload)
        headers = {'X-AjaxPro-Method': 'GetDiario', 'Referer': url}
        raw = _stdlib_post(handler_url, body, headers)
        raw = raw.strip().rstrip(';').strip()
        if raw.startswith('null'):
            return None
        rows = _parse_datatable_js(raw)
        for row in rows:
            pdf_url = row.get('URLABRIRARQUIVO', '')
            if not pdf_url:
                fname = row.get('NMARQUIVO', '') + row.get('NMEXTENSAOARQUIVO', '')
                if fname:
                    pdf_url = f'{base_pdf}/abrir_arquivo.aspx?cdLocal=12&arquivo={fname}'
            if pdf_url:
                return pdf_url
        return None
    except Exception as e:
        print(f"Erro (stdlib): {e}")
        return None

@app.route('/')
def index():
    user = get_current_user()
    check_premium_expiry(user)
    post = Post.query.order_by(Post.publication_date.desc().nullslast()).first()
    if post:
        if post.content:
            post.content = render_md(post.content)
        if post.commentary:
            post.commentary = render_md(post.commentary)
    last_check = AppConfig.query.filter_by(key='last_checked_timestamp').first()
    now = datetime.now(BRT)
    interval_min = get_check_interval()
    should_check = True
    if last_check:
        last_time = datetime.fromisoformat(last_check.value)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=BRT)
        should_check = (now - last_time) > timedelta(minutes=interval_min)
    fav_ids = {f.post_id for f in user.favorites} if user else set()
    now = datetime.now(BRT)
    unlocked_themes = get_unlocked_themes(user)
    latest_posts = Post.query.order_by(Post.publication_date.desc().nullslast()).all()
    if post:
        latest_posts = [p for p in latest_posts if p.id != post.id]
    for p in latest_posts[:5]:
        p.teaser = make_teaser(p.content)
    latest_posts = latest_posts[:5]
    cidadao_pct = min(100, int(((user.streak_count or 0) / 90) * 100)) if user else 0
    return render_template('index.html', post=post, user=user, should_check=should_check,
                           user_fav_ids=fav_ids, check_interval=interval_min, is_weekend=is_weekend(),
                           unlocked_themes=unlocked_themes, now=now, latest_posts=latest_posts,
                           cidadao_pct=cidadao_pct, streak_freezes=user.streak_freezes or 0 if user else 0)

@app.route('/api/should-check')
def api_should_check():
    last_check = AppConfig.query.filter_by(key='last_checked_timestamp').first()
    now = datetime.now(BRT)
    interval_min = get_check_interval()
    if last_check:
        last_time = datetime.fromisoformat(last_check.value)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=BRT)
        return jsonify({'should_check': (now - last_time) > timedelta(minutes=interval_min), 'interval_min': interval_min})
    return jsonify({'should_check': True, 'interval_min': interval_min})

@app.route('/api/perform-check')
def api_perform_check():
    force = request.args.get('force') == '1'
    if is_checking():
        return jsonify({'status': 'already_checking'})
    last_check = AppConfig.query.filter_by(key='last_checked_timestamp').first()
    now = datetime.now(BRT)
    interval_min = get_check_interval()
    if not force and last_check:
        last_time = datetime.fromisoformat(last_check.value)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=BRT)
        if (now - last_time) <= timedelta(minutes=interval_min):
            return jsonify({'status': 'not_needed', 'interval_min': interval_min})
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
        need_captcha = should_show_captcha(ip)
        if need_captcha and not validate_captcha(request.form.get('captcha')):
            record_attempt(ip, False)
            return render_template('login.html', error='Captcha incorreto.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        user = User.query.filter_by(username=request.form.get('username', '').strip()).first()
        if user and check_password_hash(user.password, request.form.get('password', '')):
            session['user_id'] = user.id
            update_streak(user)
            record_attempt(ip, True)
            return redirect(request.args.get('next') or url_for('dashboard'))
        record_attempt(ip, False)
        return render_template('login.html', error='Credenciais inválidas.', captcha_question=generate_captcha() if should_show_captcha(ip) else None, recaptcha_site_key=RECAPTCHA_SITE_KEY)
    ip = get_client_ip()
    return render_template('login.html', captcha_question=generate_captcha() if should_show_captcha(ip) else None, recaptcha_site_key=RECAPTCHA_SITE_KEY)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        ip = get_client_ip()
        if not check_rate_limit(ip):
            return render_template('login.html', registering=True, error='Muitas tentativas. Aguarde alguns minutos.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if not validate_csrf():
            return render_template('login.html', registering=True, error='Token inválido. Recarregue a página.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        need_captcha = should_show_captcha(ip)
        if need_captcha and not validate_captcha(request.form.get('captcha')):
            record_attempt(ip, False)
            return render_template('login.html', registering=True, error='Captcha incorreto.', captcha_question=generate_captcha(), recaptcha_site_key=RECAPTCHA_SITE_KEY)
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        captcha_q = generate_captcha() if should_show_captcha(ip) else None
        if len(username) < 3 or len(username) > 80:
            return render_template('login.html', registering=True, error='Usuário deve ter 3-80 caracteres.', captcha_question=captcha_q, recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if not email or '@' not in email:
            return render_template('login.html', registering=True, error='E-mail inválido.', captcha_question=captcha_q, recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if len(password) < 4:
            return render_template('login.html', registering=True, error='Senha deve ter no mínimo 4 caracteres.', captcha_question=captcha_q, recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if password != confirm:
            return render_template('login.html', registering=True, error='Senhas não conferem.', captcha_question=captcha_q, recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if User.query.filter_by(username=username).first():
            return render_template('login.html', registering=True, error='Usuário já existe.', captcha_question=captcha_q, recaptcha_site_key=RECAPTCHA_SITE_KEY)
        if User.query.filter_by(email=email).first():
            return render_template('login.html', registering=True, error='E-mail já cadastrado.', captcha_question=captcha_q, recaptcha_site_key=RECAPTCHA_SITE_KEY)
        token = secrets.token_urlsafe(48)
        user = User(username=username, email=email, password=generate_password_hash(password), verification_token=token, streak_freezes=3)
        db.session.add(user)
        db.session.commit()
        base_url = request.host_url.rstrip('/')
        verify_link = f'{base_url}/verify-email/{token}'
        send_email(email, 'Confirme seu e-mail - Diário Reduzido',
            f'Olá {username},\n\nConfirme seu e-mail clicando no link abaixo:\n{verify_link}\n\nSe não foi você que criou esta conta, ignore esta mensagem.')
        session['user_id'] = user.id
        update_streak(user)
        record_attempt(ip, True)
        return redirect(url_for('dashboard'))
    ip = get_client_ip()
    return render_template('login.html', registering=True, captcha_question=generate_captcha() if should_show_captcha(ip) else None, recaptcha_site_key=RECAPTCHA_SITE_KEY)

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
    posts = Post.query.order_by(Post.publication_date.desc().nullslast()).all()
    fav_post_ids = {f.post_id for f in user.favorites} if user else set()
    return render_template('archive.html', posts=posts, user=user, fav_post_ids=fav_post_ids)

@app.route('/post/<int:id>')
def view_post(id):
    post = db.session.get(Post, id)
    if post is None:
        abort(404)
    user = get_current_user()
    fav_ids = {f.post_id for f in user.favorites} if user else set()
    if post:
        if post.content:
            post.content = render_md(post.content)
        if post.commentary:
            post.commentary = render_md(post.commentary)
    now = datetime.now(BRT)
    unlocked_themes = get_unlocked_themes(user)
    latest_posts = Post.query.order_by(Post.publication_date.desc().nullslast()).limit(5).all() if user else []
    cidadao_pct = min(100, int(((user.streak_count or 0) / 90) * 100)) if user else 0
    return render_template('index.html', post=post, user=user, user_fav_ids=fav_ids,
                           unlocked_themes=unlocked_themes, now=now, latest_posts=latest_posts,
                           cidadao_pct=cidadao_pct, streak_freezes=user.streak_freezes or 0 if user else 0)

@app.route('/search-date', methods=['POST'])
@login_required
def search_date():
    if not validate_csrf():
        return render_template('login.html', error='Token inválido. Faça login novamente.')
    user = get_current_user()
    date_str = request.form.get('date')
    fav_ids = {f.post_id for f in user.favorites} if user else set()
    if not date_str:
        return render_template('index.html', post=Post.query.order_by(Post.publication_date.desc().nullslast()).first(), user=user, error='Selecione uma data.', user_fav_ids=fav_ids, unlocked_themes=get_unlocked_themes(user), now=datetime.now(BRT), latest_posts=[])
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return render_template('index.html', post=Post.query.order_by(Post.publication_date.desc().nullslast()).first(), user=user, error='Data inválida.', user_fav_ids=fav_ids, unlocked_themes=get_unlocked_themes(user), now=datetime.now(BRT), latest_posts=[])
    if not user.is_paid and user.requests_made >= 1:
        return render_template('index.html', post=Post.query.order_by(Post.publication_date.desc().nullslast()).first(), user=user,
            error='Limite atingido. Faça uma doação para pedidos ilimitados.', user_fav_ids=fav_ids, unlocked_themes=get_unlocked_themes(user), now=datetime.now(BRT), latest_posts=[])
    pdf_link, api_pub_date = search_diary_by_date(target_date)
    if not pdf_link:
        return render_template('index.html', post=Post.query.order_by(Post.publication_date.desc().nullslast()).first(), user=user,
            error=f'Nenhum diário encontrado para {target_date.strftime("%d/%m/%Y")}.', user_fav_ids=fav_ids,
            unlocked_themes=get_unlocked_themes(user), now=datetime.now(BRT), latest_posts=[])
    try:
        pdf_content = requests.get(pdf_link, timeout=60).content
        raw_text, model_name = GeminiClient().process_pdf(pdf_content)
        title, content, commentary, ai_pub_date = parse_content(raw_text)
        new_post = Post(
            title=title, content=content, summary=generate_summary(content),
            commentary=commentary, model=model_name, pdf_link=pdf_link,
            date=datetime.combine(target_date, datetime.min.time().replace(tzinfo=BRT)),
            publication_date=ai_pub_date or api_pub_date or target_date
        )
        db.session.add(new_post)
        user.requests_made += 1
        db.session.commit()
        new_post.content = render_md(new_post.content)
        if new_post.commentary:
            new_post.commentary = render_md(new_post.commentary)
        return redirect(url_for('view_post', id=new_post.id))
    except Exception as e:
        print(f"Erro durante o processamento: {e}")
        db.session.rollback()
        return render_template('index.html', post=Post.query.order_by(Post.publication_date.desc().nullslast()).first(), user=user, error=str(e), user_fav_ids=fav_ids, unlocked_themes=get_unlocked_themes(user), now=datetime.now(BRT), latest_posts=[])

@app.route('/favorite/<int:post_id>', methods=['POST'])
@login_required
def toggle_favorite(post_id):
    user = get_current_user()
    if db.session.get(Post, post_id) is None:
        abort(404)
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

@app.route('/dashboard')
@login_required
def dashboard():
    user = get_current_user()
    check_premium_expiry(user)
    latest = Post.query.order_by(Post.publication_date.desc().nullslast()).first()
    days_left = get_premium_days_left(user)
    account_created = user.id  # approximate; we don't store created_at, use id as proxy
    unlocked_themes = get_unlocked_themes(user)
    unlocked_titles = get_unlocked_titles(user)
    current_title_info = get_user_title(user)
    next_unlock = None
    if user.username != 'admin':
        streak = user.streak_count or 0
        for req_streak, info in sorted(STREAK_THEMES.items()):
            if streak < req_streak:
                next_unlock = (req_streak, info[1])
                break
    else:
        streak = 999
    cidadao_pct = min(100, int((streak / 90) * 100))
    purchasable_themes = get_purchasable_themes(user)
    purchasable_badges = get_purchasable_badges(user)
    return render_template('dashboard.html', user=user, latest=latest, days_left=days_left,
                           FREE_MONTH_POINTS=FREE_MONTH_POINTS, unlocked_themes=unlocked_themes,
                           unlocked_titles=unlocked_titles, current_title_info=current_title_info,
                           next_unlock=next_unlock, cidadao_pct=cidadao_pct,
                           streak_freezes=user.streak_freezes or 0,
                           purchasable_themes=purchasable_themes, purchasable_badges=purchasable_badges)

@app.route('/coffee')
def coffee_redirect():
    return redirect(url_for('plans'))

@app.route('/planos')
def plans():
    has_asaas = bool(os.getenv('ASAAS_API_KEY'))
    user = get_current_user()
    return render_template('coffee.html', has_asaas=has_asaas, user=user)

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
        '1dia': (10.00, '1 Dia - Diário Reduzido'),
        '1mes': (30.00, '1 Mês - Diário Reduzido'),
        '3meses': (40.00, '3 Meses - Diário Reduzido'),
        '6meses': (60.00, '6 Meses - Diário Reduzido'),
        '12meses': (108.00, 'Anual - Diário Reduzido'),
        'freeze1': (5.00, '1 Congelamento de Streak'),
        'freeze3': (12.00, '3 Congelamentos de Streak'),
        'freeze5': (18.00, '5 Congelamentos de Streak'),
    }
    for tid, (tname, _) in STREAK_THEMES.items():
        plans_map[f'theme_{tid}'] = (get_theme_price(tid, user.streak_count or 0), f'Tema: {tname}')
    for bid, (bname, bemoji) in BADGES.items():
        plans_map[f'badge_{bid}'] = (BADGE_PRICE, f'Distintivo: {bemoji} {bname}')
    for ckey, cinfo in COMBOS.items():
        plans_map[ckey] = (cinfo['price'], cinfo['name'] + ' - ' + cinfo['desc'])
    if plan not in plans_map or not name or not email or not cpf:
        return jsonify({'error': 'Dados inválidos.'}), 400
    if billing_type not in ('card', 'pix', 'boleto'):
        return jsonify({'error': 'Forma de pagamento inválida.'}), 400
    value, description = plans_map[plan]
    card_data = None
    if billing_type == 'card':
        card_holder = request.form.get('card_holder_name', '').strip()
        card_number = re.sub(r'\D', '', request.form.get('card_number', ''))
        card_expiry = re.sub(r'\D', '', request.form.get('card_expiry', ''))
        card_cvv = re.sub(r'\D', '', request.form.get('card_cvv', ''))
        postal_code = re.sub(r'\D', '', request.form.get('postal_code', ''))
        address_number = request.form.get('address_number', '').strip()
        phone = re.sub(r'\D', '', request.form.get('phone', ''))
        if not all([card_holder, card_number, card_expiry, card_cvv, postal_code, address_number, phone]):
            return jsonify({'error': 'Dados do cartão incompletos.'}), 400
        if len(card_number) < 13 or len(card_expiry) != 4 or len(card_cvv) < 3:
            return jsonify({'error': 'Dados do cartão inválidos.'}), 400
        card_data = {
            'creditCard': {
                'holderName': card_holder,
                'number': card_number,
                'expiryMonth': card_expiry[:2],
                'expiryYear': f'20{card_expiry[2:]}',
                'ccv': card_cvv,
            },
            'holderInfo': {
                'name': name,
                'email': email,
                'cpfCnpj': re.sub(r'\D', '', cpf),
                'postalCode': postal_code,
                'addressNumber': address_number,
                'phone': phone,
            },
        }
    try:
        customer_id = create_customer(name, email, cpf)
        external_ref = f'{user.id}_{plan}'
        base_url = request.host_url.rstrip('/')
        callback_url = f'{base_url}/pagamento/sucesso'
        remote_ip = request.remote_addr or ''
        credit_card_token = None
        if billing_type == 'card':
            token_resp = tokenize_credit_card(customer_id, card_data['creditCard'], card_data['holderInfo'], remote_ip)
            credit_card_token = token_resp.get('creditCardToken', '')
            if not credit_card_token:
                return jsonify({'error': 'Não foi possível validar o cartão. Verifique os dados e tente novamente.'}), 400
        payment = create_payment(customer_id, value, description, external_ref, billing_type=billing_type, callback_url=callback_url, credit_card_token=credit_card_token, remote_ip=remote_ip)
        if billing_type == 'pix':
            return jsonify({
                'method': 'pix',
                'payment_id': payment.get('id', ''),
                'encoded_image': payment.get('encodedImage', payment.get('pixQrCode', '')),
                'payload': payment.get('payload', payment.get('pixCopiaECola', '')),
                'value': value,
            })
        if billing_type == 'card':
            return jsonify({
                'method': 'card',
                'payment_id': payment.get('id', ''),
                'status': payment.get('status', 'PENDING'),
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
        target = db.session.get(User, user_id)
        if target:
            plan_key = payload.get('payment', {}).get('externalReference', '').split('_')[-1]
            value = PLAN_VALUES.get(plan_key, 0)
            if plan_key in COMBOS:
                combo = COMBOS[plan_key]
                value = combo['price']
                if not target.first_purchase_done:
                    target.first_purchase_done = True
                    value_days = 1
                else:
                    value_days = 0
                base_days = PLAN_DAYS.get(combo['plan'], 30)
                target.is_paid = True
                now = datetime.now(BRT)
                total_days = base_days + value_days
                if target.paid_until and target.paid_until > now:
                    target.paid_until += timedelta(days=total_days)
                else:
                    target.paid_until = now + timedelta(days=total_days)
                purchased_themes = set()
                if target.purchased_themes:
                    purchased_themes = set(t.strip() for t in target.purchased_themes.split(',') if t.strip())
                for theme_id in combo['themes']:
                    purchased_themes.add(theme_id)
                target.purchased_themes = ','.join(sorted(purchased_themes))
                if combo['freezes']:
                    target.streak_freezes = (target.streak_freezes or 0) + combo['freezes']
                target.points = (target.points or 0) + int(value)
                while target.points >= FREE_MONTH_POINTS:
                    target.points -= FREE_MONTH_POINTS
                    if target.paid_until and target.paid_until > now:
                        target.paid_until += timedelta(days=30)
                    else:
                        target.paid_until = now + timedelta(days=30)
                db.session.commit()
                print(f'Combo {plan_key} confirmado para usuário {user_id}: {total_days} dias, temas {combo["themes"]}, {combo["freezes"]} freezes')
            elif plan_key in ('freeze1', 'freeze3', 'freeze5'):
                freeze_count = 1 if plan_key == 'freeze1' else (3 if plan_key == 'freeze3' else 5)
                target.streak_freezes = (target.streak_freezes or 0) + freeze_count
                target.points = (target.points or 0) + int(value)
                db.session.commit()
                print(f'Streak freezes comprados para usuário {user_id}: +{freeze_count} (total: {target.streak_freezes})')
            elif plan_key.startswith('theme_'):
                theme_id = plan_key[6:]
                purchased = set()
                if target.purchased_themes:
                    purchased = set(t.strip() for t in target.purchased_themes.split(',') if t.strip())
                purchased.add(theme_id)
                target.purchased_themes = ','.join(sorted(purchased))
                target.points = (target.points or 0) + int(value)
                if not target.first_purchase_done:
                    target.first_purchase_done = True
                    days = 1
                    target.is_paid = True
                    now = datetime.now(BRT)
                    if target.paid_until and target.paid_until > now:
                        target.paid_until += timedelta(days=days)
                    else:
                        target.paid_until = now + timedelta(days=days)
                db.session.commit()
                print(f'Tema comprado para usuário {user_id}: {theme_id}')
            elif plan_key.startswith('badge_'):
                badge_id = plan_key[6:]
                purchased = set()
                if target.purchased_badges:
                    purchased = set(b.strip() for b in target.purchased_badges.split(',') if b.strip())
                purchased.add(badge_id)
                target.purchased_badges = ','.join(sorted(purchased))
                target.badge = badge_id
                target.points = (target.points or 0) + int(value)
                if not target.first_purchase_done:
                    target.first_purchase_done = True
                    days = 1
                    target.is_paid = True
                    now = datetime.now(BRT)
                    if target.paid_until and target.paid_until > now:
                        target.paid_until += timedelta(days=days)
                    else:
                        target.paid_until = now + timedelta(days=days)
                db.session.commit()
                print(f'Distintivo comprado para usuário {user_id}: {badge_id}')
            else:
                days = PLAN_DAYS.get(plan_key, 30)
                if not target.first_purchase_done:
                    target.first_purchase_done = True
                    days += 1
                target.is_paid = True
                now = datetime.now(BRT)
                if target.paid_until and target.paid_until > now:
                    target.paid_until += timedelta(days=days)
                else:
                    target.paid_until = now + timedelta(days=days)
                target.points = (target.points or 0) + int(value)
                while target.points >= FREE_MONTH_POINTS:
                    target.points -= FREE_MONTH_POINTS
                    if target.paid_until and target.paid_until > now:
                        target.paid_until += timedelta(days=30)
                    else:
                        target.paid_until = now + timedelta(days=30)
                db.session.commit()
                print(f'Pagamento confirmado para usuário {user_id}, plano {plan_key}, {days} dias adicionados')
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
        title, content, commentary, ai_pub_date = parse_content(raw_text)
        post.title = title
        post.content = content
        post.commentary = commentary
        post.model = model_name
        if ai_pub_date:
            post.publication_date = ai_pub_date
        db.session.commit()
        print(f'Post {post.id} reprocessado com sucesso')
        return jsonify({'status': 'success', 'title': title})
    except Exception as e:
        db.session.rollback()
        print(f'Erro ao reprocessar: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/migrate-content')
@login_required
def migrate_existing_posts_route():
    user = get_current_user()
    if user.username != 'admin':
        return jsonify({'error': 'Apenas admin'}), 403
    count = migrate_existing_posts()
    return jsonify({'migrated': count})

@app.route('/pagamento/sucesso')
def pagamento_sucesso():
    return render_template('pagamento.html', sucesso=True)

@app.route('/pagamento/falha')
def pagamento_falha():
    return render_template('pagamento.html', sucesso=False)

@app.route('/share/<int:post_id>')
def share_post(post_id):
    post = db.session.get(Post, post_id)
    if post is None:
        abort(404)
    now = datetime.now(BRT)
    post_date = post.date
    if post_date.tzinfo is None:
        post_date = post_date.replace(tzinfo=BRT)
    if post_date > now:
        return render_template('index.html', post=post, user=None, user_fav_ids=set(),
                               error='Esta edição ainda não pode ser compartilhada.')
    title = post.title
    import re as _re
    plain = _re.sub(r'<[^>]+>', '', post.content or '')
    plain = _re.sub(r'\s+', ' ', plain).strip()
    summary = plain[:200]
    if len(plain) > 200:
        summary += '...'
    domain = request.host_url.rstrip('/')
    article_url = f'{domain}/post/{post.id}'
    return render_template('share.html', post=post, title=title, summary=summary, article_url=article_url, user=get_current_user())

@app.route('/comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    if not validate_csrf():
        return jsonify({'error': 'Token inválido.'}), 400
    user = get_current_user()
    post = db.session.get(Post, post_id)
    if post is None:
        abort(404)
    content = request.form.get('content', '').strip()
    if not content or len(content) < 2:
        return jsonify({'error': 'Comentário deve ter pelo menos 2 caracteres.'}), 400
    if len(content) > 1000:
        return jsonify({'error': 'Comentário muito longo (máx 1000 caracteres).'}), 400
    comment = Comment(content=content, author=user, post=post)
    db.session.add(comment)
    db.session.commit()
    return redirect(request.referrer or url_for('index') + '#comments')

@app.route('/comment/<int:comment_id>/edit', methods=['POST'])
@login_required
def edit_comment(comment_id):
    if not validate_csrf():
        return jsonify({'error': 'Token inválido.'}), 400
    user = get_current_user()
    comment = db.session.get(Comment, comment_id)
    if comment is None:
        abort(404)
    if comment.author != user and user.username != 'admin':
        return jsonify({'error': 'Permissão negada.'}), 403
    content = request.form.get('content', '').strip()
    if not content or len(content) < 2:
        return jsonify({'error': 'Mínimo 2 caracteres.'}), 400
    if len(content) > 1000:
        return jsonify({'error': 'Máximo 1000 caracteres.'}), 400
    comment.content = content
    comment.edited_at = datetime.now(BRT)
    db.session.commit()
    return redirect(request.referrer or url_for('index') + '#comments')

@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    if not validate_csrf():
        return jsonify({'error': 'Token inválido.'}), 400
    user = get_current_user()
    comment = db.session.get(Comment, comment_id)
    if comment is None:
        abort(404)
    if comment.author != user and user.username != 'admin':
        return jsonify({'error': 'Permissão negada.'}), 403
    db.session.delete(comment)
    db.session.commit()
    return redirect(request.referrer or url_for('index') + '#comments')

@app.route('/comment/<int:comment_id>/reply', methods=['POST'])
@login_required
def reply_comment(comment_id):
    if not validate_csrf():
        return jsonify({'error': 'Token inválido.'}), 400
    user = get_current_user()
    parent = db.session.get(Comment, comment_id)
    if parent is None:
        abort(404)
    content = request.form.get('content', '').strip()
    if not content or len(content) < 2:
        return jsonify({'error': 'Mínimo 2 caracteres.'}), 400
    if len(content) > 1000:
        return jsonify({'error': 'Máximo 1000 caracteres.'}), 400
    reply = Comment(content=content, author=user, post=parent.post, parent_id=parent.id)
    db.session.add(reply)
    db.session.commit()
    return redirect(request.referrer or url_for('index') + '#comments')

@app.route('/theme', methods=['POST'])
@login_required
def update_theme():
    if not validate_csrf():
        return jsonify({'error': 'Token inválido.'}), 400
    user = get_current_user()
    theme = request.form.get('theme', 'newspaper')
    unlocked = {t[0] for t in get_unlocked_themes(user)}
    if theme not in unlocked:
        return jsonify({'error': 'Tema não disponível.'}), 400
    user.theme = theme
    db.session.commit()
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/update-title', methods=['POST'])
@login_required
def update_title():
    if not validate_csrf():
        return jsonify({'error': 'Token inválido.'}), 400
    user = get_current_user()
    new_title = request.form.get('title', '').strip()
    unlocked = [t[1] for t in get_unlocked_titles(user)]
    if new_title and new_title not in unlocked:
        return jsonify({'error': 'Título não disponível.'}), 400
    user.title = new_title if new_title else None
    db.session.commit()
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/update-badge', methods=['POST'])
@login_required
def update_badge():
    if not validate_csrf():
        return jsonify({'error': 'Token inválido.'}), 400
    user = get_current_user()
    badge_id = request.form.get('badge', '').strip()
    owned_badges = set()
    if user.purchased_badges:
        owned_badges = set(b.strip() for b in user.purchased_badges.split(',') if b.strip())
    pioneer = AppConfig.query.filter_by(key='first_365_user_id').first()
    if pioneer and pioneer.value and str(user.id) == pioneer.value:
        owned_badges.add('pioneer')
    if user.username == 'admin':
        owned_badges.update(bid for bid, _, _, _ in get_purchasable_badges(user))
    if badge_id and badge_id not in owned_badges:
        return jsonify({'error': 'Distintivo não disponível.'}), 400
    user.badge = badge_id if badge_id else None
    db.session.commit()
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/update-font', methods=['POST'])
@login_required
def update_font():
    if not validate_csrf():
        return jsonify({'error': 'Token inválido.'}), 400
    user = get_current_user()
    font_id = request.form.get('font', '').strip()
    unlocked = [f[0] for f in get_unlocked_fonts(user)]
    if font_id and font_id not in unlocked:
        return jsonify({'error': 'Fonte não disponível.'}), 400
    user.font = font_id if font_id != 'default' else None
    db.session.commit()
    return redirect(request.referrer or url_for('dashboard'))

app.jinja_env.globals.update(get_user_title=get_user_title, BADGES=BADGES, STREAK_THEMES=STREAK_THEMES, get_unlocked_themes=get_unlocked_themes, get_theme_price=get_theme_price, STREAK_FONTS=STREAK_FONTS, get_unlocked_fonts=get_unlocked_fonts, get_font_css=get_font_css, get_font_name=get_font_name, COMBOS=COMBOS, get_all_font_urls=get_all_font_urls, get_user_font_url=get_user_font_url, PLAN_VALUES=PLAN_VALUES, PLAN_DAYS=PLAN_DAYS, BADGE_PRICE=BADGE_PRICE, PIX_PAYLOAD=PIX_PAYLOAD, PIX_QR_IMAGE=PIX_QR_IMAGE)

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true', port=5000)
