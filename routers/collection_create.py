from fastapi import APIRouter, Depends, HTTPException
from uuid import uuid4
from sqlalchemy import text
from datetime import datetime
from db import get_db
from routers.dependencies import get_current_user
import logging
from services.metrics import track_collection_created, track_collection_size  # ✅ ADD track_collection_size
# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S,%f'[:-3]  # Format: 2025-11-26 10:16:19,580
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Collections"])


@router.post("/collections/create")
async def create_collection(
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Create a new collection for the authenticated user.
    This should be called when a new chat is initiated.
    Returns the collection_id and collection_name to be used in document uploads.
    """
    try:
        user_uuid = str(current_user.id)
        collection_id = uuid4()
        
        logger.info(f"Creating new collection for user {user_uuid}")
        
        # Generate a unique collection name with timestamp
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            collection_name = f"chat_{timestamp}_{str(collection_id)[:8]}"
            logger.info(f"Generated collection name: {collection_name}")
        except Exception as name_error:
            logger.error(f"Error generating collection name: {str(name_error)}")
            raise HTTPException(status_code=500, detail=f"Error generating collection name: {str(name_error)}")

        # Insert new collection
        try:
            db.execute(text("""
                INSERT INTO collections (id, user_id, collection_name, source_type, created_at)
                VALUES (:id, :uid, :name, 'chat', NOW())
            """), {
                "id": collection_id,
                "uid": user_uuid,
                "name": collection_name
            })
        except Exception as db_error:
            logger.error(f"Database error while inserting collection: {str(db_error)}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(db_error)}")

        try:
            db.commit()
            track_collection_created()
            track_collection_size(0)  # ✅ ADD THIS (new collection has 0 docs)
            logger.info(f"Successfully created collection {collection_name} (ID: {collection_id})")
        except Exception as commit_error:
            logger.error(f"Error committing collection creation: {str(commit_error)}")
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error committing changes: {str(commit_error)}")

        return {
            "status": "success",
            "collection_id": str(collection_id),
            "collection_name": collection_name,
            "message": "Collection created successfully. Use this collection_name when uploading documents."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in create_collection: {str(e)}", exc_info=True)
        try:
            db.rollback()
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to create collection: {str(e)}")