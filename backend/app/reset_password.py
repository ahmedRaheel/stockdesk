"""Server-operator recovery: python -m app.reset_password user@example.com.
Prompts privately; never accepts a password as a command-line argument.
"""

import asyncio, getpass, sys
from . import db, security
from .rules import email


async def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.reset_password EMAIL")
    address = email(sys.argv[1])
    value = getpass.getpass("New password (12+ characters): ")
    if value != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords do not match.")
    hashed = await security.hash_password(value)
    await db.connect()
    try:
        async with db.pool.acquire() as c:
            async with c.transaction():
                user = await c.fetchrow(
                    "UPDATE users SET password_hash=$1 WHERE email=$2 RETURNING id",
                    hashed,
                    address,
                )
                if not user:
                    raise SystemExit("Account not found.")
                await c.execute("DELETE FROM sessions WHERE user_id=$1", user["id"])
        print("Password updated; existing sessions revoked.")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
