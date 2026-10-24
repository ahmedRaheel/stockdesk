import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:YOUR_ACTUAL_PASSWORD@host.docker.internal:5432/postgres123"
)
APP_ORIGIN = os.environ.get("APP_ORIGIN", "http://localhost:8080").rstrip("/")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SESSION_HOURS = 12
