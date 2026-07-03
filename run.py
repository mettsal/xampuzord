# run.py - Application entry point
import os
from app import app, db

if __name__ == '__main__':
    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()
        
        # Create upload folder if it doesn't exist
        upload_folder = app.config.get('UPLOAD_FOLDER', 'static/uploads')
        os.makedirs(upload_folder, exist_ok=True)
    
    # Get port from environment variable (for deployment)
    port = int(os.environ.get('PORT', 5000))

    # Debug is opt-in via env and OFF by default — never expose the Werkzeug
    # debugger (RCE via console PIN) on a network-facing bind.
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ('1', 'true', 'yes', 'on')

    # Run the application
    app.run(host='0.0.0.0', port=port, debug=debug)