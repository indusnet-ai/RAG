from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Body, Query, BackgroundTasks
from uuid import uuid4
import os
import shutil
from typing import List
from sqlalchemy import text
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from services.collection_summary_service import CollectionSummaryService
import json
from db import get_db
from services.document_service import DocumentService
from services.audio_service import AudioService
from services.embedding_generator import EmbeddingGenerator
from services.vector_db import VectorDB
from routers.dependencies import get_current_user
# ADD THIS after line 14 (after existing imports)
from services.metrics import (
    track_document_upload, track_upload_failure, track_embeddings_generated,
    track_text_paste, track_upload_duration, track_embedding_duration  # ✅ ADD THESE
)
import time
router = APIRouter(tags=["Source Upload"])
UPLOAD_STORAGE_DIR = Path("uploaded_files")

@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    ⚡ Check Async Upload Job Status & Progress
    """
    try:
        user_uuid = str(current_user.id)
        row = db.execute(text("""
            SELECT id, collection_id, file_name, status, progress_pct, total_chunks, error_message, created_at, updated_at
            FROM jobs WHERE id = :jid AND user_id = :uid
        """), {"jid": job_id, "uid": user_uuid}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Job not found")

        return {
            "job_id": str(row.id),
            "collection_id": str(row.collection_id),
            "file_name": row.file_name,
            "status": row.status,
            "progress_pct": row.progress_pct,
            "total_chunks": row.total_chunks,
            "error_message": row.error_message,
            "created_at": str(row.created_at),
            "updated_at": str(row.updated_at)
        }
    except Exception as e:
        logger.error(f"Error fetching job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S,%f'[:-3]
)
logger = logging.getLogger(__name__)

doc_service = DocumentService()
embedder = EmbeddingGenerator()


class TextPasteRequest(BaseModel):
    collection_name: str = Field(..., description="Collection to add text to")
    text_content: str = Body(..., media_type="text/plain")
    text_title: str = Body("Pasted Text")


def save_uploaded_file_permanently(
    temp_path: str,
    collection_name: str,
    document_id: str,
    filename: str
) -> str:
    """
    Save uploaded file to permanent storage with SIMPLE structure.
    
    Directory structure: uploaded_files/{collection_name}/
    Filename format: {document_id}.{extension}
    
    Example: uploaded_files/chat_20260202_121204/abc-123.pdf
    
    Args:
        temp_path: Path to temporary file
        collection_name: Collection name (not ID!)
        document_id: Document UUID
        filename: Original filename (to get extension)
        
    Returns:
        Relative path to stored file (for database storage)
    """
    try:
        # Create directory structure: uploaded_files/{collection_name}/
        storage_path = UPLOAD_STORAGE_DIR / collection_name
        storage_path.mkdir(parents=True, exist_ok=True)
        
        # Get file extension from original filename
        extension = Path(filename).suffix  # e.g., ".pdf"
        
        # Create simple filename: {document_id}.{extension}
        safe_filename = f"{document_id}{extension}"
        file_path = storage_path / safe_filename
        
        # Copy file from temp to permanent location
        shutil.copy2(temp_path, file_path)
        
        # Return relative path for database storage
        relative_path = str(file_path)
        logger.info(f"💾 File saved: {relative_path}")
        
        return relative_path
        
    except Exception as e:
        logger.error(f"❌ Error saving file: {e}")
        return None


def get_file_type(filename: str) -> str:
    """Determine file type from filename extension"""
    suffix = Path(filename).suffix.lower()
    
    file_type_mapping = {
        # Documents
        '.pdf': 'pdf',
        '.docx': 'docx',
        '.txt': 'txt',
        '.md': 'md',
        '.pptx': 'pptx',  # ← ADD THIS
        '.ppt': 'pptx', 
        # Images
        '.png': 'image',
        '.jpg': 'image',
        '.jpeg': 'image',
        '.avif': 'image',
        '.gif': 'image',
        '.bmp': 'image',
        '.ico': 'image',
        '.jp2': 'image',
        '.webp': 'image',
        '.tif': 'image',
        '.tiff': 'image',
        '.heic': 'image',
        '.heif': 'image',
        # Spreadsheets
        '.xlsx': 'excel',
        '.xls': 'excel',
        '.xlsm': 'excel',
        '.csv': 'excel',
        # Audio files
        '.mp3': 'audio',
        '.wav': 'audio',
        '.m4a': 'audio',
        '.aac': 'audio',
        '.ogg': 'audio',
        '.flac': 'audio',
        '.wma': 'audio',
        '.opus': 'audio',
        '.mp4': 'audio',
        '.mov': 'audio',
        '.avi': 'audio',
        '.aiff': 'audio',
        '.amr': 'audio',
        '.webm': 'audio'
    }
    
    return file_type_mapping.get(suffix, 'unknown')


@router.post("/upload")
async def upload_documents(
    background_tasks: BackgroundTasks,
    collection_name: str = Form(..., description="Collection to add files to"),
    files: List[UploadFile] = File(..., description="Files to upload"),
    language: str = Form("en-IN", description="Language for audio transcription (e.g., en-IN, hi-IN)"),
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    📁 Upload Any File - Documents, Images, or Audio
    
    Simply upload your files and the system automatically:
    - Detects what type of file it is
    - Processes it appropriately (OCR for images, transcription for audio, etc.)
    - Detects speakers in audio (if there are multiple people talking)
    - Generates embeddings
    - Makes everything searchable
    
    📄 Supported Formats:
    - Documents: .pdf, .docx, .txt, .md, .xlsx, .xls, .csv
    - Images: .png, .jpg, .jpeg,'.bmp', '.gif', '.webp','.tif', '.tiff', '.heic', '.heif', '.avif', '.ico', '.jp2
    - Audio: .mp3, .wav, .m4a, .aac, .ogg, .flac, .wma, .opus, .mp4, .mov, .avi, .webm
    """
    upload_start_time = time.time()
    try:
        user_uuid = str(current_user.id)
        logger.info(f"📁 Upload request from user {user_uuid} for collection '{collection_name}'")
        
        # Verify collection exists
        try:
            collection_result = db.execute(text("""
                SELECT id FROM collections 
                WHERE collection_name = :name AND user_id = :uid
            """), {"name": collection_name, "uid": user_uuid})

            collection_row = collection_result.fetchone()
        except Exception as db_error:
            logger.error(f"Database error: {str(db_error)}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(db_error)}")

        if not collection_row:
            logger.warning(f"Collection '{collection_name}' not found")
            raise HTTPException(
                status_code=404, 
                detail=f"Collection '{collection_name}' not found. Please create it first."
            )

        collection_id = collection_row.id
        logger.info(f"✓ Collection validated: {collection_id}")

        # Initialize audio service lazily (only when needed)
        audio_service = None

        # Ensure files is a list
        if isinstance(files, UploadFile):
            files = [files]

        if not files:
            raise HTTPException(status_code=400, detail="No files provided")

        logger.info(f"📦 Processing {len(files)} file(s)")
        results = []

        for file in files:
            try:
                document_id = uuid4()
                
                # Detect file type
                file_type = get_file_type(file.filename)
                
                file_emoji = "🎵" if file_type == "audio" else "📄"
                logger.info(f"{file_emoji} Processing: {file.filename} (type: {file_type})")
                
                if file_type == 'unknown':
                    logger.warning(f"Unsupported file type: {file.filename}")
                    results.append({
                        "file_name": file.filename,
                        "status": "failed",
                        "error": (
                            "Unsupported file type. "
                            "Supported: PDF, DOCX, TXT, MD, XLSX, XLS, CSV, PNG, JPG, JPEG, "
                            "MP3, WAV, M4A, AAC, OGG, FLAC, WMA, OPUS, MP4, MOV, AVI, WEBM"
                            "avif, bmp, gif, ico, jp2, webp, tif, heic, heif"
                        )
                    })
                    continue

                # Save temp file
                import tempfile
                temp_path = os.path.join(tempfile.gettempdir(), f"{document_id}_{file.filename}")
                try:
                    with open(temp_path, "wb") as out_file:
                        shutil.copyfileobj(file.file, out_file)
                except Exception as file_error:
                    logger.error(f"File save error: {str(file_error)}")
                    results.append({
                        "file_name": file.filename,
                        "status": "failed",
                        "error": f"Could not save file: {str(file_error)}"
                    })
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
                        
                        # Process audio - system handles everything automatically
                        logger.info(f"🎙️ Transcribing audio...")
                        chunks = audio_service.process_uploaded_audio(
                            temp_path=temp_path,
                            original_name=file.filename,
                            language=language
                            # That's it! No diarization params needed
                            # System automatically:
                            # - Enables speaker detection
                            # - Detects number of speakers
                            # - Chunks optimally
                        )
                        logger.info(f"✓ Audio processed: {len(chunks)} chunks")
                    else:
                        # Process as document
                        chunks = doc_service.process_uploaded_file(temp_path, file.filename)
                        logger.info(f"✓ Document processed: {len(chunks)} chunks")
                        
                except Exception as process_error:
                    error_msg = str(process_error)
                    error_type = "Audio transcription" if file_type == 'audio' else "Document processing"
                    logger.error(f"❌ {error_type} error: {error_msg}")
                    
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                    
                    results.append({
                        "file_name": file.filename,
                        "file_type": file_type,
                        "status": "failed",
                        "error": f"{error_type} failed: {error_msg}"
                    })
                    continue

                # Generate embeddings (same for all file types)
                try:
                    embedding_start = time.time()
                    embedded_chunks = embedder.generate_embeddings(chunks)
                    track_embedding_duration(time.time() - embedding_start)
                    track_embeddings_generated(len(embedded_chunks))
                    logger.info(f"✓ Generated {len(embedded_chunks)} embeddings")
                except Exception as embed_error:
                    logger.error(f"❌ Embedding error: {str(embed_error)}")
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                    results.append({
                        "file_name": file.filename,
                        "file_type": file_type,
                        "status": "failed",
                        "error": f"Embedding generation failed: {str(embed_error)}"
                    })
                    continue

                # Store in database
                try:
                    # Insert document record
                    # Save file permanently BEFORE inserting into DB
                    file_path = save_uploaded_file_permanently(
                        temp_path=temp_path,
                        collection_name=collection_name,  # ← Changed from user_id, collection_id
                        document_id=str(document_id),
                        filename=file.filename
                    )

                    # Insert document record
                    db.execute(text("""
                        INSERT INTO documents (
                            id, collection_id, user_id, file_name, 
                            file_type, chunk_count, file_path
                        )
                        VALUES (:id, :cid, :uid, :fname, :ftype, :count, :fpath)
                    """), {
                        "id": document_id,
                        "cid": collection_id,
                        "uid": user_uuid,
                        "fname": file.filename,
                        "ftype": file_type,
                        "count": len(embedded_chunks),
                        "fpath": file_path  # ← ADD THIS
                    })
                    logger.info(f"Document record inserted: {document_id} (type: {file_type})")
                except Exception as doc_error:
                    logger.error(f"Database error inserting document for {file.filename}: {str(doc_error)}")
                    db.rollback()
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                    results.append({
                        "file_name": file.filename,
                        "status": "failed",
                        "error": f"Database error: {str(doc_error)}"
                    })
                    continue

                # Insert chunks
                try:

                    # Insert chunks
                    for emb in embedded_chunks:
                        c = emb.chunk
                        vector_data = emb.embedding.tolist()
                        vector_str = f"[{','.join(map(str, vector_data))}]"
                        
                        # Serialize metadata (audio chunks have speaker info, timestamps, etc.)
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
                            "source_file": file.filename,
                            "page_num": c.page_number if hasattr(c, 'page_number') else None,
                            "emb_model": "text-embedding-3-large",
                            "metadata": metadata_json
                        })
                    logger.info(f"Inserted {len(embedded_chunks)} chunks for document {document_id}")
                except Exception as chunk_error:
                    logger.error(f"Database error inserting chunks for {file.filename}: {str(chunk_error)}")
                    db.rollback()
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                    results.append({
                        "file_name": file.filename,
                        "status": "failed",
                        "error": f"Chunk insertion error: {str(chunk_error)}"
                    })
                    continue

                # Commit and cleanup
                try:
                    db.commit()
                    track_document_upload(file_type)
                    # ⚡ CLEAR QUERY CACHE FOR COLLECTION (INVALIDATE STALE CACHE)
                    try:
                        db.execute(text("DELETE FROM query_cache WHERE collection_id = :cid"), {"cid": str(collection_id)})
                        db.commit()
                        logger.info(f"⚡ Cleared query cache for collection {collection_id}")
                    except Exception as cache_clear_err:
                        logger.warning(f"⚠️ Cache clear error: {cache_clear_err}")

                    # ✅ ADD UPLOAD DURATION
                    upload_duration = time.time() - upload_start_time
                    track_upload_duration(file_type, upload_duration) 
                    os.remove(temp_path)
                    logger.info(f"✅ Success: {file.filename}")
                    
                except Exception as db_error:
                    logger.error(f"❌ Database error: {str(db_error)}")
                    db.rollback()
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                    results.append({
                        "file_name": file.filename,
                        "file_type": file_type,
                        "status": "failed",
                        "error": f"Database error: {str(db_error)}"
                    })
                    continue

                # Build success response
                result_data = {
                    "file_name": file.filename,
                    "file_type": file_type,
                    "collection_id": str(collection_id),
                    "collection_name": collection_name,
                    "document_id": str(document_id),
                    "chunks_inserted": len(embedded_chunks),
                    "file_path": file_path,  # ✨ ADD THIS LINE
                    "status": "success"
                }
                
                # Add audio insights (what the system discovered automatically)
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
                        "language": language,
                        "estimated_words": total_words
                    }
                    
                    # Include what was auto-detected
                    if speakers_detected:
                        audio_insights["speakers_detected"] = sorted(list(speakers_detected))
                        audio_insights["speaker_count"] = len(speakers_detected)
                        audio_insights["note"] = "Speakers were automatically detected"
                    
                    result_data["audio_insights"] = audio_insights
                
                results.append(result_data)

            except Exception as e:
                track_upload_failure(file_type if 'file_type' in locals() else 'unknown', type(e).__name__)  # ✅ ADD THIS LINE
                logger.error(f"❌ Unexpected error: {str(e)}", exc_info=True)
                try:
                    db.rollback()
                except:
                    pass
                results.append({
                    "file_name": file.filename,
                    "status": "failed",
                    "error": str(e)
                })

        successful = len([r for r in results if r['status'] == 'success'])
        failed = len([r for r in results if r['status'] == 'failed'])
        logger.info(f"🎉 Complete: {successful} successful, {failed} failed")
        # Trigger summary update in BACKGROUND (non-blocking)
        if successful > 0:
            def _bg_summary(cid: str, uid: str):
                try:
                    from db import SessionLocal
                    bg_db = SessionLocal()
                    summary_service = CollectionSummaryService(bg_db)
                    summary_service.trigger_summary_update(collection_id=cid, user_id=uid)
                    bg_db.close()
                    logger.info(f"✅ Background summary updated for collection {cid}")
                except Exception as bg_err:
                    logger.warning(f"⚠️ Background summary update failed: {bg_err}")
            
            background_tasks.add_task(_bg_summary, str(collection_id), user_uuid)
            logger.info(f"⚡ Scheduled background summary update for collection {collection_name}")
        
        return results[0] if len(results) == 1 else {"results": results}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/paste-text")
async def paste_text(
    text_content: str = Body(..., media_type="text/plain"),
    collection_name: str = Query(..., description="Target collection name"),
    text_title: str = Query("Pasted Text", description="Title for pasted text"),
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    """
    📝 Paste text directly without uploading a file.
    
    Creates a .txt file from the pasted text and stores it like other sources,
    so users can click to view it later.
    """
    try:
        user_uuid = str(current_user.id)
        logger.info(f"📝 Text paste: '{text_title}'")

        text_content = text_content.strip()

        if len(text_content) < 10:
            raise HTTPException(400, "Text too short (min 10 chars)")
        if len(text_content) > 1_000_000:
            raise HTTPException(400, "Text too large (max 1MB)")

        collection_row = db.execute(
            text("""
                SELECT id FROM collections
                WHERE collection_name = :name AND user_id = :uid
            """),
            {"name": collection_name, "uid": user_uuid}
        ).fetchone()

        if not collection_row:
            raise HTTPException(404, f"Collection '{collection_name}' not found")

        collection_id = collection_row.id
        document_id = uuid4()

        # ============================================
        # NEW: Create a .txt file from pasted text
        # ============================================
        
        # Create temporary file
        import tempfile
        temp_fd, temp_path = tempfile.mkstemp(suffix='.txt', prefix='pasted_')
        
        try:
            # Write text content to temporary file
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write(text_content)
            
            # Generate safe filename
            safe_title = "".join(
                c for c in text_title 
                if c.isalnum() or c in (' ', '_', '-')
            ).strip() or "Pasted_Text"
            filename = f"{safe_title}.txt"
            
            # Save file permanently using existing function
            file_path = save_uploaded_file_permanently(
                temp_path=temp_path,
                collection_name=collection_name,
                document_id=str(document_id),
                filename=filename
            )
            
            if not file_path:
                raise Exception("Failed to save text file")
            
            logger.info(f"💾 Created text file: {file_path}")
            
            # Process text to create chunks
            chunks = doc_service.process_pasted_text(
                text_content=text_content,
                text_title=text_title
            )

            embedded_chunks = embedder.generate_embeddings(chunks)

            # Insert document record WITH file_path
            db.execute(
                text("""
                    INSERT INTO documents (
                        id, collection_id, user_id,
                        file_name, file_type, file_path, chunk_count
                    )
                    VALUES (:id, :cid, :uid, :fname, 'text', :fpath, :count)
                """),
                {
                    "id": document_id,
                    "cid": collection_id,
                    "uid": user_uuid,
                    "fname": filename,  # Use generated filename
                    "fpath": file_path,  # ← NEW: Store file path
                    "count": len(embedded_chunks),
                }
            )

            # Insert chunks
            for emb in embedded_chunks:
                c = emb.chunk
                vector_str = f"[{','.join(map(str, emb.embedding.tolist()))}]"

                db.execute(
                    text("""
                        INSERT INTO chunks (
                            id, document_id, collection_id, user_id,
                            chunk_index, start_char, end_char,
                            content, vector,
                            source_type, source_file,
                            embedding_model, metadata, created_at
                        )
                        VALUES (
                            :id, :doc, :cid, :uid,
                            :idx, :start, :end,
                            :content, CAST(:vector AS vector),
                            'text', :source_file,
                            'text-embedding-3-large',
                            '{"input_method":"paste"}',
                            CURRENT_TIMESTAMP
                        )
                    """),
                    {
                        "id": uuid4(),
                        "doc": document_id,
                        "cid": collection_id,
                        "uid": user_uuid,
                        "idx": c.chunk_index,
                        "start": c.start_char,
                        "end": c.end_char,
                        "content": c.content,
                        "vector": vector_str,
                        "source_file": filename,
                    }
                )

            db.commit()
            track_text_paste()
            # ============================================
            # 🆕 AUTO-UPDATE COLLECTION SUMMARY
            # ============================================
            try:
                logger.info(f"🔄 Updating summary for collection '{collection_name}'")
                summary_service = CollectionSummaryService(db)
                summary_service.trigger_summary_update(
                    collection_id=str(collection_id),
                    user_id=user_uuid
                )
                logger.info(f"✅ Summary updated after text paste")
            except Exception as summary_error:
                logger.warning(f"⚠️ Summary update failed: {summary_error}")
                
            return {
                "status": "success",
                "document_id": str(document_id),
                "file_name": filename,
                "file_path": file_path,  # ← NEW: Return file path
                "text_title": text_title,
                "chunks_created": len(embedded_chunks),
                "characters_processed": len(text_content),
            }
            
        finally:
            # Clean up temporary file
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except:
                pass

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("❌ Paste text failed")
        db.rollback()
        raise HTTPException(500, "Internal Server Error")