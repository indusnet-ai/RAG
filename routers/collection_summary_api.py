"""
Collection Summary API
NotebookLM-style automatic summaries of document collections

Endpoint: GET /api/collections/{collection_name}/summary
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from db import get_db
from routers.dependencies import get_current_user
from services.collection_summary_service import CollectionSummaryService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/collections", tags=["Collection Summary"])


class SummaryResponse(BaseModel):
    """Response model for collection summary"""
    collection_name: str
    collection_id: str
    summary: str
    generated_at: str | None
    source_count: int
    cached: bool


@router.get("/{collection_name}/summary", response_model=SummaryResponse)
async def get_collection_summary(
    collection_name: str,
    regenerate: bool = Query(False, description="Force regenerate summary even if cached"),
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    📝 Get Collection Summary
    
    Returns a comprehensive NotebookLM-style summary of all documents in the collection.
    
    Features:
    - Automatically updates when new sources are added
    - Cached for performance
    - Use ?regenerate=true to force refresh
    
    Example:
        GET /api/collections/my_research/summary
        
    Returns:
        {
            "collection_name": "my_research",
            "summary": "These notes provide a comprehensive technical foundation...",
            "generated_at": "2025-02-09T10:30:00",
            "source_count": 4,
            "cached": false
        }
    """
    try:
        user_id = str(current_user.id)
        
        # Get collection ID
        collection_result = db.execute(text("""
            SELECT id, collection_name
            FROM collections
            WHERE collection_name = :cname
            AND user_id = :uid
            AND (is_deleted = FALSE OR is_deleted IS NULL)
        """), {"cname": collection_name, "uid": user_id})
        
        collection = collection_result.fetchone()
        
        if not collection:
            raise HTTPException(404, "Collection not found")
        
        collection_id = str(collection.id)
        
        # Generate/retrieve summary
        summary_service = CollectionSummaryService(db)
        summary_data = summary_service.generate_collection_summary(
            collection_id=collection_id,
            user_id=user_id,
            force_regenerate=regenerate
        )
        
        return SummaryResponse(
            collection_name=collection_name,
            collection_id=collection_id,
            summary=summary_data["summary"],
            generated_at=summary_data["generated_at"],
            source_count=summary_data["source_count"],
            cached=summary_data["cached"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting collection summary: {e}", exc_info=True)
        raise HTTPException(500, f"Error generating summary: {str(e)}")


@router.post("/{collection_name}/summary/regenerate")
async def regenerate_collection_summary(
    collection_name: str,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    🔄 Force Regenerate Summary
    
    Manually trigger summary regeneration.
    Useful if you want to update the summary without uploading new sources.
    """
    try:
        user_id = str(current_user.id)
        
        # Get collection ID
        collection_result = db.execute(text("""
            SELECT id
            FROM collections
            WHERE collection_name = :cname
            AND user_id = :uid
            AND (is_deleted = FALSE OR is_deleted IS NULL)
        """), {"cname": collection_name, "uid": user_id})
        
        collection = collection_result.fetchone()
        
        if not collection:
            raise HTTPException(404, "Collection not found")
        
        collection_id = str(collection.id)
        
        # Force regenerate
        summary_service = CollectionSummaryService(db)
        summary_data = summary_service.generate_collection_summary(
            collection_id=collection_id,
            user_id=user_id,
            force_regenerate=True
        )
        
        return {
            "status": "success",
            "message": "Summary regenerated successfully",
            "collection_name": collection_name,
            "summary": summary_data["summary"],
            "source_count": summary_data["source_count"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating summary: {e}", exc_info=True)
        raise HTTPException(500, f"Error: {str(e)}")