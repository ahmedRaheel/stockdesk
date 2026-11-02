"""Environment-level safety checks; no IO or side effects on import."""
import os
from urllib.parse import urlsplit


def production_errors(environ=None):
    env = os.environ if environ is None else environ
    if env.get('APP_ENV', 'development').strip().lower() != 'production':
        return []
    errors = []
    origin = env.get('APP_ORIGIN', '').strip()
    try:
        parsed = urlsplit(origin)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            errors.append('APP_ORIGIN must be the public HTTPS origin, with no path, credentials, or query.')
    except ValueError:
        errors.append('APP_ORIGIN is malformed.')
    if env.get('COOKIE_SECURE', '').lower() != 'true':
        errors.append('COOKIE_SECURE must be true in production.')
    db_url = env.get('DATABASE_URL', '')
    try:
        db = urlsplit(db_url)
        if db.scheme not in ('postgres', 'postgresql') or not db.hostname or not db.path.strip('/'):
            errors.append('DATABASE_URL must point to a PostgreSQL database.')
    except ValueError:
        errors.append('DATABASE_URL is malformed.')
    password = env.get('ADMIN_PASSWORD', '')
    if password and (len(password) < 14 or password.lower() in ('password', 'admin123456789', 'changeme12345678')):
        errors.append('ADMIN_PASSWORD is weak: use a randomly generated password of at least 14 characters.')
    if env.get('DEMO_SEED_CONFIRM'):
        errors.append('Do not supply DEMO_SEED_CONFIRM to production services.')
    return errors


def require_production_configuration(environ=None):
    errors = production_errors(environ)
    if errors:
        raise RuntimeError('Unsafe production configuration: ' + ' '.join(errors))
