"""Emergency admin recovery — deletes ALL dashboard users + lockout records so
the first-run setup flow re-opens. API keys, alert settings, and all market
data are untouched.

Usage:  cd /app/backend && python reset_admin.py
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


async def main():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    database = client[os.environ['DB_NAME']]
    res = await database.users.delete_many({})
    await database.login_attempts.delete_many({})
    print(f"Deleted {res.deleted_count} user(s) and cleared lockouts.")
    print("Setup flow is open again — open the dashboard to create a new admin account.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
