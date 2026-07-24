from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
import logging
 
from routers.dependencies import get_current_user
from db import get_db
from services.metrics import track_query_edit
 
logger = logging.getLogger(__name__)
 
router = APIRouter(tags=["Query"])
 
class EditQueryRequest(BaseModel):
    query_id: str = Field(..., description="ID of the query to edit")
    new_query_text: str = Field(..., min_length=1, description="Updated query text")
    reset_response: bool = Field(
        True,
        description="If true, clears old response and sources"
    )
 
@router.put("/query/edit")
async def edit_query(
    req: EditQueryRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    user_uuid = str(current_user.id)
 
    try:
        # Verify ownership
        query_row = db.execute(
            text("""
                SELECT id
                FROM queries
                WHERE id = :qid
                  AND user_id = :uid
                  AND (is_deleted = FALSE OR is_deleted IS NULL)
            """),
            {
                "qid": req.query_id,
                "uid": user_uuid
            }
        ).fetchone()
 
        if not query_row:
            raise HTTPException(status_code=404, detail="Query not found")
 
        # Update query
        if req.reset_response:
            update_sql = """
                UPDATE queries
                SET
                    is_deleted = TRUE
                WHERE id = :qid
            """
        else:
            update_sql = """
                UPDATE queries
                SET
                    query_text = :query_text
                WHERE id = :qid
            """
 
        db.execute(
            text(update_sql),
            {
                "qid": req.query_id,
                "query_text": req.new_query_text.strip()
            }
        )
        db.commit()
        track_query_edit()
 
        return {
            "status": "success",
            "message": "Query updated successfully",
            "query_id": req.query_id
        }
 
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to edit query: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to edit query")