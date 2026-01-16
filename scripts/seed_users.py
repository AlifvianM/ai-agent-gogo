import asyncio

from sqlalchemy import insert, select

from api.auth.helpers import hash_password
from api.auth.models import user
from api.database.client import engine
from api.helpers.generators import generate_time_now

DEFAULT_EMAIL = "ai-agent@zunotrip.com"
DEFAULT_USERNAME = "ai-agent"
DEFAULT_PASSWORD = "password"

async def seed_user(email: str, username: str, password: str) -> int:
    async with engine.begin() as conn:
        existing = await conn.execute(select(user.c.id).where(user.c.email == email))
        if existing.first():
            print(f"User already exists: {email}")
            return 0

        payload = {
            "email": email,
            "username": username,
            "password": hash_password(password),
            "created_by": "seed",
            "created_at": generate_time_now(),
        }
        await conn.execute(insert(user).values(**payload))

    print(f"Seeded user: {email}")
    return 0


def main() -> int:
    return asyncio.run(seed_user(DEFAULT_EMAIL, DEFAULT_USERNAME, DEFAULT_PASSWORD))


if __name__ == "__main__":
    raise SystemExit(main())
