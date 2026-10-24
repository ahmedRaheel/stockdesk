"""Versioned SQL migrations. Applied SQL is immutable and checksum-verified."""

from pathlib import Path
import hashlib, asyncio
import asyncpg
from .config import DATABASE_URL

pool: asyncpg.Pool | None = None


async def connect():
    global pool
    pool = await asyncpg.create_pool(
        DATABASE_URL, min_size=1, max_size=10, command_timeout=30
    )
    async with pool.acquire() as c:
        await c.execute("SELECT pg_advisory_lock(78243212)")
        try:
            await c.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations(name text PRIMARY KEY,checksum text NOT NULL,applied timestamptz NOT NULL DEFAULT now())"
            )
            for path in sorted(
                (Path(__file__).resolve().parents[1] / "migrations").glob("*.sql")
            ):
                sql = path.read_text()
                digest = hashlib.sha256(sql.encode()).hexdigest()
                prior = await c.fetchval(
                    "SELECT checksum FROM schema_migrations WHERE name=$1", path.name
                )
                if prior and prior != digest:
                    raise RuntimeError(f"Applied migration modified: {path.name}")
                if not prior:
                    async with c.transaction():
                        await c.execute(sql)
                        await c.execute(
                            "INSERT INTO schema_migrations(name,checksum) VALUES($1,$2)",
                            path.name,
                            digest,
                        )
        finally:
            await c.execute("SELECT pg_advisory_unlock(78243212)")


async def close():
    if pool:
        try:
            await asyncio.wait_for(pool.close(), timeout=5)
        except TimeoutError:
            pool.terminate()
