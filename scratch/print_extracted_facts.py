import sys
import os
import json

# Add parent directory to path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from db import SessionLocal
from sqlalchemy import text
from services.embedding_generator import EmbeddingGenerator
from services.rag_generation import RAGGenerator
from context_builder import _extract_facts_from_batch

db = SessionLocal()
embedder = EmbeddingGenerator()
rag = RAGGenerator(embedding_generator=embedder, db=db)

# Retrieve all chunks
simple_query = text("""
    SELECT c.content FROM chunks c
    WHERE (c.is_deleted = FALSE OR c.is_deleted IS NULL)
    ORDER BY c.page_number, c.chunk_index
""")
rows = db.execute(simple_query).fetchall()
chunks = [{"content": r[0]} for r in rows]

print(f"Running Map phase over {len(chunks)} chunks...")
all_facts = []
batch_size = 5
for i in range(0, len(chunks), batch_size):
    batch = chunks[i : i + batch_size]
    combined = "\n\n".join(c.get("content", "") for c in batch)
    batch_facts = _extract_facts_from_batch(rag, combined)
    all_facts.extend(batch_facts)

print("\n=== EXTRACTED FACTS IN MAP PHASE ===")
print(json.dumps(all_facts, indent=2))
db.close()
