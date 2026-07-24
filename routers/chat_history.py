from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from db import get_db
from routers.dependencies import get_current_user
import logging
from services.metrics import track_collection_deleted, track_chat_history_request
# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S,%f'[:-3]
)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Chat History"])


@router.get("/chat/history")
async def get_chat_history(
    collection_name: str,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Fetch chat history for a collection.
    Returns chat_title from database (generated during first query).
    """
    track_chat_history_request()
    try:
        user_id = str(current_user.id)
        logger.info(f"Fetching chat history for user {user_id}, collection: {collection_name}")
        
        # Validate collection and get chat_title from database
        try:
            collection = db.execute(text("""
                SELECT id, collection_name, chat_title
                FROM collections
                WHERE collection_name = :cname AND user_id = :uid
                AND (is_deleted = FALSE OR is_deleted IS NULL)
            """), {
                "cname": collection_name,
                "uid": user_id
            }).fetchone()
        except Exception as db_error:
            logger.error(f"Database error while fetching collection: {str(db_error)}")
            raise HTTPException(500, f"Database error: {str(db_error)}")

        if not collection:
            logger.warning(f"Collection '{collection_name}' not found for user {user_id}")
            raise HTTPException(404, "Collection not found or unauthorized")

        collection_id = collection.id
        # Read chat_title from database, fallback to collection_name
        chat_title = collection.chat_title or collection_name
        logger.info(f"Collection found: {collection_id}, chat_title: {chat_title}")

        # Fetch chat history
        try:
            rows = db.execute(text("""
                SELECT 
                    id,
                    query_text,
                    response_text,
                    sources_used,
                    created_at,
                    reference_map
                FROM queries
                WHERE collection_id = :cid AND user_id = :uid
                AND (is_deleted = FALSE OR is_deleted IS NULL)
                ORDER BY created_at ASC
            """), {
                "cid": collection_id,
                "uid": user_id
            }).fetchall()
        except Exception as db_error:
            logger.error(f"Database error while fetching queries: {str(db_error)}")
            raise HTTPException(500, f"Database error: {str(db_error)}")

        history = [dict(r._mapping) for r in rows]
        logger.info(f"Successfully fetched {len(history)} messages")

        return {
            "collection_name": collection_name,
            "collection_id": str(collection_id),
            "chat_title": chat_title,
            "messages": history,
            "message_count": len(history)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_chat_history: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=f"Error fetching chat history: {str(e)}")


@router.delete("/chat/history-delete")
async def delete_chat_history_and_collection(
    collection_name: str,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Soft delete all chat history and the entire collection.
    """
    try:
        user_id = str(current_user.id)
        logger.info(f"Starting soft delete of collection '{collection_name}'")
        
        # Validate collection
        try:
            collection = db.execute(text("""
                SELECT id
                FROM collections
                WHERE collection_name = :cname 
                AND user_id = :uid
                AND (is_deleted = FALSE OR is_deleted IS NULL)
            """), {
                "cname": collection_name,
                "uid": user_id
            }).fetchone()
        except Exception as db_error:
            logger.error(f"Database error: {str(db_error)}")
            raise HTTPException(500, f"Database error: {str(db_error)}")

        if not collection:
            logger.warning(f"Collection not found or already deleted")
            raise HTTPException(404, "Collection not found or already deleted")

        collection_id = collection.id

        # Soft delete queries
        try:
            query_result = db.execute(text("""
                UPDATE queries 
                SET is_deleted = TRUE
                WHERE collection_id = :cid AND user_id = :uid
                AND (is_deleted = FALSE OR is_deleted IS NULL)
            """), {"cid": collection_id, "uid": user_id})
            deleted_queries = query_result.rowcount
        except Exception as db_error:
            logger.error(f"Error deleting queries: {str(db_error)}")
            db.rollback()
            raise HTTPException(500, f"Error deleting queries: {str(db_error)}")

        # Get documents and soft delete chunks
        try:
            documents = db.execute(text("""
                SELECT id FROM documents
                WHERE collection_id = :cid AND user_id = :uid
                AND (is_deleted = FALSE OR is_deleted IS NULL)
            """), {"cid": collection_id, "uid": user_id}).fetchall()
            
            total_deleted_chunks = 0
            for doc in documents:
                chunk_result = db.execute(text("""
                    UPDATE chunks 
                    SET is_deleted = TRUE
                    WHERE document_id = :doc_id
                    AND (is_deleted = FALSE OR is_deleted IS NULL)
                """), {"doc_id": doc.id})
                total_deleted_chunks += chunk_result.rowcount
            
            total_deleted_docs = len(documents)
        except Exception as db_error:
            logger.error(f"Error deleting chunks: {str(db_error)}")
            db.rollback()
            raise HTTPException(500, f"Error deleting chunks: {str(db_error)}")

        # Soft delete documents
        try:
            db.execute(text("""
                UPDATE documents 
                SET is_deleted = TRUE
                WHERE collection_id = :cid AND user_id = :uid
                AND (is_deleted = FALSE OR is_deleted IS NULL)
            """), {"cid": collection_id, "uid": user_id})
        except Exception as db_error:
            logger.error(f"Error deleting documents: {str(db_error)}")
            db.rollback()
            raise HTTPException(500, f"Error deleting documents: {str(db_error)}")

        # Soft delete collection
        try:
            db.execute(text("""
                UPDATE collections 
                SET is_deleted = TRUE
                WHERE id = :cid
            """), {"cid": collection_id})
        except Exception as db_error:
            logger.error(f"Error deleting collection: {str(db_error)}")
            db.rollback()
            raise HTTPException(500, f"Error deleting collection: {str(db_error)}")

        # Commit all changes
        try:
            db.commit()
            track_collection_deleted()
            logger.info(f"Successfully deleted collection")
        except Exception as commit_error:
            logger.error(f"Error committing: {str(commit_error)}")
            db.rollback()
            raise HTTPException(500, f"Error committing: {str(commit_error)}")

        return {
            "status": "success",
            "message": "Collection and all data soft deleted.",
            "collection_name": collection_name,
            "collection_id": str(collection_id),
            "queries_deleted": deleted_queries,
            "documents_deleted": total_deleted_docs,
            "chunks_deleted": total_deleted_chunks
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        try:
            db.rollback()
        except:
            pass
        raise HTTPException(500, detail=f"Error deleting: {str(e)}")