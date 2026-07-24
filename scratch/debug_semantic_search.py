import traceback
from db import SessionLocal, text
from services.hybrid_search import _search_semantic
import numpy as np

db = SessionLocal()
try:
    # Get a user and collection to test
    cursor = db.execute(text("SELECT user_id, collection_id FROM chunks LIMIT 1"))
    row = cursor.fetchone()
    if row:
        uid, cid = row[0], row[1]
        print(f"Testing with uid={uid}, cid={cid}")
        # Generate dummy 3072 dim query vector
        query_vector = [0.1] * 3072
        _search_semantic(db, query_vector, uid, cid, limit=5)
    else:
        print("No chunks found in database.")
except Exception as e:
    traceback.print_exc()
finally:
    db.close()
