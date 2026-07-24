import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

# Add parent directory to path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from db import SessionLocal
from sqlalchemy import text

db = SessionLocal()

pages_to_print = [3, 4, 10]
for page in pages_to_print:
    print(f"\n==========================================")
    print(f"PAGE {page} CONTENT CHUNKS")
    print(f"==========================================")
    query = text("""
        SELECT content FROM chunks 
        WHERE page_number = :page
        ORDER BY chunk_index
    """)
    rows = db.execute(query, {"page": page}).fetchall()
    for idx, r in enumerate(rows):
        print(f"\n--- Chunk {idx+1} ---")
        print(r.content)

db.close()
