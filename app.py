from flask import Flask
from config import Config
from routes.main import main_bp

def create_app():
    """Application Factory"""
    flask_app = Flask(__name__)
    flask_app.config.from_object(Config)
    flask_app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB for graph image uploads
    
    # Register Blueprints
    flask_app.register_blueprint(main_bp)
    
    return flask_app

# Expose app instance for Gunicorn
app = create_app()

if __name__ == "__main__":
    print(f"[INFO] Starting DILI Analysis Platform on port {Config.PORT}...")
    app.run(debug=Config.DEBUG, host="0.0.0.0", port=Config.PORT)

