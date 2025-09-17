# README.md
# Cybernetic Poetry Blog

A modern, minimalist blog platform for digital poetry with a cyberpunk aesthetic.

## Features

- **Instagram-style Grid Layout**: 3x3 post grid with infinite scroll
- **Markdown Editor**: Medium-inspired editor with live preview
- **Customizable Typography**: Multiple font options for posts
- **Dark/Light Theme**: Toggle between black/white themes
- **Tag System**: Organize posts by year and genre
- **User Authentication**: Register, login, and manage your posts
- **Admin Dashboard**: Monitor posts, users, and site statistics
- **Quality of Life Features**:
  - Auto-save drafts to localStorage
  - Keyboard shortcuts (Ctrl+S to save, Ctrl+P to preview)
  - Tag autocomplete
  - Search by tags
  - View counter for posts

## Tech Stack

- **Backend**: Flask (Python 3.10+)
- **Database**: SQLite with SQLAlchemy ORM
- **Frontend**: Vanilla JavaScript, Tailwind CSS
- **Authentication**: Flask-Login
- **Security**: Bleach for HTML sanitization, Werkzeug for password hashing

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/cyberpoetry-blog.git
cd cyberpoetry-blog
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Initialize the database:
```bash
flask init-db
flask seed-db  # Optional: add sample data
```

5. Run the application:
```bash
python run.py
```

The app will be available at `http://localhost:5000`

## Project Structure

```
cyberpoetry_blog/
├── app.py                 # Main Flask application
├── config.py              # Configuration settings
├── run.py                 # Entry point
├── requirements.txt       # Python dependencies
├── templates/            # Jinja2 templates
│   ├── base.html         # Base template with navigation
│   ├── index.html        # Homepage with post grid
│   ├── post.html         # Single post view
│   ├── editor.html       # Post editor
│   ├── login.html        # Login page
│   ├── register.html     # Registration page
│   └── admin.html        # Admin dashboard
├── static/
│   ├── css/
│   │   └── style.css     # Custom styles
│   ├── js/
│   │   ├── main.js       # Main JavaScript
│   │   └── editor.js     # Editor functionality
│   └── uploads/          # User uploaded images
└── README.md
```

## API Endpoints

- `GET /` - Homepage with initial posts
- `GET /api/posts?page=<int>&tags=<json>` - Get posts for infinite scroll
- `GET /post/<id>` - View single post
- `POST /post/new` - Create new post (requires login)
- `POST /post/<id>/edit` - Edit post (requires ownership)
- `GET /api/tags` - Get all tags for autocomplete
- `POST /api/user/settings` - Update user preferences
- `GET /admin` - Admin dashboard (requires admin role)

## Deployment

### Heroku

1. Create a new Heroku app:
```bash
heroku create your-app-name
```

2. Set environment variables:
```bash
heroku config:set SECRET_KEY=your-secret-key-here
```

3. Deploy:
```bash
git push heroku main
```

### Vercel

1. Install Vercel CLI:
```bash
npm i -g vercel
```

2. Deploy:
```bash
vercel
```

## Development

### Adding a new feature

1. Create a new branch:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes
3. Test thoroughly
4. Submit a pull request

### Running tests

```bash
python -m pytest tests/
```

## Security Considerations

- Change `SECRET_KEY` in production
- Use PostgreSQL or MySQL in production instead of SQLite
- Enable HTTPS in production
- Regularly update dependencies
- Implement rate limiting for API endpoints
- Add CAPTCHA for registration

## License

MIT License - feel free to use this project for your own cybernetic poetry!

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Credits