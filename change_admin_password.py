"""
change_admin_password.py
------------------------
Directly updates the password for admin@ragchat.com in the database.
Passwords are stored as plain text in this system (matching the create_user logic).

Usage:
    python change_admin_password.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# ─── Import db engine after loading env ──────────────────────────────────────
from sqlalchemy import create_engine, text as sa_text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("[ERROR] DATABASE_URL is not set in .env")
    sys.exit(1)

ADMIN_EMAIL = "admin@ragchat.com"

# ─── Ask for new password ─────────────────────────────────────────────────────
import getpass

print(f"\n🔐 Change password for: {ADMIN_EMAIL}")
new_password = getpass.getpass("  Enter new password: ")
confirm_password = getpass.getpass("  Confirm new password: ")

if new_password != confirm_password:
    print("[ERROR] Passwords do not match. Aborting.")
    sys.exit(1)

if len(new_password) < 8:
    print("[ERROR] Password must be at least 8 characters long.")
    sys.exit(1)

# ─── Connect and update ───────────────────────────────────────────────────────
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

with engine.connect() as conn:
    # Check the user exists
    result = conn.execute(
        sa_text("SELECT id, name, email, role FROM users WHERE email = :email AND (is_deleted = FALSE OR is_deleted IS NULL)"),
        {"email": ADMIN_EMAIL}
    ).fetchone()

    if not result:
        print(f"[ERROR] No active user found with email: {ADMIN_EMAIL}")
        sys.exit(1)

    print(f"\n  Found user: {result.name} | Role: {result.role}")

    # Update password (plain text, matching system convention)
    conn.execute(
        sa_text("UPDATE users SET password = :password WHERE email = :email"),
        {"password": new_password, "email": ADMIN_EMAIL}
    )
    conn.commit()

print(f"\n✅ Password updated successfully for {ADMIN_EMAIL}")
print("   You can now log in with your new password.\n")
