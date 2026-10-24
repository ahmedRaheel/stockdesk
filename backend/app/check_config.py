"""Run: docker compose run --rm --no-deps backend python -m app.check_config.
Prints no credentials, executes no migrations, and creates no records.
"""

import asyncio, os, socket
from urllib.parse import urlsplit
import asyncpg


async def main():
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL is missing from the container environment.")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port or 5432
    except ValueError:
        raise SystemExit(
            "DATABASE_URL is malformed. URL-encode password special characters."
        )
    print(f'Database host: {host}; port: {port}; database: {parsed.path.lstrip("/")}')
    if not host:
        raise SystemExit("DATABASE_URL has no hostname.")
    try:
        socket.getaddrinfo(host, port)
    except socket.gaierror:
        raise SystemExit(
            "Hostname does not resolve. Attach backend and postgres to the same external network; use the database container name."
        )
    try:
        connection = await asyncpg.connect(url, timeout=10)
    except asyncpg.InvalidPasswordError:
        raise SystemExit(
            "PostgreSQL rejected the username/password. Check DATABASE_URL."
        )
    except asyncpg.InvalidCatalogNameError:
        raise SystemExit(
            "The database does not exist. Create it on your existing PostgreSQL server."
        )
    except (OSError, asyncio.TimeoutError):
        raise SystemExit(
            "PostgreSQL could not be reached. Check the container network, port and database status."
        )
    except Exception as error:
        raise SystemExit(
            f"Connection failed: {type(error).__name__}. No credentials were printed."
        )
    try:
        print("PostgreSQL connection: OK")
        exists = await connection.fetchval(
            "SELECT to_regclass('public.users') IS NOT NULL"
        )
        admin = (
            await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM users WHERE is_admin=true)"
            )
            if exists
            else False
        )
        if not admin and not 12 <= len(os.getenv("ADMIN_PASSWORD", "")) <= 128:
            raise SystemExit("First-run ADMIN_PASSWORD must contain 12–128 characters.")
        if not admin and not os.getenv("ADMIN_EMAIL"):
            raise SystemExit("First-run ADMIN_EMAIL is required.")
        print("Configuration check passed. Startup will apply pending migrations.")
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
