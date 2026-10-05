#!/usr/bin/env python3
"""Create/update the two admin users from backend/.env (port of scripts/seedUsers.js).

  python backend/scripts/seed_users.py
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / '.env')

from config.database import admin_users_from_env, hash_password, initialize_database  # noqa: E402
from models import user as User  # noqa: E402


def seed_users():
    users = admin_users_from_env()
    if len(users) < 2:
        raise SystemExit('Both admin user credentials (ADMIN1_*, ADMIN2_*) must be set in backend/.env')
    status = initialize_database()
    for u in users:
        User.upsert_by_email(u['username'], u['email'], hash_password(u['password']), 'admin')
        print(f"Seeded {u['username']} ({u['email']})")
    print(f"User seed complete ({status['engine']}). Re-running this command updates these two users without duplicates.")


if __name__ == '__main__':
    seed_users()
