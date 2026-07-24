from sqlalchemy import text
from uuid import uuid4
import json
from datetime import datetime

class PostgresMemoryStore:

    def __init__(self, db, user_id, session_id):
        self.db = db
        self.user_id = str(user_id)
        self.session_id = str(session_id)

    # ---------------------------
    # Required by LangMem
    # ---------------------------
    def put(self, namespace, key, value, metadata=None):
        """Store a memory summary"""
        self.db.execute(text("""
            INSERT INTO memory_sessions (
                id, user_id, session_id, summary_text, context_state, updated_at
            )
            VALUES (:id, :uid, :sid, :summary, :meta, NOW())
        """), {
            "id": uuid4(),
            "uid": self.user_id,
            "sid": self.session_id,
            "summary": value,
            "meta": json.dumps(metadata or {})
        })
        self.db.commit()

    def get(self, namespace, key):
        """Not used much by LangMem"""
        row = self.db.execute(text("""
            SELECT summary_text, context_state
            FROM memory_sessions
            WHERE user_id = :uid AND session_id = :sid
            ORDER BY updated_at DESC LIMIT 1
        """), {
            "uid": self.user_id,
            "sid": self.session_id
        }).fetchone()

        if not row:
            return None

        return {"value": row.summary_text, "metadata": row.context_state}

    # ---------------------------
    # For recall
    # ---------------------------
    def search(self, namespace, query, limit=5):
        """Simple LIKE-based recall"""
        rows = self.db.execute(text("""
            SELECT summary_text, updated_at
            FROM memory_sessions
            WHERE user_id = :uid AND session_id = :sid
              AND summary_text ILIKE :q
            ORDER BY updated_at DESC
            LIMIT :limit
        """), {
            "uid": self.user_id,
            "sid": self.session_id,
            "q": f"%{query}%",
            "limit": limit
        }).fetchall()

        class Result:
            def __init__(self, summary, time):
                self.value = summary
                self.created_at = time
                self.score = 1.0

        return [Result(r.summary_text, r.updated_at) for r in rows]
