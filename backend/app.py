from datetime import datetime
from pathlib import Path
import sys

from flask import Flask, jsonify
from flask_cors import CORS

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from backend.auth import auth_bp
    from backend.chat import chat_bp
    from backend.config import Config
    from backend.db import close_db, get_db, init_db
    from backend.feedback import feedback_bp
    from backend.analytics import analytics_bp
    from backend.llm import load_llama_model
    from backend.utils import google_credentials_path
else:
    from .auth import auth_bp
    from .chat import chat_bp
    from .config import Config
    from .db import close_db, get_db, init_db
    from .feedback import feedback_bp
    from .analytics import analytics_bp
    from .llm import load_llama_model
    from .utils import google_credentials_path


def create_app():
    """Create the Flask app and attach the active feature blueprints."""
    app = Flask(
        __name__,
        template_folder=str(Config.FRONTEND_DIR / "templates"),
        static_folder=str(Config.FRONTEND_DIR / "static"),
    )
    app.secret_key = Config.SECRET_KEY
    CORS(app, supports_credentials=True)

    # Open SQLite lazily per request and close it automatically afterward.
    app.teardown_appcontext(close_db)
    init_db()
    load_llama_model()

    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(feedback_bp)
    app.register_blueprint(analytics_bp)  # Phase 3: analytics dashboard

    @app.route("/api/health", methods=["GET"])
    def health_check():
        """Return the core service status used by the chat header."""
        db_ok = False
        try:
            get_db().execute("SELECT 1")
            db_ok = True
        except Exception:
            db_ok = False

        # Ollama is local, so configuration is ready when its endpoint and model are set.
        llama_ok = bool(Config.OLLAMA_BASE_URL and Config.LLAMA_MODEL)
        oauth_ok = bool(google_credentials_path() or (Config.GOOGLE_CLIENT_ID and Config.GOOGLE_CLIENT_SECRET))
        return jsonify({
            "status": "ok" if db_ok and llama_ok and oauth_ok else "degraded",
            "database": "connected" if db_ok else "error",
            "local_llama": "configured" if llama_ok else "missing",
            "google_oauth": "configured" if oauth_ok else "missing",
            "model": Config.LLAMA_MODEL,
            "timestamp": datetime.utcnow().isoformat(),
        })

    return app


app = create_app()


if __name__ == "__main__":
    print("System initialization complete.")
    print(f"Using local Llama model: {Config.LLAMA_MODEL} via Ollama")
    print(f"Starting Flask server on http://127.0.0.1:{Config.APP_PORT}")
    app.run(debug=True, port=Config.APP_PORT)
