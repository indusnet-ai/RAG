from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from db import get_db
from routers.dependencies import get_current_user
from services.metrics import track_collection_list_request  # ✅ ADD THIS
router = APIRouter(prefix="/collections", tags=["Collections"])

@router.get("/")
def get_collections(
    db = Depends(get_db),
    current_user = Depends(get_current_user)
):
    track_collection_list_request()
    """
    Fetch all collections with chat titles.
    """
    try:
        query = text("""
            SELECT 
                id, 
                collection_name, 
                chat_title,
                created_at
            FROM collections
            WHERE user_id = :uid
            AND (is_deleted = FALSE OR is_deleted IS NULL)
            ORDER BY created_at DESC
        """)

        rows = db.execute(query, {"uid": str(current_user.id)}).fetchall()

        collections = [
            {
                "id": str(row.id),
                "collection_name": row.collection_name,
                "chat_title": row.chat_title or row.collection_name,
                "created_at": row.created_at
            }
            for row in rows
        ]

        return {
            "user_id": str(current_user.id),
            "total_collections": len(collections),
            "collections": collections
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))