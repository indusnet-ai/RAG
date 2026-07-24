from sqlalchemy import text
from db import engine

def fix_schema():
    with engine.connect() as conn:
        try:
            print("Adding is_deleted to users table...")
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;"))
            conn.commit()
            print("Successfully added is_deleted to users table!")
        except Exception as e:
            print("Error altering table:", e)

if __name__ == "__main__":
    fix_schema()
