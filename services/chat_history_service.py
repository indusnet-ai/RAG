from sqlalchemy import text
from typing import List, Dict, Any


def fetch_recent_chat_history(
    db,
    user_id: str,
    collection_id: str,
    limit: int = 3
) -> List[Dict[str, Any]]:
    """
    Fetch the last N chat turns (query + response) in correct order.
    Returned order: OLDEST → NEWEST.
    """
    result = db.execute(
        text("""
            SELECT
                query_text,
                response_text,
                created_at
            FROM queries
            WHERE user_id = :uid
              AND collection_id = :cid
              AND (is_deleted = FALSE OR is_deleted IS NULL)
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {
            "uid": user_id,
            "cid": collection_id,
            "limit": limit
        }
    ).fetchall()

    # DB gives newest → oldest, reverse it
    rows = list(reversed(result))

    return [dict(r._mapping) for r in rows]
