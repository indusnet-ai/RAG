# document_delete.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from db import get_db
from routers.dependencies import get_current_user
import logging
from datetime import datetime
from services.metrics import track_document_deleted, track_document_restore
# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S,%f'[:-3]
)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Documents"])

@router.delete("/documents")
async def delete_document_by_collection(
    collection_name: str,
    document_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Soft delete a document and its associated chunks.
    Hard delete embeddings from langchain_embedding table.
    """
    try:
        user_id = str(current_user.id)
        logger.info(f"Soft deleting document {document_id} from collection '{collection_name}' for user {user_id}")
        
        # 1️⃣ Validate collection name + user (must not be deleted)
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
            logger.error(f"Database error while fetching collection: {str(db_error)}")
            raise HTTPException(500, f"Database error: {str(db_error)}")

        if not collection:
            logger.warning(f"Collection '{collection_name}' not found or already deleted for user {user_id}")
            raise HTTPException(404, "Collection not found or unauthorized")
        
        collection_id = collection.id
        logger.info(f"Collection validated: {collection_id}")

        # 2️⃣ Validate document inside the collection (must not be deleted)
        try:
            doc = db.execute(text("""
                SELECT id, file_name
                FROM documents
                WHERE id = :doc 
                AND collection_id = :cid 
                AND user_id = :uid
                AND (is_deleted = FALSE OR is_deleted IS NULL)
            """), {
                "doc": document_id,
                "cid": collection_id,
                "uid": user_id
            }).fetchone()
        except Exception as db_error:
            logger.error(f"Database error while fetching document: {str(db_error)}")
            raise HTTPException(500, f"Database error: {str(db_error)}")

        if not doc:
            logger.warning(f"Document {document_id} not found or already deleted in collection {collection_id}")
            raise HTTPException(404, "Document not found in this collection or already deleted")

        doc_file_name = doc.file_name

        # 3️⃣ Get chunk IDs BEFORE soft deleting them
        try:
            chunk_ids_result = db.execute(text("""
                SELECT id FROM chunks
                WHERE document_id = :doc
                AND (is_deleted = FALSE OR is_deleted IS NULL)
            """), {"doc": document_id}).fetchall()
            
            chunk_ids = [str(row.id) for row in chunk_ids_result]
            logger.info(f"Found {len(chunk_ids)} chunks to delete")
        except Exception as db_error:
            logger.error(f"Database error while fetching chunks: {str(db_error)}")
            raise HTTPException(500, f"Error fetching chunks: {str(db_error)}")

        # 4️⃣ Soft delete chunks
        try:
            logger.info(f"Soft deleting chunks for document {document_id}")
            chunk_result = db.execute(text("""
                UPDATE chunks 
                SET is_deleted = TRUE
                WHERE document_id = :doc 
                AND (is_deleted = FALSE OR is_deleted IS NULL)
            """), {
                "doc": document_id
            })
            deleted_chunks = chunk_result.rowcount
            logger.info(f"Soft deleted {deleted_chunks} chunks")
        except Exception as db_error:
            logger.error(f"Database error while soft deleting chunks: {str(db_error)}")
            db.rollback()
            raise HTTPException(500, f"Error soft deleting chunks: {str(db_error)}")

        # 🆕 5️⃣ Hard delete embeddings from langchain_embedding table
        try:
            if chunk_ids:
                logger.info(f"Hard deleting embeddings for {len(chunk_ids)} chunks from langchain_embedding table")
                
                # Initialize memory layer
                from services.memory_service import PersistentMemoryLayer
                memory_layer = PersistentMemoryLayer(
                    user_id=user_id,
                    collection_id=str(collection_id)
                )
                
                # ✅ HARD DELETE embeddings (completely remove rows)
                deleted_count = memory_layer.hard_delete_embeddings(
                    chunk_ids=chunk_ids,
                    source_file=doc_file_name
                )
                logger.info(f"✅ Hard deleted {deleted_count} embeddings from langchain_embedding table")
            else:
                logger.warning("No chunks found, skipping embedding deletion")
                
        except Exception as mem_error:
            logger.error(f"Error deleting embeddings (non-critical): {str(mem_error)}", exc_info=True)
        # 🆕 6️⃣ Soft delete queries that reference this document's chunks
        try:
            if chunk_ids:
                logger.info("Soft deleting queries referencing deleted document")

                query_result = db.execute(text("""
                    UPDATE queries
                    SET
                        is_deleted = TRUE
                    WHERE
                        user_id = :uid
                        AND collection_id = :cid
                        AND (is_deleted IS NULL OR is_deleted = FALSE)
                        AND EXISTS (
                            SELECT 1
                            FROM jsonb_array_elements(COALESCE(sources_used, '[]')::jsonb) AS src
                            WHERE EXISTS (
                                SELECT 1
                                FROM jsonb_array_elements_text(src->'chunk_ids') AS cid
                                WHERE cid = ANY(:chunk_ids)
                            )
                        )
                """), {
                    "uid": user_id,
                    "cid": collection_id,
                    "chunk_ids": chunk_ids
                })

                logger.info(f"✅ Soft deleted {query_result.rowcount} queries")
            else:
                logger.info("No chunk_ids found, skipping query deletion")

        except Exception as q_error:
            logger.error(f"Error soft deleting queries (non-critical): {str(q_error)}", exc_info=True)

        # 6️⃣ Soft delete document
        try:
            logger.info(f"Soft deleting document {document_id}")
            db.execute(text("""
                UPDATE documents 
                SET is_deleted = TRUE
                WHERE id = :doc
            """), {
                "doc": document_id
            })
        except Exception as db_error:
            logger.error(f"Database error while soft deleting document: {str(db_error)}")
            db.rollback()
            raise HTTPException(500, f"Error soft deleting document: {str(db_error)}")

        try:
            db.commit()
            track_document_deleted()
            logger.info(f"Successfully soft deleted document {document_id} and {deleted_chunks} chunks from collection {collection_name}")
        except Exception as commit_error:
            logger.error(f"Error committing transaction: {str(commit_error)}")
            db.rollback()
            raise HTTPException(500, f"Error committing changes: {str(commit_error)}")

        return {
            "status": "success",
            "message": "Document deleted successfully.",
            "chunks_deleted": deleted_chunks,
            "collection_name": collection_name,
            "document_id": document_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in delete_document_by_collection: {str(e)}", exc_info=True)
        try:
            db.rollback()
        except:
            pass
        raise HTTPException(500, detail=f"Error deleting document: {str(e)}")


@router.post("/documents/restore")
async def restore_document(
    collection_name: str,
    document_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Restore a soft-deleted document and its associated chunks.
    Also restores the collection if it was soft-deleted.
    """
    try:
        user_id = str(current_user.id)
        logger.info(f"Restoring document {document_id} in collection '{collection_name}' for user {user_id}")
        
        # Find the collection (even if deleted)
        collection = db.execute(text("""
            SELECT id, is_deleted
            FROM collections
            WHERE collection_name = :cname AND user_id = :uid
        """), {
            "cname": collection_name,
            "uid": user_id
        }).fetchone()

        if not collection:
            raise HTTPException(404, "Collection not found")
        
        collection_id = collection.id
        
        # Restore collection if it was deleted
        if collection.is_deleted:
            db.execute(text("""
                UPDATE collections 
                SET is_deleted = FALSE
                WHERE id = :cid
            """), {"cid": collection_id})
            logger.info(f"Restored collection {collection_id}")
        
        # Restore document
        doc_result = db.execute(text("""
            UPDATE documents 
            SET is_deleted = FALSE
            WHERE id = :doc AND collection_id = :cid AND user_id = :uid
        """), {
            "doc": document_id,
            "cid": collection_id,
            "uid": user_id
        })
        
        if doc_result.rowcount == 0:
            raise HTTPException(404, "Document not found")
        
        # Restore chunks
        chunk_result = db.execute(text("""
            UPDATE chunks 
            SET is_deleted = FALSE
            WHERE document_id = :doc
        """), {"doc": document_id})

        # 🆕 Restore associated memories
        try:
            # Get document filename
            doc_info = db.execute(text("""
                SELECT file_name 
                FROM documents 
                WHERE id = :doc
            """), {"doc": document_id}).fetchone()
            
            if doc_info and doc_info.file_name:
                logger.info(f"Restoring memories for document: {doc_info.file_name}")
                
                # Initialize memory layer
                from services.memory_service import PersistentMemoryLayer
                memory_layer = PersistentMemoryLayer(
                    user_id=user_id,
                    collection_id=collection_id
                )
                
                # Restore memories
                restored_count = memory_layer.restore_memories(
                    document_id=document_id,
                    source_file=doc_info.file_name
                )
                logger.info(f"✅ Restored {restored_count} memories")
                
        except Exception as mem_error:
            logger.error(f"Error restoring memories (non-critical): {str(mem_error)}")
        
        # Commit all changes
        db.commit()
        track_document_restore()
        
        return {
            "status": "success",
            "message": "Document restored successfully",
            "document_id": document_id,
            "chunks_restored": chunk_result.rowcount
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring document: {str(e)}")
        db.rollback()
        raise HTTPException(500, detail=f"Error restoring document: {str(e)}")