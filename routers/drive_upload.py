from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Body, Query
from uuid import uuid4
import os
import shutil
from typing import List, Dict, Any, Optional
from sqlalchemy import text
import logging
from pathlib import Path
from pydantic import BaseModel, Field
import json
import time
import tempfile

from db import get_db
from services.document_service import DocumentService
from services.audio_service import AudioService
from services.embedding_generator import EmbeddingGenerator
from services.google_drive_service import GoogleDriveService, get_file_type_from_mime
from routers.dependencies import get_current_user
from services.metrics import (
    track_document_upload, track_upload_failure, track_embeddings_generated,
    track_text_paste, track_upload_duration, track_embedding_duration
)

router = APIRouter(tags=["Source Upload"])
UPLOAD_STORAGE_DIR = Path("uploaded_files")

def save_uploaded_file_permanently(
    temp_path: str,
    collection_name: str,
    document_id: str,
    filename: str
) -> str:
    """
    Move downloaded file from temp directory to permanent storage.
    Returns stored file path.
    """
 
    try:
        # Create directory if not exists
        collection_dir = UPLOAD_STORAGE_DIR / collection_name
        collection_dir.mkdir(parents=True, exist_ok=True)
 
        # Create unique filename
        file_extension = Path(filename).suffix
        new_filename = f"{document_id}{file_extension}"
 
        permanent_path = collection_dir / new_filename
 
        # Move file
        shutil.move(temp_path, permanent_path)
 
        logger.info(f"📦 File saved permanently at {permanent_path}")
 
        return str(permanent_path)
 
    except Exception as e:
        logger.error(f"❌ Error saving file permanently: {e}")
        return None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S,%f'[:-3]
)
logger = logging.getLogger(__name__)

doc_service = DocumentService()
embedder = EmbeddingGenerator()


class GoogleDriveUploadRequest(BaseModel):
    """Request model for Google Drive upload"""
    collection_name: str = Field(..., description="Collection to add files to")
    file_ids: List[str] = Field(..., description="Google Drive file IDs to upload")
    language: str = Field("en-IN", description="Language for audio transcription")


class GoogleDriveBrowseRequest(BaseModel):
    """Request model for browsing Google Drive"""
    folder_id: Optional[str] = Field(None, description="Folder ID to browse (default: root)")
    search_query: Optional[str] = Field(None, description="Search query")
    filter_type: Optional[str] = Field(None, description="Filter by type (pdf, docx, etc.)")
    recent_days: Optional[int] = Field(None, description="Get files from last N days")
    starred_only: bool = Field(False, description="Only show starred files")
    page_size: int = Field(100, description="Number of results per page")


@router.post("/google-drive/browse")
async def browse_google_drive(
    request: GoogleDriveBrowseRequest,
    current_user=Depends(get_current_user),
):
    """
    📁 Browse Google Drive files and folders
    
    Browse, search, and filter files from Google Drive before uploading.
    """
    try:
        logger.info(f"🔍 Browsing Google Drive for user {current_user.id}")
        
        # Initialize Google Drive service
        drive_service = GoogleDriveService()
        
        results = {
            "files": [],
            "folders": [],
            "total_files": 0,
            "total_folders": 0
        }
        
        # List folders
        folders = drive_service.list_folders(request.folder_id or 'root')
        results["folders"] = folders
        results["total_folders"] = len(folders)
        
        # Get files based on filters
        if request.starred_only:
            # Get starred files
            files = drive_service.get_starred_files(request.page_size)
        elif request.recent_days:
            # Get recent files
            files = drive_service.get_recent_files(request.recent_days, request.page_size)
        elif request.search_query:
            # Search files
            files = drive_service.search_files(request.search_query, page_size=request.page_size)
        else:
            # List files in current folder
            files = drive_service.list_files(request.folder_id, page_size=request.page_size)
        
        # Apply type filter if specified
        if request.filter_type and files:
            filtered_files = []
            for file in files:
                file_type = get_file_type_from_mime(file['mime_type'], file['name'])
                if file_type == request.filter_type:
                    filtered_files.append(file)
            files = filtered_files
        
        results["files"] = files
        results["total_files"] = len(files)
        
        # Add folder breadcrumb if not root
        breadcrumbs = []
        if request.folder_id and request.folder_id != 'root':
            try:
                folder_info = drive_service.get_file(request.folder_id)
                breadcrumbs.append({
                    "id": folder_info['id'],
                    "name": folder_info['name']
                })
            except:
                pass
        
        results["breadcrumbs"] = breadcrumbs
        results["current_folder_id"] = request.folder_id or 'root'
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Error browsing Google Drive: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error browsing Google Drive: {str(e)}")


@router.post("/google-drive/upload")
async def upload_from_google_drive(
    request: GoogleDriveUploadRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    📥 Upload files from Google Drive
    
    Upload files directly from Google Drive by their IDs.
    The system automatically detects file types and processes them appropriately.
    """
    upload_start_time = time.time()
    
    try:
        user_uuid = str(current_user.id)
        logger.info(
            f"📁 Google Drive upload request from user {user_uuid} "
            f"for collection '{request.collection_name}' - {len(request.file_ids)} files"
        )
        
        # Verify collection exists
        collection_result = db.execute(text("""
            SELECT id FROM collections 
            WHERE collection_name = :name AND user_id = :uid
        """), {"name": request.collection_name, "uid": user_uuid})

        collection_row = collection_result.fetchone()

        if not collection_row:
            logger.warning(f"Collection '{request.collection_name}' not found")
            raise HTTPException(
                status_code=404, 
                detail=f"Collection '{request.collection_name}' not found. Please create it first."
            )

        collection_id = collection_row.id
        logger.info(f"✓ Collection validated: {collection_id}")
        
        # Initialize services
        drive_service = GoogleDriveService()
        audio_service = None
        
        results = []
        
        for file_id in request.file_ids:
            try:
                document_id = uuid4()
                
                # Get file metadata from Google Drive
                logger.info(f"📄 Getting file info: {file_id}")
                file_metadata = drive_service.get_file(file_id)
                filename = file_metadata['name']
                
                # Determine file type
                file_type = get_file_type_from_mime(
                    file_metadata['mime_type'], 
                    filename
                )
                
                if file_type == 'unknown':
                    logger.warning(f"Unsupported file type: {filename}")
                    results.append({
                        "file_id": file_id,
                        "file_name": filename,
                        "status": "failed",
                        "error": f"Unsupported file type: {file_metadata['mime_type']}"
                    })
                    continue
                
                file_emoji = "🎵" if file_type == "audio" else "📄"
                logger.info(f"{file_emoji} Processing from Google Drive: {filename} (type: {file_type})")
                
                # Download file to temp location
                temp_dir = tempfile.mkdtemp()
                temp_path = os.path.join(temp_dir, filename)
                
                try:
                    downloaded_path = drive_service.download_file(file_id, temp_path)
                except Exception as download_error:
                    logger.error(f"❌ Download error: {str(download_error)}")
                    results.append({
                        "file_id": file_id,
                        "file_name": filename,
                        "status": "failed",
                        "error": f"Download failed: {str(download_error)}"
                    })
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    continue
                
                # Process file based on type
                try:
                    if file_type == 'audio':
                        # Initialize audio service if needed
                        if audio_service is None:
                            sarvam_api_key = os.getenv("SARVAM_API_KEY")
                            if not sarvam_api_key:
                                raise HTTPException(
                                    status_code=500,
                                    detail="SARVAM_API_KEY not configured. Cannot process audio files."
                                )
                            audio_service = AudioService(sarvam_api_key=sarvam_api_key)
                            logger.info("🎙️ Audio service initialized")
                        
                        # Process audio
                        logger.info(f"🎙️ Transcribing audio from Google Drive...")
                        chunks = audio_service.process_uploaded_audio(
                            temp_path=downloaded_path,
                            original_name=filename,
                            language=request.language
                        )
                        logger.info(f"✓ Audio processed: {len(chunks)} chunks")
                    else:
                        # Process as document
                        chunks = doc_service.process_uploaded_file(downloaded_path, filename)
                        logger.info(f"✓ Document processed: {len(chunks)} chunks")
                        
                except Exception as process_error:
                    error_msg = str(process_error)
                    error_type = "Audio transcription" if file_type == 'audio' else "Document processing"
                    logger.error(f"❌ {error_type} error: {error_msg}")
                    
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    
                    results.append({
                        "file_id": file_id,
                        "file_name": filename,
                        "file_type": file_type,
                        "status": "failed",
                        "error": f"{error_type} failed: {error_msg}"
                    })
                    continue

                # Generate embeddings
                try:
                    embedding_start = time.time()
                    embedded_chunks = embedder.generate_embeddings(chunks)
                    track_embedding_duration(time.time() - embedding_start)
                    track_embeddings_generated(len(embedded_chunks))
                    logger.info(f"✓ Generated {len(embedded_chunks)} embeddings")
                except Exception as embed_error:
                    logger.error(f"❌ Embedding error: {str(embed_error)}")
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    results.append({
                        "file_id": file_id,
                        "file_name": filename,
                        "file_type": file_type,
                        "status": "failed",
                        "error": f"Embedding generation failed: {str(embed_error)}"
                    })
                    continue

                # Store in database
                try:
                    # Save file permanently
                    file_path = save_uploaded_file_permanently(
                        temp_path=downloaded_path,
                        collection_name=request.collection_name,
                        document_id=str(document_id),
                        filename=filename
                    )
                    
                    if not file_path:
                        raise Exception("Failed to save file permanently")

                    # Insert document record
                    db.execute(text("""
                        INSERT INTO documents (
                            id, collection_id, user_id, file_name, 
                            file_type, chunk_count, file_path,
                            source, external_id, source_url
                        )
                        VALUES (:id, :cid, :uid, :fname, :ftype, :count, :fpath, :source, :ext_id, :ext_url)
                    """), {
                        "id": document_id,
                        "cid": collection_id,
                        "uid": user_uuid,
                        "fname": filename,
                        "ftype": file_type,
                        "count": len(embedded_chunks),
                        "fpath": file_path,
                        "source": "google_drive",
                        "ext_id": file_id,
                        "ext_url": file_metadata.get('web_view_link', '')
                    })
                    logger.info(f"Document record inserted: {document_id} (type: {file_type})")
                    
                except Exception as doc_error:
                    logger.error(f"Database error inserting document: {str(doc_error)}")
                    db.rollback()
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    results.append({
                        "file_id": file_id,
                        "file_name": filename,
                        "status": "failed",
                        "error": f"Database error: {str(doc_error)}"
                    })
                    continue

                # Insert chunks
                try:
                    for emb in embedded_chunks:
                        c = emb.chunk
                        vector_data = emb.embedding.tolist()
                        vector_str = f"[{','.join(map(str, vector_data))}]"
                        
                        # Serialize metadata
                        metadata_json = json.dumps(c.metadata) if hasattr(c, 'metadata') and c.metadata else '{}'

                        db.execute(text("""
                            INSERT INTO chunks (
                                id, document_id, collection_id, user_id,
                                chunk_index, start_char, end_char,
                                content, vector, source_type,
                                source_file, page_number,
                                embedding_model, metadata, created_at
                            )
                            VALUES (
                                :id, :doc, :cid, :uid,
                                :idx, :start, :end,
                                :content, CAST(:vector AS vector), :stype,
                                :source_file, :page_num,
                                :emb_model, :metadata, CURRENT_TIMESTAMP
                            )
                        """), {
                            "id": uuid4(),
                            "doc": document_id,
                            "cid": collection_id,
                            "uid": user_uuid,
                            "idx": c.chunk_index,
                            "start": c.start_char,
                            "end": c.end_char,
                            "content": c.content,
                            "vector": vector_str,
                            "stype": c.source_type,
                            "source_file": filename,
                            "page_num": c.page_number if hasattr(c, 'page_number') else None,
                            "emb_model": "text-embedding-3-large",
                            "metadata": metadata_json
                        })
                    logger.info(f"Inserted {len(embedded_chunks)} chunks for document {document_id}")
                    
                except Exception as chunk_error:
                    logger.error(f"Database error inserting chunks: {str(chunk_error)}")
                    db.rollback()
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    results.append({
                        "file_id": file_id,
                        "file_name": filename,
                        "status": "failed",
                        "error": f"Chunk insertion error: {str(chunk_error)}"
                    })
                    continue

                # Commit and cleanup
                try:
                    db.commit()
                    track_document_upload(file_type)
                    upload_duration = time.time() - upload_start_time
                    track_upload_duration(file_type, upload_duration)
                    
                    # Cleanup temp directory
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    
                    logger.info(f"✅ Google Drive upload success: {filename}")
                    
                except Exception as db_error:
                    logger.error(f"❌ Database commit error: {str(db_error)}")
                    db.rollback()
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    results.append({
                        "file_id": file_id,
                        "file_name": filename,
                        "status": "failed",
                        "error": f"Database error: {str(db_error)}"
                    })
                    continue

                # Build success response
                result_data = {
                    "file_id": file_id,
                    "file_name": filename,
                    "file_type": file_type,
                    "collection_id": str(collection_id),
                    "collection_name": request.collection_name,
                    "document_id": str(document_id),
                    "chunks_inserted": len(embedded_chunks),
                    "file_path": file_path,
                    "source_url": file_metadata.get('web_view_link', ''),
                    "status": "success"
                }
                
                # Add audio insights
                if file_type == 'audio' and chunks:
                    speakers_detected = set()
                    total_words = 0
                    
                    for chunk in chunks:
                        if chunk.metadata:
                            if 'speakers' in chunk.metadata:
                                speakers_detected.update(chunk.metadata['speakers'])
                            if 'word_count' in chunk.metadata:
                                total_words += chunk.metadata.get('word_count', 0)
                    
                    if total_words == 0:
                        total_words = len(' '.join(c.content for c in chunks).split())
                    
                    audio_insights = {
                        "transcribed": True,
                        "language": request.language,
                        "estimated_words": total_words
                    }
                    
                    if speakers_detected:
                        audio_insights["speakers_detected"] = sorted(list(speakers_detected))
                        audio_insights["speaker_count"] = len(speakers_detected)
                        audio_insights["note"] = "Speakers were automatically detected"
                    
                    result_data["audio_insights"] = audio_insights
                
                results.append(result_data)

            except Exception as e:
                track_upload_failure('google_drive', type(e).__name__)
                logger.error(f"❌ Unexpected error processing Google Drive file {file_id}: {str(e)}", exc_info=True)
                try:
                    db.rollback()
                except:
                    pass
                results.append({
                    "file_id": file_id,
                    "status": "failed",
                    "error": str(e)
                })

        successful = len([r for r in results if r['status'] == 'success'])
        failed = len([r for r in results if r['status'] == 'failed'])
        logger.info(f"🎉 Google Drive upload complete: {successful} successful, {failed} failed")
        
        return results[0] if len(results) == 1 else {"results": results}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error in Google Drive upload: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/google-drive/check-auth")
async def check_google_drive_auth(current_user=Depends(get_current_user)):
    """
    🔐 Check Google Drive authentication status
    
    Returns whether the user is authenticated with Google Drive
    """
    try:
        drive_service = GoogleDriveService()
        
        # Try to list a few files to verify authentication
        try:
            files = drive_service.list_files(page_size=5)
            return {
                "authenticated": True,
                "can_access": True,
                "sample_files": len(files),
                "message": "Successfully authenticated with Google Drive"
            }
        except Exception as e:
            logger.warning(f"Google Drive auth check failed: {e}")
            return {
                "authenticated": False,
                "can_access": False,
                "message": f"Authentication failed: {str(e)}"
            }
            
    except Exception as e:
        logger.error(f"Error checking Google Drive auth: {e}")
        return {
            "authenticated": False,
            "can_access": False,
            "message": f"Error: {str(e)}"
        }