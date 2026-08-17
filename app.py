# app.py - Main Flask Application
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import IntegrityError
from PIL import Image
from datetime import datetime, timezone
import json
import bleach
import os
import re
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

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
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
            'post_theme': self.post_theme
        }

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

# ============= HELPERS =============

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

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

def process_tags(tag_string):
    """Process comma-separated tags into JSON format"""
    tags = []
    for tag in tag_string.split(','):
        tag = tag.strip()
        if tag:
            # Check if it's a year
            tag_type = 'year' if tag.isdigit() and len(tag) == 4 else 'genre'
            tags.append({'type': tag_type, 'value': tag})
            
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
    """Main page with post grid"""
    initial_posts = Post.query.order_by(Post.created_at.desc()).limit(9).all()
    return render_template('index.html', posts=initial_posts)

@app.route('/api/posts')
def api_posts():
    """API endpoint for infinite scroll"""
    page = request.args.get('page', 1, type=int)
    tags_filter = request.args.get('tags', '[]')
    
    try:
        tags_filter = json.loads(tags_filter)
    except (json.JSONDecodeError, TypeError):
        tags_filter = []
    
    query = Post.query

    # Filter by tags if provided. Substring case-insensitive sobre o JSON
    # serializado ("ciber" casa com "cybernetic", como a busca antiga do
    # cliente) — o filtro e a paginação acontecem no banco, não mais O(N)
    # em Python. Seq scan aceitável nesta escala; se crescer, FTS.
    if tags_filter:
        wanted = [str(t).lower() for t in tags_filter]
        conditions = [db.cast(Post.tags, db.String).ilike(f'%{q}%') for q in wanted]
        query = query.filter(db.or_(*conditions))

    posts = query.order_by(Post.created_at.desc()).paginate(
        page=page, per_page=9, error_out=False
    ).items

    return jsonify([post.to_dict() for post in posts])

@app.route('/post/<int:post_id>')
def view_post(post_id):
    """View single post"""
    post = db.get_or_404(Post, post_id)
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
            return jsonify({'success': True, 'post_id': post.id})
        return redirect(url_for('view_post', post_id=post.id))
    
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
        decrement_tags(post.tags)
        post.tags = process_tags(data.get('tags', ''))
        post.font = data.get('font', post.font)
        post.teaser_image = data.get('teaser_image', post.teaser_image)
        post.teaser_type = data.get('teaser_type', post.teaser_type)
        post.post_theme = data.get('post_theme', post.post_theme)
        post.updated_at = utcnow()
        
        db.session.commit()
        
        if request.is_json:
            return jsonify({'success': True, 'post_id': post.id})
        return redirect(url_for('view_post', post_id=post.id))
    
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
        return redirect(url_for('view_post', post_id=post_id))

    # Delete teaser image file if it exists
    if post.teaser_image:
        try:
            teaser_path = os.path.join('static', post.teaser_image)
            if os.path.exists(teaser_path):
                os.remove(teaser_path)
        except Exception:
            pass  # Continue even if file deletion fails

    # Keep aggregate Tag.count accurate and delete the post
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
    post = db.get_or_404(Post, post_id)
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
    post = db.get_or_404(Post, post_id)
    body = (request.form.get('body') or '').strip()[:2000]
    if not body:
        flash('Comentário vazio')
        return redirect(url_for('view_post', post_id=post.id))

    db.session.add(Comment(post_id=post.id, author_id=current_user.id, body=body))
    db.session.commit()
    return redirect(url_for('view_post', post_id=post.id))

@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    """Delete comment - admin only"""
    comment = db.get_or_404(Comment, comment_id)
    if not current_user.is_admin:
        flash('Apenas admins podem deletar comentários')
        return redirect(url_for('view_post', post_id=comment.post_id))

    post_id = comment.post_id
    db.session.delete(comment)
    db.session.commit()
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/depoimentos', methods=['GET', 'POST'])
@limiter.limit("10 per hour", methods=["POST"])  # Limite só na escrita
def depoimentos():
    """Guestbook: GET lista, POST adiciona (exige login)"""
    if request.method == 'POST':
        if not current_user.is_authenticated:
            flash('Entre ou cadastre um pseudônimo para deixar um depoimento')
            return redirect(url_for('login'))
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

@app.route('/admin')
@login_required
def admin():
    """Admin dashboard"""
    if not current_user.is_admin:
        flash('Acesso restrito a admins')
        return redirect(url_for('index'))
    
    posts = Post.query.order_by(Post.created_at.desc()).all()
    users = User.query.order_by(User.created_at.desc()).all()
    tags = Tag.query.order_by(Tag.count.desc()).all()
    
    return render_template('admin.html', posts=posts, users=users, tags=tags)

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

@app.route('/sobre')
def sobre():
    """About page"""
    return render_template('sobre.html')

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
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
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
    """Seed database with sample data"""
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