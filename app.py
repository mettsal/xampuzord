# app.py - Main Flask Application
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, Response, abort, g, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event, inspect as sa_inspect, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value
from feedgen.feed import FeedGenerator
from PIL import Image
from datetime import datetime, timezone
from collections import defaultdict
from functools import wraps
from pathlib import Path
import json
import urllib.parse
import urllib.request
import bleach
import os
import re
import unicodedata
import uuid

# Initialize Flask app
app = Flask(__name__)

# Load configuration from config.py. FLASK_ENV selects dev/production/testing,
# so the cookie/debug hardening in ProductionConfig actually takes effect.
from config import config
config_name = os.environ.get('FLASK_ENV', 'development')
app.config.from_object(config.get(config_name, config['default']))

# Keep the teaser upload path consistent with the path save_teaser_image() returns.
app.config['UPLOAD_FOLDER'] = 'static/uploads/teasers'

# Fail closed: never run production signed with a publicly-known SECRET_KEY.
_WEAK_SECRET_KEYS = {
    'cyber-poetry-secret-key-change-in-production',
    'cyber-poetry-dev-key-change-in-production',
}
if config_name == 'production' and app.config.get('SECRET_KEY') in _WEAK_SECRET_KEYS:
    raise RuntimeError(
        'SECRET_KEY inseguro em produção. Defina a variável de ambiente SECRET_KEY '
        'com uma chave forte: python -c "import secrets; print(secrets.token_hex(32))"'
    )

# Fix for Heroku-style Postgres URL
if app.config.get('SQLALCHEMY_DATABASE_URI', '').startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
csrf = CSRFProtect(app)

_LOOPBACK = {'127.0.0.1', '::1'}

def client_ip():
    """IP real do visitante, chave do rate limit.

    O Cloudflare Tunnel entrega tudo em 127.0.0.1:5000 — sem isto, a internet
    inteira dividiria um contador só (e 5 cadastros/hora valeriam para todos).
    O cloudflared é o único que fala com o loopback, e a Cloudflare sobrescreve
    CF-Connecting-IP; fora do loopback o header é ignorado (seria forjável).
    """
    if (request.remote_addr or '') in _LOOPBACK:
        forwarded = request.headers.get('CF-Connecting-IP', '').strip()
        if forwarded:
            return forwarded
    return get_remote_address()

# Rate limit só nas rotas de escrita (limites explícitos nos decorators):
# leitura (home, posts, feeds, API de scroll) fica livre.
limiter = Limiter(
    app=app,
    key_func=client_ip,
    storage_uri="memory://"
)

def utcnow():
    """UTC naive: mesmo valor do deprecado datetime.utcnow(), sem mudar
    o schema — as colunas DateTime do SQLite seguem naive."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

# ============= MODELS =============

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    settings = db.Column(db.JSON, default=lambda: {'font': 'Consolas', 'theme': 'light'})
    posts = db.relationship('Post', backref='author', lazy=True)
    is_admin = db.Column(db.Boolean, default=False)
    # Bloqueado pelo painel admin: sessões caem (load_user) e o login é recusado.
    is_banned = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    created_at = db.Column(db.DateTime, default=utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body_html = db.Column(db.Text, nullable=False)
    # Fonte Markdown do post (o que o autor digitou no editor). NULL em posts
    # legados/importados — o editor cai no fallback body_html nesses casos.
    body_md = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    tags = db.Column(db.JSON, default=list)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    views = db.Column(db.Integer, default=0)
    font = db.Column(db.String(50), default='Consolas')
    teaser_image = db.Column(db.String(200), nullable=True)  # Path to teaser image
    teaser_type = db.Column(db.String(20), default='auto')  # 'image', 'auto', or 'none'
    post_theme = db.Column(db.String(50), default='inherit')  # Theme: inherit, dark, light, cyberpunk, matrix, etc.
    # Arquivo de origem em poesia/ (ex. '2019/caveira.txt'); NULL em posts do
    # editor. Liga o post ao painel /admin/acervo.
    source_path = db.Column(db.String(500), nullable=True, index=True)
    # Oculto pelo painel do acervo: some de home, busca, feeds, arquivo e
    # contagens de Tag, mas mantém views/curtidas/comentários. Só admin vê.
    hidden = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    # URL do post (/post/<slug>), gerado do título em assign_post_slugs();
    # /post/<id> e slugs antigos (PostSlugAlias) redirecionam para cá.
    slug = db.Column(db.String(80), unique=True, index=True)
    slug_aliases = db.relationship('PostSlugAlias', backref='post', lazy=True,
                                   cascade='all, delete-orphan')
    # Interações passivas morrem junto com o post (cascade)
    likes = db.relationship('Like', backref='post', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='post', lazy=True,
                               cascade='all, delete-orphan', order_by='Comment.created_at')
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'body_html': self.body_html,
            'created_at': self.created_at.isoformat(),
            'tags': self.tags,
            'author': self.author.username,
            'views': self.views,
            'font': self.font,
            'teaser_image': self.teaser_image,
            'teaser_type': self.teaser_type,
            'post_theme': self.post_theme,
            'slug': self.slug,
        }

class SiteSetting(db.Model):
    """Interruptores do site (painel admin → Site). Valor '1'/'0'."""
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(200), nullable=False)

class PostSlugAlias(db.Model):
    """Slug antigo de um post cujo título mudou: o link velho continua valendo (301)."""
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'year', 'genre', etc.
    count = db.Column(db.Integer, default=0)

class Like(db.Model):
    """Curtida anônima: um por post por visitante (UUID gerado no navegador)."""
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    visitor_id = db.Column(db.String(36), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    __table_args__ = (db.UniqueConstraint('post_id', 'visitor_id'),)

class Comment(db.Model):
    """Comentário de usuário logado; publica direto, admin pode deletar."""
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    author = db.relationship('User', backref='comments')

class Testimonial(db.Model):
    """Depoimento (guestbook) de usuário logado; admin pode deletar."""
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    author = db.relationship('User', backref='testimonials')

class GalleryItem(db.Model):
    """Imagem da página Galeria; upload reaproveita save_teaser_image()."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    image_path = db.Column(db.String(200), nullable=False)  # path relativo a /static/, como Post.teaser_image
    caption = db.Column(db.Text, nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    author = db.relationship('User', backref='gallery_items')

# ============= HELPERS =============

@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    return None if user is None or user.is_banned else user

def admin_required(view):
    """login_required + is_admin; API responde 403 JSON, página redireciona."""
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Acesso restrito a admins'}), 403
            flash('Acesso restrito a admins')
            return redirect(url_for('index'))
        return view(*args, **kwargs)
    return wrapper

# ============= INTERRUPTORES DO SITE =============

SITE_SWITCHES = {
    'registration_open': ('Cadastro de pseudônimos', True),
    'comments_open': ('Comentários nos poemas', True),
    'testimonials_open': ('Depoimentos (guestbook)', True),
}

def setting(key):
    """Interruptor do site (bool), lido uma vez por request."""
    if '_site_settings' not in g:
        g._site_settings = {row.key: row.value == '1' for row in SiteSetting.query}
    return g._site_settings.get(key, SITE_SWITCHES[key][1])

app.jinja_env.globals['setting'] = setting

# ============= CAPTCHA (honeypot + Cloudflare Turnstile opcional) =============

HONEYPOT_FIELD = 'website'  # invisível para gente; bot que preenche tudo cai aqui
TURNSTILE_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'

def turnstile_site_key():
    """Chave pública do Turnstile, só quando as duas chaves estão no .env."""
    site, secret = os.environ.get('TURNSTILE_SITE_KEY'), os.environ.get('TURNSTILE_SECRET_KEY')
    return site if site and secret else None

app.jinja_env.globals['turnstile_site_key'] = turnstile_site_key

def verify_turnstile(token):
    """Valida o token com a Cloudflare. Falha de rede = recusa (fail closed)."""
    if not token:
        return False
    payload = urllib.parse.urlencode({
        'secret': os.environ.get('TURNSTILE_SECRET_KEY', ''),
        'response': token,
        'remoteip': client_ip(),
    }).encode()
    try:
        with urllib.request.urlopen(TURNSTILE_VERIFY_URL, data=payload, timeout=5) as res:
            return bool(json.loads(res.read()).get('success'))
    except Exception:
        app.logger.exception('Turnstile: verificação falhou')
        return False

def sanitize_html(html_content):
    """Sanitize HTML content to prevent XSS and auto-wrap in <pre><code>"""
    allowed_tags = [
        'p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'blockquote', 'code', 'pre', 'ul', 'ol', 'li', 'a', 'img', 'span', 'div'
    ]
    # No 'style' attribute: bleach 6 does not sanitize inline CSS without a
    # css_sanitizer, so allowing it enables CSS-injection / UI-redress attacks.
    allowed_attrs = {
        'a': ['href', 'title'],
        'img': ['src', 'alt', 'width', 'height'],
        'div': ['class'],
        'pre': ['class'],
        'code': ['class']
    }

    # Clean against the allowlist; restrict URL protocols so javascript:/data:
    # cannot ride in on href/src; drop disallowed tags entirely.
    cleaned = bleach.clean(
        html_content,
        tags=allowed_tags,
        attributes=allowed_attrs,
        protocols=['http', 'https', 'mailto'],
        strip=True,
    )

    # Auto-wrap entire content in <pre><code> if not already wrapped
    # Check if content already starts with <pre> or <code>
    stripped = cleaned.strip()
    if not (stripped.startswith('<pre') or stripped.startswith('<code')):
        cleaned = f'<pre><code>{cleaned}</code></pre>'

    return cleaned

def process_tags(tag_string, count=True):
    """Process comma-separated tags into JSON format.

    count=False só monta a lista, sem mexer em Tag.count (post oculto não
    conta nas contagens públicas)."""
    tags = []
    for tag in tag_string.split(','):
        tag = tag.strip()
        if tag:
            # Check if it's a year
            tag_type = 'year' if tag.isdigit() and len(tag) == 4 else 'genre'
            tags.append({'type': tag_type, 'value': tag})
            if not count:
                continue

            # Update global tag count
            tag_obj = Tag.query.filter_by(name=tag).first()
            if not tag_obj:
                tag_obj = Tag(name=tag, type=tag_type, count=1)
                db.session.add(tag_obj)
            else:
                tag_obj.count += 1
    return tags

def decrement_tags(tags_list):
    """Decrement global Tag counts for a list of [{'type','value'}] dicts.

    Called when a post's tags are removed (delete) or replaced (edit) so the
    aggregate Tag.count stays accurate. Rows that reach zero are removed.
    """
    for tag in tags_list or []:
        name = tag.get('value') if isinstance(tag, dict) else None
        if not name:
            continue
        tag_obj = Tag.query.filter_by(name=name).first()
        if tag_obj:
            tag_obj.count = max(0, tag_obj.count - 1)
            if tag_obj.count == 0:
                db.session.delete(tag_obj)

def increment_tags(tags_list):
    """Inverso de decrement_tags: post oculto voltando ao site."""
    process_tags(', '.join(t['value'] for t in tags_list or []
                           if isinstance(t, dict) and t.get('value')))

def public_posts():
    """Post.query sem os ocultos — base de tudo que o público vê."""
    return Post.query.filter(Post.hidden.is_(False))

def ensure_visible(post):
    """Post oculto é 404 para todo mundo menos admin."""
    if post.hidden and not (current_user.is_authenticated and current_user.is_admin):
        abort(404)
    return post

def get_visible_post_or_404(post_id):
    return ensure_visible(db.get_or_404(Post, post_id))

# ============= SLUGS (/post/<slug>) =============

SLUG_MAX = 80
RESERVED_SLUGS = {'new'}  # /post/new é o editor

def slugify(text):
    """'xampu é o quê não é' -> 'xampu-e-o-que-nao-e'.

    Título sem nenhuma letra ('☆', '500', '¿¿¿') -> '' e o post vira
    poema-<id> (ver slug_base): número puro colidiria com /post/<id>."""
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    if len(text) > SLUG_MAX:
        cut = text[:SLUG_MAX]
        text = (cut.rsplit('-', 1)[0] if '-' in cut else cut).strip('-')
    if not re.search('[a-z]', text):
        return ''
    if text in RESERVED_SLUGS:
        return f'poema-{text}'
    return text

def slug_base(title, post_id):
    """Slug desejado; '' se o título não tem letras e o id ainda não existe."""
    return slugify(title) or (f'poema-{post_id}' if post_id else '')

def _unique_slug(session, base, post_id, taken):
    """base, base-2, base-3… livre no banco e no flush corrente."""
    candidate, n = base, 1
    while True:
        if candidate not in taken:
            other = session.query(Post.id).filter(Post.slug == candidate).first()
            if other is None or other.id == post_id:
                return candidate
        n += 1
        suffix = f'-{n}'
        candidate = base[:SLUG_MAX - len(suffix)].rstrip('-') + suffix

@event.listens_for(Session, 'before_flush')
def assign_post_slugs(session, flush_context, instances):
    """Todo caminho de criação (editor, importador, publish_inbox, painel do
    acervo) ganha slug aqui. Título editado -> slug novo, e o antigo vira
    PostSlugAlias para os links já compartilhados não quebrarem."""
    taken = set()
    with session.no_autoflush:
        for obj in list(session.new):
            if isinstance(obj, Post) and not obj.slug:
                base = slugify(obj.title)
                if base:  # sem letras: fica para slug_from_id, quando houver id
                    obj.slug = _unique_slug(session, base, None, taken)
                    taken.add(obj.slug)
        for obj in list(session.dirty):
            if not isinstance(obj, Post) or obj in session.deleted:
                continue
            history = sa_inspect(obj).attrs.title.history
            if obj.slug and not history.has_changes():
                continue
            if obj.slug and history.deleted and slugify(history.deleted[0]) == slugify(obj.title):
                continue  # mudou só caixa/acento/pontuação: mesma URL
            new_slug = _unique_slug(session, slug_base(obj.title, obj.id), obj.id, taken)
            taken.add(new_slug)
            if new_slug == obj.slug:
                continue
            if obj.slug:
                alias = session.query(PostSlugAlias).filter_by(slug=obj.slug).first()
                if alias:
                    alias.post_id = obj.id
                else:
                    session.add(PostSlugAlias(slug=obj.slug, post_id=obj.id))
            for stale in session.query(PostSlugAlias).filter_by(slug=new_slug):
                session.delete(stale)
            obj.slug = new_slug

@event.listens_for(Post, 'after_insert')
def slug_from_id(mapper, connection, target):
    """Post novo com título sem letras: poema-<id>, gravado logo após o INSERT."""
    if target.slug:
        return
    base = candidate = f'poema-{target.id}'
    n = 1
    while connection.execute(select(Post.id).where(Post.slug == candidate)).first():
        n += 1
        candidate = f'{base}-{n}'
    connection.execute(update(Post.__table__).where(Post.__table__.c.id == target.id)
                       .values(slug=candidate))
    set_committed_value(target, 'slug', candidate)

def post_url(post, **kwargs):
    """URL canônica do post (slug; id só se ainda não houver slug). Aceita
    o Post ou o dict das linhas do arquivo (build_archive_years)."""
    slug, post_id = (post.get('slug'), post['id']) if isinstance(post, dict) else (post.slug, post.id)
    if slug:
        return url_for('view_post', slug=slug, **kwargs)
    return url_for('post_by_id', post_id=post_id, **kwargs)

app.jinja_env.globals['post_url'] = post_url

MESES_PT = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro',
}

def build_archive_years():
    """Árvore Ano → Mês → Poemas da sidebar da home. Só id/title/created_at
    (sem body_html) para não carregar o conteúdo inteiro de cada post."""
    rows = (
        db.session.query(Post.id, Post.title, Post.created_at, Post.slug)
        .filter(Post.created_at.isnot(None), Post.hidden.is_(False))
        .order_by(Post.created_at.desc())
        .all()
    )
    by_year = {}
    for pid, title, created, slug in rows:
        by_year.setdefault(created.year, {}).setdefault(created.month, []).append(
            {'id': pid, 'title': title, 'slug': slug}
        )
    years = []
    for y in sorted(by_year.keys(), reverse=True):
        months_dict = by_year[y]
        months = [
            {'month': m, 'name': MESES_PT[m], 'count': len(months_dict[m]), 'posts': months_dict[m]}
            for m in sorted(months_dict.keys(), reverse=True)
        ]
        years.append({'year': y, 'count': sum(len(p) for p in months_dict.values()), 'months': months})
    return years

@app.context_processor
def inject_ribbon_data():
    """Dados do ribbon (topo de todas as páginas): total de poemas e último
    publicado. Duas queries leves (count + order_by limit 1) em toda request."""
    last_post = public_posts().order_by(Post.created_at.desc()).first()
    return dict(ribbon_post_count=public_posts().count(), ribbon_last_post=last_post)

def allowed_file(filename):
    """Check if the uploaded file is allowed"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_teaser_image(file):
    """Save uploaded teaser image and return the filename"""
    if not (file and allowed_file(file.filename)):
        return None

    # Extension check is not enough: verify the bytes are really an image so a
    # renamed HTML/script polyglot cannot be stored and served.
    try:
        file.stream.seek(0)
        Image.open(file.stream).verify()
        file.stream.seek(0)
    except Exception:
        return None

    # Generate unique filename
    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{filename}"

    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Save file
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    file.save(file_path)

    return f"uploads/teasers/{unique_filename}"

# ============= ROUTES =============

@app.route('/')
def index():
    """Main page with post grid + sidebar (arquivo ano/mês + marcadores)"""
    initial_posts = public_posts().order_by(Post.created_at.desc()).limit(9).all()
    archive_years = build_archive_years()
    tag_counts = Tag.query.order_by(Tag.count.desc()).all()
    return render_template(
        'index.html', posts=initial_posts, archive_years=archive_years, tag_counts=tag_counts
    )

def filter_by_tags(query, tags):
    """Filtra Post.query por substring case-insensitive (OR) sobre o JSON
    serializado ("ciber" casa com "cybernetic") — usado pelos feeds (semântica
    de tag exata/parcial, não busca livre). Filtro e paginação acontecem no
    banco. Seq scan aceitável nesta escala; se crescer, FTS."""
    if not tags:
        return query
    wanted = [str(t).lower() for t in tags]
    conditions = [db.cast(Post.tags, db.String).ilike(f'%{q}%') for q in wanted]
    return query.filter(db.or_(*conditions))

def filter_by_search(query, terms):
    """Busca livre usada por /api/posts (search bar): cada termo casa se
    aparecer, por substring case-insensitive, no título, nas tags (JSON
    serializado) ou no corpo (body_html) do post. Mesmo trade-off de
    filter_by_tags: seq scan com ilike, aceitável nesta escala."""
    if not terms:
        return query
    wanted = [str(t).lower() for t in terms]
    conditions = []
    for term in wanted:
        like = f'%{term}%'
        conditions.append(db.or_(
            Post.title.ilike(like),
            db.cast(Post.tags, db.String).ilike(like),
            Post.body_html.ilike(like),
        ))
    return query.filter(db.or_(*conditions))

@app.route('/api/posts')
def api_posts():
    """API endpoint for infinite scroll. `tags` aqui é a query da search bar:
    filtra por título, tags e conteúdo (ver filter_by_search)."""
    page = request.args.get('page', 1, type=int)
    tags_filter = request.args.get('tags', '[]')

    try:
        tags_filter = json.loads(tags_filter)
    except (json.JSONDecodeError, TypeError):
        tags_filter = []

    query = filter_by_search(public_posts(), tags_filter)

    posts = query.order_by(Post.created_at.desc()).paginate(
        page=page, per_page=9, error_out=False
    ).items

    return jsonify([post.to_dict() for post in posts])

@app.route('/post/<int:post_id>')
def post_by_id(post_id):
    """Link antigo por id -> URL com slug (301)."""
    post = get_visible_post_or_404(post_id)
    if not post.slug:
        return view_post_page(post)
    return redirect(post_url(post), 301)

@app.route('/post/<slug>')
def view_post(slug):
    """View single post"""
    post = Post.query.filter_by(slug=slug).first()
    if post is None:
        alias = PostSlugAlias.query.filter_by(slug=slug).first_or_404()
        return redirect(post_url(ensure_visible(alias.post)), 301)
    return view_post_page(ensure_visible(post))

CARD_CACHE_DIR = Path(app.root_path) / 'instance' / 'cards'

@app.route('/post/<slug>/card.png')
@limiter.limit("60 per minute")  # gerar cartão custa CPU (só no 1º acesso; depois é cache)
def post_card(slug):
    """Imagem de compartilhamento (og:image): o poema inteiro em 1200×630."""
    post = ensure_visible(Post.query.filter_by(slug=slug).first_or_404())
    import cards  # lazy: Pillow só carrega quando alguém compartilha
    response = send_file(cards.ensure_card(CARD_CACHE_DIR, post), mimetype='image/png')
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response

def view_post_page(post):
    """Renderiza o post (já checado por ensure_visible) e conta a view."""
    post_id = post.id
    # 1 view por post por sessão: refresh, bots sem cookie e o próprio autor
    # relendo não inflam o contador. A lista fica no cookie de sessão
    # assinado (~4KB), então guardamos só os últimos 100 ids.
    viewed = session.get('viewed_posts', [])
    if post_id not in viewed:
        post.views += 1
        db.session.commit()
        viewed.append(post_id)
        session['viewed_posts'] = viewed[-100:]
    return render_template('post.html', post=post)

@app.route('/post/new', methods=['GET', 'POST'])
@login_required
@limiter.limit("20 per hour")  # Prevent spam posting
def new_post():
    """Create new post"""
    # Apenas admins publicam: registro é aberto, mas usuário comum é read-only
    if not current_user.is_admin:
        if request.is_json:
            return jsonify({'error': 'Apenas admins podem publicar posts'}), 403
        flash('Apenas admins podem publicar posts')
        return redirect(url_for('index'))

    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        title = data.get('title', 'Untitled')
        body_html = sanitize_html(data.get('body_html', ''))
        body_md = data.get('body_md') or None
        tags = process_tags(data.get('tags', ''))
        font = data.get('font', 'Consolas')
        teaser_image = data.get('teaser_image', None)
        teaser_type = data.get('teaser_type', 'auto')
        post_theme = data.get('post_theme', 'inherit')

        post = Post(
            title=title,
            body_html=body_html,
            body_md=body_md,
            tags=tags,
            font=font,
            teaser_image=teaser_image,
            teaser_type=teaser_type,
            post_theme=post_theme,
            author_id=current_user.id
        )
        
        db.session.add(post)
        db.session.commit()
        
        if request.is_json:
            return jsonify({'success': True, 'post_id': post.id, 'url': post_url(post)})
        return redirect(post_url(post))
    
    return render_template('editor.html')

@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    """Edit existing post"""
    post = db.get_or_404(Post, post_id)
    
    # Apenas admins editam (usuário comum é read-only, inclusive os próprios posts)
    if not current_user.is_admin:
        if request.is_json:
            return jsonify({'error': 'Apenas admins podem editar posts'}), 403
        flash('Apenas admins podem editar posts')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        post.title = data.get('title', post.title)
        post.body_html = sanitize_html(data.get('body_html', post.body_html))
        post.body_md = data.get('body_md') or post.body_md
        # Release the old tags' counts before re-processing so edits don't inflate them
        # (post oculto não está nas contagens: nem tira nem põe)
        if not post.hidden:
            decrement_tags(post.tags)
        post.tags = process_tags(data.get('tags', ''), count=not post.hidden)
        post.font = data.get('font', post.font)
        post.teaser_image = data.get('teaser_image', post.teaser_image)
        post.teaser_type = data.get('teaser_type', post.teaser_type)
        post.post_theme = data.get('post_theme', post.post_theme)
        post.updated_at = utcnow()
        
        db.session.commit()
        
        if request.is_json:
            return jsonify({'success': True, 'post_id': post.id, 'url': post_url(post)})
        return redirect(post_url(post))
    
    return render_template('editor.html', post=post)

@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    """Delete existing post"""
    post = db.get_or_404(Post, post_id)

    # Apenas admins deletam (usuário comum é read-only, inclusive os próprios posts)
    if not current_user.is_admin:
        if request.is_json:
            return jsonify({'error': 'Apenas admins podem deletar posts'}), 403
        flash('Apenas admins podem deletar posts')
        return redirect(url_for('post_by_id', post_id=post_id))

    # Delete teaser image file if it exists
    if post.teaser_image:
        try:
            teaser_path = os.path.join('static', post.teaser_image)
            if os.path.exists(teaser_path):
                os.remove(teaser_path)
        except Exception:
            pass  # Continue even if file deletion fails

    # Keep aggregate Tag.count accurate and delete the post
    if not post.hidden:
        decrement_tags(post.tags)
    db.session.delete(post)
    db.session.commit()

    if request.is_json:
        return jsonify({'success': True})

    flash('Post deletado com sucesso')
    return redirect(url_for('index'))

# ============= INTERAÇÕES PASSIVAS (curtir / comentar / depoimentos) =============

@app.route('/post/<int:post_id>/like', methods=['POST'])
@limiter.limit("30 per minute")  # Curtida anônima: limite por IP contra flood
def like_post(post_id):
    """Toggle de curtida anônima (visitor_id = UUID no localStorage do visitante)"""
    post = get_visible_post_or_404(post_id)
    data = request.get_json(silent=True) or {}
    visitor_id = str(data.get('visitor_id', ''))[:36]
    if not visitor_id:
        return jsonify({'error': 'visitor_id ausente'}), 400

    existing = Like.query.filter_by(post_id=post.id, visitor_id=visitor_id).first()
    if existing:
        db.session.delete(existing)
        liked = False
    else:
        db.session.add(Like(post_id=post.id, visitor_id=visitor_id))
        liked = True
    db.session.commit()

    count = Like.query.filter_by(post_id=post.id).count()
    return jsonify({'success': True, 'liked': liked, 'likes': count})

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
@limiter.limit("10 per hour")  # Comentário exige conta; limite contra spam
def add_comment(post_id):
    """Add comment to post (publica direto; admin deleta depois se preciso)"""
    post = get_visible_post_or_404(post_id)
    if not setting('comments_open'):
        flash('Comentários fechados no momento')
        return redirect(post_url(post))
    body = (request.form.get('body') or '').strip()[:2000]
    if not body:
        flash('Comentário vazio')
        return redirect(post_url(post))

    db.session.add(Comment(post_id=post.id, author_id=current_user.id, body=body))
    db.session.commit()
    return redirect(post_url(post))

@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    """Delete comment - admin only"""
    comment = db.get_or_404(Comment, comment_id)
    if not current_user.is_admin:
        flash('Apenas admins podem deletar comentários')
        return redirect(url_for('post_by_id', post_id=comment.post_id))

    post_id = comment.post_id
    db.session.delete(comment)
    db.session.commit()
    return redirect(url_for('post_by_id', post_id=post_id))

@app.route('/depoimentos', methods=['GET', 'POST'])
@limiter.limit("10 per hour", methods=["POST"])  # Limite só na escrita
def depoimentos():
    """Guestbook: GET lista, POST adiciona (exige login)"""
    if request.method == 'POST':
        if not current_user.is_authenticated:
            flash('Entre ou cadastre um pseudônimo para deixar um depoimento')
            return redirect(url_for('login'))
        if not setting('testimonials_open'):
            flash('Depoimentos fechados no momento')
            return redirect(url_for('depoimentos'))
        body = (request.form.get('body') or '').strip()[:2000]
        if body:
            db.session.add(Testimonial(author_id=current_user.id, body=body))
            db.session.commit()
        return redirect(url_for('depoimentos'))

    items = Testimonial.query.order_by(Testimonial.created_at.desc()).all()
    return render_template('depoimentos.html', testimonials=items)

@app.route('/depoimento/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_testimonial(item_id):
    """Delete testimonial - admin only"""
    item = db.get_or_404(Testimonial, item_id)
    if not current_user.is_admin:
        flash('Apenas admins podem deletar depoimentos')
        return redirect(url_for('depoimentos'))

    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('depoimentos'))

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per hour")  # Prevent mass account creation
def register():
    """User registration"""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form

        if not setting('registration_open'):
            if request.is_json:
                return jsonify({'error': 'Cadastros fechados no momento'}), 403
            flash('Cadastros fechados no momento')
            return redirect(url_for('register'))
        # Honeypot preenchido: finge que deu certo e não cria nada.
        if (data.get(HONEYPOT_FIELD) or '').strip():
            return redirect(url_for('index'))
        if turnstile_site_key() and not verify_turnstile(data.get('cf-turnstile-response')):
            if request.is_json:
                return jsonify({'error': 'Verificação anti-robô falhou'}), 400
            flash('Verificação anti-robô falhou, tente de novo')
            return redirect(url_for('register'))

        username = (data.get('username') or '').strip()
        email = (data.get('email') or '').strip()
        password = data.get('password') or ''

        def reg_error(msg, code=400):
            if request.is_json:
                return jsonify({'error': msg}), code
            flash(msg)
            return redirect(url_for('register'))

        # Server-side validation (client 'required' is not enough)
        if not username or not email or not password:
            return reg_error('Preencha usuário, e-mail e senha')
        if len(password) < 8:
            return reg_error('A senha precisa ter ao menos 8 caracteres')
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            return reg_error('E-mail inválido')

        # Check if user exists
        if User.query.filter_by(username=username).first():
            return reg_error('Nome de usuário já existe')
        if User.query.filter_by(email=email).first():
            return reg_error('E-mail já cadastrado')

        # Create new user
        user = User(username=username, email=email)
        user.set_password(password)

        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            # Race between the existence checks above and commit
            db.session.rollback()
            return reg_error('Usuário ou e-mail já cadastrado')

        login_user(user)

        if request.is_json:
            return jsonify({'success': True, 'username': username})
        return redirect(url_for('index'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")  # Prevent brute force attacks
def login():
    """User login"""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        username = data.get('username')
        password = data.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password) and user.is_banned:
            if request.is_json:
                return jsonify({'error': 'Pseudônimo bloqueado'}), 403
            flash('Este pseudônimo está bloqueado')
            return redirect(url_for('login'))

        if user and user.check_password(password):
            login_user(user, remember=True)
            if request.is_json:
                return jsonify({'success': True, 'username': username})
            return redirect(url_for('index'))
        
        if request.is_json:
            return jsonify({'error': 'Credenciais inválidas'}), 401
        flash('Usuário ou senha inválidos')
        return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    return redirect(url_for('index'))

@app.route('/api/tags')
def api_tags():
    """Get all tags for autocomplete"""
    tags = Tag.query.order_by(Tag.count.desc()).limit(50).all()
    return jsonify([{'name': t.name, 'type': t.type, 'count': t.count} for t in tags])

# ============= FEEDS (RSS/Atom) =============

FEED_ENTRY_LIMIT = 50

# XML 1.0 não aceita a maioria dos caracteres de controle — sobrevivem em
# body_html de posts importados de .txt legado (Notepad, "poesia visual"
# preservada byte-a-byte por tools/import_posts.py). fg.rss_str()/atom_str()
# só valida isso na hora de serializar o documento inteiro, não por entry —
# sem isso, um post derrubaria o feed inteiro em vez de só perder o caractere.
_XML_ILLEGAL_RE = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f]')

def _xml_safe(text):
    return _XML_ILLEGAL_RE.sub('', text) if text else text

def _build_feed(tags=None):
    """Monta um FeedGenerator com os posts mais recentes (globais ou
    filtrados por tag, mesmo filtro de /api/posts), corpo completo
    (body_html já sanitizado) em cada entry. Um post com dado incompleto
    (timestamp nulo, author órfão) não pode derrubar o feed inteiro — essa
    entry é descartada individualmente e o resto segue."""
    query = filter_by_tags(public_posts().options(db.joinedload(Post.author)), tags)
    posts = query.order_by(Post.created_at.desc()).limit(FEED_ENTRY_LIMIT).all()

    fg = FeedGenerator()
    feed_url = request.url
    title = 'Xampu Para Ossos' + (f' — #{", #".join(tags)}' if tags else '')
    fg.id(feed_url)
    fg.title(title)
    fg.link(href=url_for('index', _external=True), rel='alternate')
    fg.link(href=feed_url, rel='self')
    fg.language('pt-BR')
    fg.description('Blog minimalista de poesia digital com estética cyberpunk/K-punk.')
    fg.icon(url_for('static', filename='images/wp-icon.png', _external=True))

    for post in posts:
        fe = fg.add_entry()
        try:
            # id da entry = URL por id: estável mesmo se título/slug mudar
            # (leitor de feed não re-anuncia o poema como novo)
            fe.id(url_for('post_by_id', post_id=post.id, _external=True))
            fe.title(_xml_safe(post.title))
            fe.link(href=post_url(post, _external=True))
            fe.content(_xml_safe(post.body_html), type='html')  # corpo completo, não teaser
            fe.author(name=post.author.username)
            fe.published((post.created_at or post.updated_at).replace(tzinfo=timezone.utc))
            fe.updated((post.updated_at or post.created_at).replace(tzinfo=timezone.utc))
            for t in post.tags or []:
                value = t.get('value')
                if value:
                    fe.category(term=_xml_safe(value))
        except Exception:
            app.logger.exception('Post %s quebrou a geração do feed — pulado', post.id)
            fg.remove_entry(fe)
    return fg

@app.route('/feed.xml')
def feed_rss():
    """Feed RSS 2.0 — global, ou filtrado por ?tag=valor (repetível)."""
    fg = _build_feed(request.args.getlist('tag'))
    return Response(fg.rss_str(), mimetype='application/rss+xml')

@app.route('/feed.atom')
def feed_atom():
    """Feed Atom 1.0 — global, ou filtrado por ?tag=valor (repetível)."""
    fg = _build_feed(request.args.getlist('tag'))
    return Response(fg.atom_str(), mimetype='application/atom+xml')

@app.route('/admin')
@admin_required
def admin():
    """Painel admin: Posts · Moderação · Usuários · Site (dados via /api/admin/*)"""
    return render_template('admin.html')

@app.route('/admin/acervo')
@admin_required
def admin_acervo():
    """Painel do acervo: marcar/desmarcar pastas e poemas de poesia/ no site"""
    return render_template('acervo.html')

@app.route('/api/admin/acervo', methods=['GET', 'POST'])
@admin_required
def api_admin_acervo():
    """GET: estado de cada arquivo do acervo. POST: aplica mudanças (ver acervo.py)."""
    import acervo  # lazy: acervo -> tools/import_posts -> app
    if request.method == 'GET':
        return jsonify(acervo.tree_state())

    data = request.get_json(silent=True) or {}
    def as_list(name):
        value = data.get(name) or []
        return value if isinstance(value, list) else []
    try:
        changes = acervo.apply_changes(
            include=[str(p) for p in as_list('include')],
            exclude=[str(p) for p in as_list('exclude')],
            include_posts=[int(i) for i in as_list('include_posts')],
            exclude_posts=[int(i) for i in as_list('exclude_posts')],
            author=current_user,
            dry_run=bool(data.get('dry_run')),
        )
    except (TypeError, ValueError):
        return jsonify({'error': 'Payload inválido'}), 400
    return jsonify(changes)

# ============= API DO PAINEL ADMIN (/admin) =============

BACKUP_DIR = Path(os.environ.get('BACKUP_DIR', str(Path.home() / 'backups' / 'xampu-db')))
PUBLISH_STATUS_FILE = Path(app.root_path) / 'instance' / 'publish_status.json'

def _iso(when):
    return when.isoformat() if when else None

def _post_row(post, likes=0, comments=0):
    return {
        'id': post.id, 'title': post.title, 'slug': post.slug, 'url': post_url(post),
        'created_at': _iso(post.created_at), 'views': post.views or 0,
        'likes': likes, 'comments': comments, 'hidden': bool(post.hidden),
        'source_path': post.source_path,
    }

def _counts_by_post(model):
    return dict(db.session.query(model.post_id, db.func.count(model.id)).group_by(model.post_id))

@app.route('/api/admin/posts')
@admin_required
def api_admin_posts():
    """Todos os posts (inclusive ocultos) com views/curtidas/comentários."""
    likes, comments = _counts_by_post(Like), _counts_by_post(Comment)
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return jsonify([_post_row(p, likes.get(p.id, 0), comments.get(p.id, 0)) for p in posts])

@app.route('/api/admin/posts/<int:post_id>', methods=['PATCH'])
@admin_required
def api_admin_post_update(post_id):
    """Edita título (slug novo + alias do antigo, via assign_post_slugs) e/ou
    oculta/reexibe (mesmas regras de Tag.count do painel do acervo)."""
    post = db.get_or_404(Post, post_id)
    data = request.get_json(silent=True) or {}
    if 'title' in data:
        title = ' '.join(str(data['title'] or '').split())[:200]
        if not title:
            return jsonify({'error': 'Título vazio'}), 400
        post.title = title
        post.updated_at = utcnow()
    if 'hidden' in data:
        import acervo  # lazy, ver api_admin_acervo
        (acervo._hide if data['hidden'] else acervo._show)(post, defaultdict(list))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Conflito ao salvar, tente de novo'}), 409
    return jsonify(_post_row(post, Like.query.filter_by(post_id=post.id).count(),
                             Comment.query.filter_by(post_id=post.id).count()))

@app.route('/api/admin/posts/<int:post_id>/views/reset', methods=['POST'])
@admin_required
def api_admin_post_views_reset(post_id):
    post = db.get_or_404(Post, post_id)
    post.views = 0
    db.session.commit()
    return jsonify({'success': True, 'views': 0})

@app.route('/api/admin/views/reset', methods=['POST'])
@admin_required
def api_admin_views_reset():
    """Zera as views de TODOS os posts — exige {"confirm": "zerar"}."""
    data = request.get_json(silent=True) or {}
    if data.get('confirm') != 'zerar':
        return jsonify({'error': 'Confirmação ausente'}), 400
    total = Post.query.filter(Post.views > 0).update({Post.views: 0}, synchronize_session=False)
    db.session.commit()
    return jsonify({'success': True, 'posts': total})

@app.route('/api/admin/moderation')
@admin_required
def api_admin_moderation():
    """Comentários e depoimentos recentes, para moderar num lugar só."""
    comments = (Comment.query.options(db.joinedload(Comment.author), db.joinedload(Comment.post))
                .order_by(Comment.created_at.desc()).limit(200).all())
    testimonials = (Testimonial.query.options(db.joinedload(Testimonial.author))
                    .order_by(Testimonial.created_at.desc()).limit(200).all())
    return jsonify({
        'comments': [{'id': c.id, 'body': c.body, 'created_at': _iso(c.created_at),
                      'author': c.author.username if c.author else '?',
                      'post': {'id': c.post.id, 'title': c.post.title, 'url': post_url(c.post)}}
                     for c in comments],
        'testimonials': [{'id': t.id, 'body': t.body, 'created_at': _iso(t.created_at),
                          'author': t.author.username if t.author else '?'}
                         for t in testimonials],
    })

@app.route('/api/admin/comments/<int:comment_id>', methods=['DELETE'])
@admin_required
def api_admin_comment_delete(comment_id):
    db.session.delete(db.get_or_404(Comment, comment_id))
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/admin/testimonials/<int:item_id>', methods=['DELETE'])
@admin_required
def api_admin_testimonial_delete(item_id):
    db.session.delete(db.get_or_404(Testimonial, item_id))
    db.session.commit()
    return jsonify({'success': True})

def _user_row(user, comments, testimonials):
    return {
        'id': user.id, 'username': user.username, 'email': user.email,
        'created_at': _iso(user.created_at), 'is_admin': bool(user.is_admin),
        'is_banned': bool(user.is_banned), 'comments': comments, 'testimonials': testimonials,
        'is_self': user.id == current_user.id,
    }

def _counts_by_author(model):
    return dict(db.session.query(model.author_id, db.func.count(model.id)).group_by(model.author_id))

@app.route('/api/admin/users')
@admin_required
def api_admin_users():
    comments, testimonials = _counts_by_author(Comment), _counts_by_author(Testimonial)
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([_user_row(u, comments.get(u.id, 0), testimonials.get(u.id, 0)) for u in users])

def _guard_user_change(user):
    """Admin e a própria conta não são bloqueáveis/apagáveis pelo painel."""
    if user.is_admin or user.id == current_user.id:
        return jsonify({'error': 'Não dá para mexer em conta de admin pelo painel'}), 400
    return None

@app.route('/api/admin/users/<int:user_id>', methods=['PATCH'])
@admin_required
def api_admin_user_update(user_id):
    user = db.get_or_404(User, user_id)
    refused = _guard_user_change(user)
    if refused:
        return refused
    data = request.get_json(silent=True) or {}
    if 'banned' in data:
        user.is_banned = bool(data['banned'])
    db.session.commit()
    return jsonify(_user_row(user, len(user.comments), len(user.testimonials)))

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def api_admin_user_delete(user_id):
    """Apaga a conta e o que ela escreveu (comentários e depoimentos)."""
    user = db.get_or_404(User, user_id)
    refused = _guard_user_change(user)
    if refused:
        return refused
    if user.posts:
        return jsonify({'error': 'Conta tem posts; oculte-os ou transfira antes'}), 400
    removed = {'comments': len(user.comments), 'testimonials': len(user.testimonials)}
    for item in list(user.comments) + list(user.testimonials):
        db.session.delete(item)
    db.session.delete(user)
    db.session.commit()
    return jsonify({'success': True, **removed})

def _latest_backup():
    try:
        files = sorted(BACKUP_DIR.glob('*.db'), key=lambda f: f.stat().st_mtime)
    except OSError:
        return None
    if not files:
        return None
    newest = files[-1]
    return {'file': newest.name, 'at': datetime.fromtimestamp(newest.stat().st_mtime).isoformat(),
            'count': len(files)}

def _publish_status():
    try:
        return json.loads(PUBLISH_STATUS_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None

@app.route('/api/admin/site', methods=['GET', 'PATCH'])
@admin_required
def api_admin_site():
    """Interruptores do site + status (backup, publicação automática, contagens)."""
    if request.method == 'PATCH':
        data = request.get_json(silent=True) or {}
        for key, value in data.items():
            if key not in SITE_SWITCHES:
                return jsonify({'error': f'Interruptor desconhecido: {key}'}), 400
            row = db.session.get(SiteSetting, key) or SiteSetting(key=key)
            row.value = '1' if value else '0'
            db.session.add(row)
        db.session.commit()
        g.pop('_site_settings', None)
    return jsonify({
        'switches': [{'key': key, 'label': label, 'on': setting(key)}
                     for key, (label, _default) in SITE_SWITCHES.items()],
        'status': {
            'posts_visible': public_posts().count(),
            'posts_hidden': Post.query.filter(Post.hidden.is_(True)).count(),
            'views_total': db.session.query(db.func.coalesce(db.func.sum(Post.views), 0)).scalar(),
            'users': User.query.count(),
            'users_banned': User.query.filter(User.is_banned.is_(True)).count(),
            'backup': _latest_backup(),
            'publish': _publish_status(),
        },
    })

@app.route('/api/user/settings', methods=['GET', 'POST'])
@login_required
def user_settings():
    """Get/update user settings"""
    if request.method == 'POST':
        data = request.get_json()
        current_user.settings = data
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify(current_user.settings)

@app.route('/api/upload/teaser', methods=['POST'])
@login_required
@limiter.limit("10 per minute")  # Prevent upload spam
def upload_teaser():
    """Upload teaser image for posts"""
    # Upload cai no diretório público: restringir a admins como o restante da escrita
    if not current_user.is_admin:
        return jsonify({'error': 'Apenas admins podem enviar imagens'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Tipo de arquivo não permitido'}), 400
    
    try:
        filename = save_teaser_image(file)
        if filename:
            return jsonify({
                'success': True, 
                'filename': filename,
                'url': f"/static/{filename}"
            })
        else:
            return jsonify({'error': 'Arquivo inválido ou não é uma imagem'}), 400
    except Exception:
        app.logger.exception('Teaser upload failed')
        return jsonify({'error': 'Falha ao processar o upload'}), 500

# ============= ERROR HANDLERS =============

SOBRE_FILE = Path(app.root_path) / 'instance' / 'sobre.html'

def sanitize_sobre(html_content):
    """HTML da página Sobre (só admin edita): allowlist ampla, sem <pre> automático."""
    tags = ['p', 'br', 'strong', 'em', 'u', 'b', 'i', 'h1', 'h2', 'h3', 'h4', 'blockquote',
            'ul', 'ol', 'li', 'a', 'img', 'span', 'div', 'section', 'hr']
    attrs = {'*': ['class'], 'a': ['href', 'title', 'class', 'target', 'rel'],
             'img': ['src', 'alt', 'width', 'height', 'class']}
    return bleach.clean(html_content, tags=tags, attributes=attrs,
                        protocols=['http', 'https', 'mailto'], strip=True)

def read_sobre():
    try:
        return SOBRE_FILE.read_text(encoding='utf-8').strip()
    except OSError:
        return ''

@app.route('/sobre')
def sobre():
    """About page (texto padrão no template; admin pode sobrescrever)"""
    custom = read_sobre()
    source = custom
    if not source and current_user.is_authenticated and current_user.is_admin:
        source = render_template('_sobre_default.html')
    return render_template('sobre.html', sobre_custom=custom, sobre_source=source)

@app.route('/sobre/edit', methods=['POST'])
@admin_required
def sobre_edit():
    html = sanitize_sobre(request.form.get('html', '')).strip()
    if html:
        SOBRE_FILE.parent.mkdir(exist_ok=True)
        SOBRE_FILE.write_text(html, encoding='utf-8')
        flash('Página Sobre atualizada.', 'success')
    else:
        SOBRE_FILE.unlink(missing_ok=True)
        flash('Página Sobre restaurada ao texto original.', 'success')
    return redirect(url_for('sobre'))

@app.route('/galeria')
def galeria():
    """Galeria: lista vertical título → imagem → legenda"""
    items = GalleryItem.query.order_by(GalleryItem.created_at.desc()).all()
    return render_template('galeria.html', items=items)

@app.route('/galeria/new', methods=['POST'])
@login_required
@limiter.limit("20 per hour")
def galeria_new():
    """Adicionar imagem à galeria — admin only, reaproveita save_teaser_image()"""
    if not current_user.is_admin:
        flash('Apenas admins podem adicionar imagens à galeria')
        return redirect(url_for('galeria'))

    title = (request.form.get('title') or '').strip()[:200]
    caption = (request.form.get('caption') or '').strip()[:2000]
    file = request.files.get('image')

    if not title or not file or file.filename == '':
        flash('Título e imagem são obrigatórios')
        return redirect(url_for('galeria'))

    image_path = save_teaser_image(file)
    if not image_path:
        flash('Arquivo inválido ou não é uma imagem')
        return redirect(url_for('galeria'))

    db.session.add(GalleryItem(
        title=title, image_path=image_path, caption=caption, author_id=current_user.id
    ))
    db.session.commit()
    return redirect(url_for('galeria'))

def _remove_gallery_file(image_path):
    """Apaga o arquivo de uma imagem da galeria (silencioso se já não existe)."""
    if not image_path:
        return
    try:
        image_fs_path = os.path.join(app.root_path, 'static', image_path)
        if os.path.exists(image_fs_path):
            os.remove(image_fs_path)
    except Exception:
        pass

@app.route('/galeria/<int:item_id>/edit', methods=['POST'])
@login_required
def galeria_edit(item_id):
    """Editar título/legenda/data (e opcionalmente trocar a imagem) — admin only"""
    item = db.get_or_404(GalleryItem, item_id)
    if not current_user.is_admin:
        flash('Apenas admins podem editar imagens da galeria')
        return redirect(url_for('galeria'))

    title = (request.form.get('title') or '').strip()[:200]
    if not title:
        flash('O título não pode ficar vazio')
        return redirect(url_for('galeria'))

    new_date = None
    raw_date = (request.form.get('date') or '').strip()
    if raw_date:
        try:
            new_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
        except ValueError:
            flash('Data inválida')
            return redirect(url_for('galeria'))

    old_path = None
    file = request.files.get('image')
    if file and file.filename:
        image_path = save_teaser_image(file)
        if not image_path:
            flash('Arquivo inválido ou não é uma imagem')
            return redirect(url_for('galeria'))
        old_path, item.image_path = item.image_path, image_path

    item.title = title
    item.caption = (request.form.get('caption') or '').strip()[:2000] or None
    # a data ordena a galeria; mesma data = mantém a hora original
    if new_date and new_date != item.created_at.date():
        item.created_at = datetime.combine(new_date, item.created_at.time())
    db.session.commit()
    _remove_gallery_file(old_path)
    flash('Imagem atualizada')
    return redirect(url_for('galeria') + f'#img-{item.id}')

@app.route('/galeria/<int:item_id>/delete', methods=['POST'])
@login_required
def galeria_delete(item_id):
    """Deletar imagem da galeria — admin only"""
    item = db.get_or_404(GalleryItem, item_id)
    if not current_user.is_admin:
        flash('Apenas admins podem deletar imagens da galeria')
        return redirect(url_for('galeria'))

    image_path = item.image_path
    db.session.delete(item)
    db.session.commit()
    _remove_gallery_file(image_path)
    flash('Imagem deletada')
    return redirect(url_for('galeria'))

# ============= BUSCADORES =============

@app.route('/robots.txt')
def robots_txt():
    lines = [
        'User-agent: *',
        'Disallow: /admin',
        'Disallow: /api/',
        'Disallow: /login',
        'Disallow: /register',
        f"Sitemap: {url_for('sitemap_xml', _external=True)}",
    ]
    return Response('\n'.join(lines) + '\n', mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap_xml():
    """Páginas fixas + todos os poemas visíveis (URL com slug)."""
    entries = [(url_for(endpoint, _external=True), None)
               for endpoint in ('index', 'galeria', 'sobre', 'depoimentos')]
    rows = (db.session.query(Post.id, Post.slug, Post.updated_at, Post.created_at)
            .filter(Post.hidden.is_(False)).order_by(Post.created_at.desc()).all())
    for row in rows:
        when = row.updated_at or row.created_at
        entries.append((post_url({'id': row.id, 'slug': row.slug}, _external=True),
                        when.date().isoformat() if when else None))
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod in entries:
        xml.append(f'<url><loc>{loc}</loc>' + (f'<lastmod>{lastmod}</lastmod>' if lastmod else '') + '</url>')
    xml.append('</urlset>')
    return Response('\n'.join(xml), mimetype='application/xml')

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

# Headers de segurança em toda resposta. A CSP é permissiva em script/style
# ('unsafe-inline') por causa dos handlers inline dos templates; marked.js é o
# único script externo. CSP estrita (nonces) fica de backlog.
@app.after_request
def security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://challenges.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "  # Newsreader/JetBrains Mono
        "img-src 'self' data:; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self'; "
        "frame-src https://challenges.cloudflare.com; "  # widget do Turnstile (cadastro)
        "frame-ancestors 'self'"
    )
    return response

# ============= CLI COMMANDS =============

@app.cli.command()
def init_db():
    """Initialize the database"""
    db.create_all()
    print("Database initialized!")

@app.cli.command()
def seed_db():
    """Seed database with sample data (só dev: as senhas abaixo são públicas)"""
    if config_name == 'production':
        print("❌ seed-db recusado em produção: cria contas com senha pública no repo.")
        return
    # Create admin user
    admin = User(username='xampuzordmin', email='admin@xampuparaossos.com', is_admin=True)
    admin.set_password('cipherbill64')
    db.session.add(admin)

    # Create sample users
    for i in range(5):
        user = User(username=f'poet_{i}', email=f'poet{i}@example.com')
        user.set_password('password123')
        db.session.add(user)

    db.session.commit()

    # Create sample posts
    users = User.query.all()
    genres = ['cybernetic', 'digital', 'glitch', 'neural', 'quantum']

    for i in range(20):
        post = Post(
            title=f'Digital Dreams #{i+1}',
            body_html=f'''<p>In circuits deep where data flows<br/>
                        Through silicon and chrome<br/>
                        The ghost machine forever knows<br/>
                        The path that leads us home</p>''',
            tags=[
                {'type': 'genre', 'value': genres[i % 5]},
                {'type': 'year', 'value': '2025'}
            ],
            author_id=users[i % len(users)].id,
            views=i * 10
        )
        db.session.add(post)

    db.session.commit()
    print("Database seeded with sample data!")

SEED_USER_RE = re.compile(r'poet_\d+')

@app.cli.command()
def prune_seed_users():
    """Apaga as contas poet_N do seed-db (senha 'password123' pública no repo).

    Só remove conta não-admin, com o e-mail do seed e sem nenhum conteúdo
    (posts, comentários, depoimentos). Idempotente."""
    removed = 0
    for user in User.query.order_by(User.id):
        if not SEED_USER_RE.fullmatch(user.username) or user.is_admin:
            continue
        if not (user.email or '').endswith('@example.com'):
            print(f"⏭️  {user.username}: e-mail não é do seed, mantido")
            continue
        if user.posts or user.comments or user.testimonials:
            print(f"⏭️  {user.username}: tem conteúdo, mantido")
            continue
        print(f"🗑️  {user.username} ({user.email})")
        db.session.delete(user)
        removed += 1
    db.session.commit()
    print(f"✅ {removed} conta(s) de seed removida(s)")

@app.cli.command()
def reset_admin_password():
    """Reset admin password interactively"""
    import getpass

    # Find admin user
    admin = User.query.filter_by(is_admin=True).first()

    if not admin:
        print("❌ No admin user found in database!")
        print("ℹ️  Run 'flask seed-db' to create one, or manually set is_admin=True for a user.")
        return

    print(f"✅ Found admin user: {admin.username} ({admin.email})")
    print()

    # Ask for new password
    while True:
        new_password = getpass.getpass("Enter new password: ")
        confirm_password = getpass.getpass("Confirm new password: ")

        if new_password != confirm_password:
            print("❌ Passwords don't match. Try again.\n")
            continue

        if len(new_password) < 4:
            print("❌ Password too short (min 4 chars). Try again.\n")
            continue

        break

    # Update password
    admin.set_password(new_password)
    db.session.commit()

    print()
    print("✅ Admin password reset successfully!")
    print(f"   Username: {admin.username}")
    print(f"   New password: {'*' * len(new_password)}")

@app.cli.command()
def list_users():
    """List all users in the database"""
    users = User.query.all()

    if not users:
        print("❌ No users found in database!")
        return

    print(f"\n📋 Total users: {len(users)}\n")
    print(f"{'ID':<5} {'Username':<20} {'Email':<30} {'Admin':<8} {'Posts':<8}")
    print("-" * 75)

    for user in users:
        admin_status = "✅ Yes" if user.is_admin else "No"
        post_count = len(user.posts)
        print(f"{user.id:<5} {user.username:<20} {user.email:<30} {admin_status:<8} {post_count:<8}")
    print()

@app.cli.command()
def make_admin():
    """Make a user admin by username"""
    import sys

    username = input("Enter username to make admin: ").strip()

    if not username:
        print("❌ Username cannot be empty!")
        return

    user = User.query.filter_by(username=username).first()

    if not user:
        print(f"❌ User '{username}' not found!")
        print("\nℹ️  Available users:")
        users = User.query.all()
        for u in users:
            print(f"   - {u.username}")
        return

    if user.is_admin:
        print(f"ℹ️  User '{username}' is already an admin!")
        return

    # Confirm
    confirm = input(f"Make '{username}' an admin? (yes/no): ").strip().lower()

    if confirm not in ['yes', 'y']:
        print("❌ Cancelled.")
        return

    user.is_admin = True
    db.session.commit()

    print(f"✅ User '{username}' is now an admin!")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ('1', 'true', 'yes', 'on')
    app.run(debug=debug)