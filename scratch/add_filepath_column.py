from sqlalchemy import text
from db import engine

def add_filepath():
    with engine.connect() as conn:
        try:
            print("Adding file_path to documents table...")
            conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_path VARCHAR(500);"))
            conn.commit()
            print("Successfully added file_path to documents table!")
        except Exception as e:
            print("Error altering table:", e)

if __name__ == "__main__":
    add_filepath()
