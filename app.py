# app.py - Main Flask Application
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
import bleach
import os
import uuid
from werkzeug.utils import secure_filename

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'cyber-poetry-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///xampuparaossos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'static/uploads/teasers'

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ============= MODELS =============

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    settings = db.Column(db.JSON, default=lambda: {'font': 'Consolas', 'theme': 'light'})
    posts = db.relationship('Post', backref='author', lazy=True)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body_html = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tags = db.Column(db.JSON, default=list)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    views = db.Column(db.Integer, default=0)
    font = db.Column(db.String(50), default='Consolas')
    teaser_image = db.Column(db.String(200), nullable=True)  # Path to teaser image
    teaser_type = db.Column(db.String(20), default='auto')  # 'image', 'auto', or 'none'
    
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
            'teaser_type': self.teaser_type
        }

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'year', 'genre', etc.
    count = db.Column(db.Integer, default=0)

# ============= HELPERS =============

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def sanitize_html(html_content):
    """Sanitize HTML content to prevent XSS"""
    allowed_tags = [
        'p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'blockquote', 'code', 'pre', 'ul', 'ol', 'li', 'a', 'img', 'span', 'div'
    ]
    allowed_attrs = {
        'a': ['href', 'title'],
        'img': ['src', 'alt', 'width', 'height'],
        'span': ['style'],
        'div': ['style', 'class']
    }
    return bleach.clean(html_content, tags=allowed_tags, attributes=allowed_attrs)

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

def allowed_file(filename):
    """Check if the uploaded file is allowed"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_teaser_image(file):
    """Save uploaded teaser image and return the filename"""
    if file and allowed_file(file.filename):
        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        
        # Ensure upload directory exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Save file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        
        return f"uploads/teasers/{unique_filename}"
    return None

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
    except:
        tags_filter = []
    
    query = Post.query
    
    # Filter by tags if provided
    if tags_filter:
        # This is a simple implementation - in production, use proper SQL filtering
        posts = []
        all_posts = query.order_by(Post.created_at.desc()).all()
        for post in all_posts:
            post_tags = [t['value'] for t in post.tags]
            if any(tag in post_tags for tag in tags_filter):
                posts.append(post)
        posts = posts[(page-1)*9:page*9]
    else:
        posts = query.order_by(Post.created_at.desc()).paginate(
            page=page, per_page=9, error_out=False
        ).items
    
    return jsonify([post.to_dict() for post in posts])

@app.route('/post/<int:post_id>')
def view_post(post_id):
    """View single post"""
    post = Post.query.get_or_404(post_id)
    post.views += 1
    db.session.commit()
    return render_template('post.html', post=post)

@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def new_post():
    """Create new post"""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        title = data.get('title', 'Untitled')
        body_html = sanitize_html(data.get('body_html', ''))
        tags = process_tags(data.get('tags', ''))
        font = data.get('font', 'Consolas')
        teaser_image = data.get('teaser_image', None)
        teaser_type = data.get('teaser_type', 'auto')
        
        post = Post(
            title=title,
            body_html=body_html,
            tags=tags,
            font=font,
            teaser_image=teaser_image,
            teaser_type=teaser_type,
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
    post = Post.query.get_or_404(post_id)
    
    # Check ownership
    if post.author_id != current_user.id and not current_user.is_admin:
        flash('You can only edit your own posts')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        post.title = data.get('title', post.title)
        post.body_html = sanitize_html(data.get('body_html', post.body_html))
        post.tags = process_tags(data.get('tags', ''))
        post.font = data.get('font', post.font)
        post.teaser_image = data.get('teaser_image', post.teaser_image)
        post.teaser_type = data.get('teaser_type', post.teaser_type)
        post.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        if request.is_json:
            return jsonify({'success': True})
        return redirect(url_for('view_post', post_id=post.id))
    
    return render_template('editor.html', post=post)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            if request.is_json:
                return jsonify({'error': 'Username already exists'}), 400
            flash('Username already exists')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            if request.is_json:
                return jsonify({'error': 'Email already registered'}), 400
            flash('Email already registered')
            return redirect(url_for('register'))
        
        # Create new user
        user = User(username=username, email=email)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        
        if request.is_json:
            return jsonify({'success': True, 'username': username})
        return redirect(url_for('index'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
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
            return jsonify({'error': 'Invalid credentials'}), 401
        flash('Invalid username or password')
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
        flash('Admin access required')
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
def upload_teaser():
    """Upload teaser image for posts"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    
    try:
        filename = save_teaser_image(file)
        if filename:
            return jsonify({
                'success': True, 
                'filename': filename,
                'url': f"/static/{filename}"
            })
        else:
            return jsonify({'error': 'Failed to save file'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============= ERROR HANDLERS =============

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

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
    admin = User(username='admin', email='admin@xampuparaossos.com', is_admin=True)
    admin.set_password('admin123')
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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)