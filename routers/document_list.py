from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from db import get_db
from routers.dependencies import get_current_user
from urllib.parse import urlparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S,%f'[:-3]
)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Documents"])


@router.get("/documents")
async def list_documents_by_collection_name(
    collection_name: str,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Get all documents in a collection.
    
    Returns file_path for frontend to fetch files directly.
    """
    try:
        user_id = str(current_user.id)
        logger.info(f"Listing documents for user {user_id}, collection: {collection_name}")
        
        # Validate collection
        collection = db.execute(text("""
            SELECT id, collection_name 
            FROM collections
            WHERE collection_name = :cname 
            AND user_id = :uid
            AND (is_deleted = FALSE OR is_deleted IS NULL)
        """), {
            "cname": collection_name,
            "uid": user_id
        }).fetchone()

        if not collection:
            logger.warning(f"Collection '{collection_name}' not found")
            raise HTTPException(404, "Collection not found")

        # Fetch documents with file_path
        rows = db.execute(text("""
            SELECT 
                id, file_name, file_type, chunk_count,
                uploaded_at, source_url, file_path
            FROM documents
            WHERE collection_id = :cid 
            AND user_id = :uid
            AND (is_deleted = FALSE OR is_deleted IS NULL)
            ORDER BY uploaded_at DESC
        """), {
            "cid": collection.id,
            "uid": user_id
        }).fetchall()

        # Build response
        documents = []
        for row in rows:
            doc = dict(row._mapping)
            
            # Add frontend-friendly fields
            doc['is_clickable'] = True
            doc['icon'] = _get_source_icon(doc['file_type'])
            doc['display_name'] = _get_display_name(doc)
            
            # ✨ NEW: Return file_path for frontend
            # Frontend can access: http://localhost:8000/{file_path}
            # Example: http://localhost:8000/uploaded_files/chat_20260202_121204/abc-123.pdf
            doc['file_url'] = _get_file_url(doc, collection_name)
            
            documents.append(doc)

        logger.info(f"✅ Fetched {len(documents)} documents")

        return {
            "collection_name": collection.collection_name,
            "collection_id": str(collection.id),
            "documents": documents
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(500, str(e))


def _get_file_url(doc: dict, collection_name: str) -> str:
    """
    Get file URL for frontend.
    
    Returns the file_path which frontend can fetch directly.
    """
    file_type = doc.get('file_type', '').lower()
    source_url = doc.get('source_url')
    file_path = doc.get('file_path')
    
    # External sources: YouTube, Web
    if file_type in ['youtube', 'web', 'website'] and source_url:
        return source_url
    
    # Uploaded files: Return file_path
    # Frontend will access: http://localhost:8000/{file_path}
    if file_path:
        return f"/{file_path}"  # Prepend / for absolute URL
    
    # Fallback if file_path not in DB (shouldn't happen)
    doc_id = doc.get('id')
    extension = _get_extension_from_type(file_type)
    return f"/uploaded_files/{collection_name}/{doc_id}{extension}"


def _get_extension_from_type(file_type: str) -> str:
    """Get file extension from file type"""
    extensions = {
        'pdf': '.pdf',
        'docx': '.docx',
        'txt': '.txt',
        'md': '.md',
        'excel': '.xlsx',
        'csv': '.csv',
        'image': '.png'
    }
    return extensions.get(file_type.lower(), '')


def _get_source_icon(file_type: str) -> str:
    """Get icon for file type"""
    icon_map = {
        'pdf': 'file-pdf',
        'docx': 'file-word',
        'txt': 'file-text',
        'md': 'file-code',
        'excel': 'file-excel',
        'csv': 'file-spreadsheet',
        'image': 'file-image',
        'youtube': 'youtube',
        'web': 'globe',
        'website': 'globe',
        'text': 'file-text',
        'audio': 'file-audio'
    }
    return icon_map.get(file_type.lower(), 'file')


def _get_display_name(doc: dict) -> str:
    """Get display name"""
    file_type = doc.get('file_type', '').lower()
    file_name = doc.get('file_name', 'Untitled')
    
    if file_type == 'youtube':
        return file_name
    
    if file_type in ['web', 'website']:
        source_url = doc.get('source_url', '')
        if source_url:
            try:
                domain = urlparse(source_url).netloc.replace('www.', '')
                if domain:
                    return f"Web: {domain}"
            except:
                pass
        return file_name or "Web Page"
    
    return file_name