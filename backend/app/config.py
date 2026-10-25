import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://stockdesk:stockdesk@localhost:5432/stockdesk"
)
APP_ORIGIN = os.environ.get("APP_ORIGIN", "http://localhost:8080").rstrip("/")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SESSION_HOURS = 12

ALERT_WORKER_ENABLED = os.environ.get("ALERT_WORKER_ENABLED", "false").lower() == "true"
