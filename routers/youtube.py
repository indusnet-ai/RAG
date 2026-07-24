from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Union, List
import logging
import os
from uuid import uuid4
from sqlalchemy import text
from dotenv import load_dotenv
import json
from services.metrics import track_document_upload, track_upload_duration
import time

load_dotenv()

from services.youtube_transcriber import YouTubeTranscriber
from services.embedding_generator import EmbeddingGenerator
from services.vector_db import VectorDB
from routers.dependencies import get_current_user
from db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Source Upload"])

class YouTubeRequest(BaseModel):
    urls: Union[str, List[str]]
    collection_name: str

@router.post("/youtube")
async def transcribe_youtube(
    req: YouTubeRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Transcribe YouTube videos and add them to an existing collection.
    """
    try:
        sarvam_api_key = os.getenv("SARVAM_API_KEY")
        if not sarvam_api_key:
            raise HTTPException(
                status_code=500,
                detail="SARVAM_API_KEY not found in environment variables."
            )

        user_uuid = str(current_user.id)

        # Verify collection exists
        collection_result = db.execute(text("""
            SELECT id FROM collections 
            WHERE collection_name = :name AND user_id = :uid
        """), {"name": req.collection_name, "uid": user_uuid})

        collection_row = collection_result.fetchone()
        if not collection_row:
            raise HTTPException(
                status_code=404, 
                detail=f"Collection '{req.collection_name}' not found."
            )

        collection_id = collection_row.id

        yt = YouTubeTranscriber(sarvam_api_key,youtube_api_key=os.getenv("YOUTUBE_API_KEY"))
        embedder = EmbeddingGenerator()

        urls = req.urls if isinstance(req.urls, list) else [req.urls]
        urls = list(dict.fromkeys(urls))

        if not urls:
            raise HTTPException(status_code=400, detail="No URLs provided")

        results = []

        for url in urls:
            upload_start_time = time.time()
            try:
                logger.info(f"🎬 Processing YouTube URL: {url}")

                # Get chunks and video title
                chunks, video_title = yt.transcribe_youtube_video(
                    url=url,
                    enable_diarization=False,
                    num_speakers=1
                )
                
                embedded_chunks = embedder.generate_embeddings(chunks)

                document_id = uuid4()

                # Save document with video title
                db.execute(text("""
                    INSERT INTO documents (id, collection_id, user_id, file_name, source_url, file_type, chunk_count)
                    VALUES (:id, :cid, :uid, :name, :url, 'youtube', :count)
                """), {
                    "id": document_id,
                    "cid": collection_id,
                    "uid": user_uuid,
                    "name": video_title,
                    "url": url,
                    "count": len(embedded_chunks)
                })

                # Insert chunks with video title as source_file
                for emb in embedded_chunks:
                    c = emb.chunk
                    vector_data = emb.embedding.tolist()
                    vector_str = f"[{','.join(map(str, vector_data))}]"
                    
                    metadata_json = json.dumps(c.metadata) if c.metadata else '{}'

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
                        "source_file": video_title,  # ✅ FIXED: Use video title instead of URL
                        "page_num": None,
                        "emb_model": "text-embedding-3-large",
                        "metadata": metadata_json
                    })

                db.commit()
                track_document_upload("youtube")
                # ✅ ADD THIS
                upload_duration = time.time() - upload_start_time
                track_upload_duration("youtube", upload_duration)
                results.append({
                    "url": url,
                    "video_title": video_title,
                    "collection_id": str(collection_id),
                    "collection_name": req.collection_name,
                    "document_id": str(document_id),
                    "chunks_inserted": len(embedded_chunks),
                    "status": "success"
                })

            except Exception as e:
                db.rollback()
                logger.error(f"❌ Error processing {url}: {str(e)}")
                results.append({
                    "url": url,
                    "status": "failed",
                    "error": str(e)
                })

        return results[0] if len(results) == 1 else {"results": results}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))