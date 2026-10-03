import os
from pathlib import Path

from dotenv import load_dotenv

# Base directories for the backend and frontend files.
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"

# Load environment variables from the project root and backend folders.
load_dotenv(PROJECT_DIR / ".env", override=True)
load_dotenv(BASE_DIR / ".env", override=True)
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")


class Config:
    """Application configuration loaded from environment variables."""

    SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")
    # Ollama serves the local Llama model over this loopback HTTP endpoint.
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
    LLAMA_MODEL = os.getenv("LLAMA_MODEL", "llama3.2:3b").strip()
    DATABASE_PATH = os.getenv("DATABASE_PATH") or "chatbot.db"
    if not Path(DATABASE_PATH).is_absolute():
        DATABASE_PATH = str(BASE_DIR / DATABASE_PATH)
    APP_PORT = int(os.getenv("APP_PORT", "5000"))

    BASE_DIR = BASE_DIR
    PROJECT_DIR = PROJECT_DIR
    FRONTEND_DIR = FRONTEND_DIR

    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")
    SCOPES = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/userinfo.email",
    ]
