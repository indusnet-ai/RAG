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
query = text("""
    SELECT content, page_number FROM chunks 
    WHERE content ILIKE '%Standard RAG%' 
       OR content ILIKE '%DeepRAG%' 
       OR content ILIKE '%MA-RAG%' 
       OR content ILIKE '%Corrective RAG%' 
       OR content ILIKE '%Speculative RAG%' 
       OR content ILIKE '%Fusion RAG%' 
       OR content ILIKE '%RAG-Gym%' 
       OR content ILIKE '%Modular RAG%' 
       OR content ILIKE '%SAM-RAG%'
    ORDER BY page_number, chunk_index
""")
rows = db.execute(query).fetchall()
print(f"Found {len(rows)} matching chunks in database:")
for idx, r in enumerate(rows):
    print(f"\n--- Chunk {idx+1} (Page {r.page_number}) ---")
    print(r.content)
db.close()
