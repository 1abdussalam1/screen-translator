#!/usr/bin/env python3
"""
CLI script to create or reset admin accounts.
Run from the server/ directory:
    python setup_admin.py --username admin --password MySecurePass123
"""
import argparse
import asyncio
import sys
import os

# Ensure src package is importable
sys.path.insert(0, os.path.dirname(__file__))

import bcrypt
from sqlalchemy import select
from src.db import AsyncSessionLocal, create_all_tables
from src.models.database import Admin


async def create_or_update_admin(username: str, password: str) -> None:
    await create_all_tables()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Admin).where(Admin.username == username))
        existing = result.scalar_one_or_none()

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        if existing:
            existing.password_hash = password_hash
            db.add(existing)
            print(f"[OK] Password updated for admin '{username}'")
        else:
            admin = Admin(username=username, password_hash=password_hash)
            db.add(admin)
            print(f"[OK] Admin '{username}' created successfully")

        await db.commit()


def main():
    parser = argparse.ArgumentParser(description="Create or update an admin account")
    parser.add_argument("--username", required=True, help="Admin username")
    parser.add_argument("--password", required=True, help="Admin password")
    args = parser.parse_args()

    if len(args.password) < 8:
        print("[ERROR] Password must be at least 8 characters", file=sys.stderr)
        sys.exit(1)

    asyncio.run(create_or_update_admin(args.username, args.password))


if __name__ == "__main__":
    main()
