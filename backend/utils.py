from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urljoin, urlparse

from flask import jsonify, redirect, request, session, url_for

from .config import Config


def now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format with Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def json_payload() -> dict:
    """Return a JSON request body without raising for empty or invalid JSON."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def current_user_id() -> str | None:
    """Return the logged-in user's id from the session."""
    return session.get("user_id")


def current_user() -> dict:
    """Return template-friendly data for the current user."""
    return {
        "id": session.get("user_id", ""),
        "name": session.get("username", "User"),
        "email": session.get("email", ""),
        "picture": session.get("picture_url", ""),
    }


def require_login(fn):
    """Redirect anonymous users to login, or return 401 for JSON requests."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user_id():
            if request.is_json:
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("auth.login"))
        return fn(*args, **kwargs)

    return wrapper


def safe_redirect_target(target: str | None) -> str:
    """Keep post-login redirects inside this Flask app."""
    if not target:
        return url_for("chat.chat")

    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))
    if redirect_url.scheme in ("http", "https") and redirect_url.netloc == host_url.netloc:
        return redirect_url.geturl()
    return url_for("chat.chat")


def google_credentials_path() -> str | None:
    """Find a local Google OAuth credentials file in common project locations."""
    candidates = [
        Config.BASE_DIR / "credentials.json",
        Config.PROJECT_DIR / "credentials.json",
    ]
    return next((str(path) for path in candidates if Path(path).exists()), None)
