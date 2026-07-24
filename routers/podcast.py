import os
import logging
from uuid import uuid4
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from dotenv import load_dotenv

# Import existing services
from services.script_generator import PodcastScriptGenerator
from services.text_to_speech import PodcastTTSGenerator, PodcastScript as TTSPodcastScript
from services.web_scraper import WebScraper
from services.youtube_transcriber import YouTubeTranscriber
# ADD THIS after line 5 (after existing imports)
from services.metrics import track_podcast_request, track_podcast_duration, track_podcast_failure
import time
from routers.dependencies import get_current_user
from db import get_db

load_dotenv()

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Podcast"])


# -------------------------------------------------
# Request Models
# -------------------------------------------------
class ScriptRequest(BaseModel):
    input_type: str = Field(..., pattern="^(text|youtube|web|file|collection)$")
    content: Optional[str] = None
    collection_name: Optional[str] = None

    podcast_style: str = "conversational"
    target_duration: str = "5 minutes"
    target_language: str = "English"

    @model_validator(mode="after")
    def validate_fields(self):
        # COLLECTION MODE
        if self.input_type == "collection":
            if not self.collection_name:
                raise ValueError("collection_name is required when input_type='collection'.")
            self.content = None  # ignore content
        else:
            # NON-COLLECTION MODES REQUIRE CONTENT
            if not self.content:
                raise ValueError("content is required when using input_type='text|youtube|web|file'.")
        return self


class ScriptResponse(BaseModel):
    script: list[dict]
    source_document: str
    total_lines: int
    estimated_duration: str
    
class PodcastChunkRequest(BaseModel):
    collection_name: str
    selected_document_ids: Optional[List[str]] = None
    podcast_style: str = "conversational"
    target_duration: str = "5 minutes"
    target_language: str = "English"

class AudioRequest(BaseModel):
    script_data: ScriptResponse
    combine_audio: bool = True
    pause_duration: float = 0.25

class CollectionPodcastRequest(BaseModel):
    collection_name: str
    selected_document_ids: Optional[List[str]] = None
    podcast_style: str = "conversational"
    target_duration: str = "10 minutes"
    target_language: str = "English"


# -------------------------------------------------
# Extractor Function
# -------------------------------------------------
def extract_content_for_podcast(req: ScriptRequest, script_gen: PodcastScriptGenerator, db, current_user):
    """
    Handles extraction based on input_type.
    For collection: combine ALL chunks into a single text.
    """

    # ---------------- TEXT ----------------
    if req.input_type == "text":
        return script_gen.generate_script_from_text(
            text_content=req.content,
            source_name="Text Input",
            podcast_style=req.podcast_style,
            target_duration=req.target_duration,
            target_language=req.target_language
        )

    # ---------------- WEB ----------------
    if req.input_type == "web":
        # firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
        # if not firecrawl_key:
        #     raise HTTPException(500, "FIRECRAWL_API_KEY not set.")

        scraper = WebScraper(use_undetected=True)
        chunks = scraper.scrape_url(req.content, 1000, 100)

        if not chunks:
            raise HTTPException(400, "Failed to scrape website content.")

        return script_gen.generate_script_from_website(
            website_chunks=chunks,
            source_url=req.content,
            podcast_style=req.podcast_style,
            target_duration=req.target_duration,
            target_language=req.target_language
        )

    # ---------------- YOUTUBE ----------------
    if req.input_type == "youtube":
        sarvam_key = os.getenv("SARVAM_API_KEY")
        if not sarvam_key:
            raise HTTPException(500, "SARVAM_API_KEY not set for transcription.")

        yt = YouTubeTranscriber(sarvam_key)
        chunks = yt.transcribe_youtube_video(req.content)

        if not chunks:
            raise HTTPException(400, "Failed to transcribe YouTube video.")

        try:
            full_text = "\n".join([c.page_content for c in chunks])
        except:
            full_text = "\n".join([str(c) for c in chunks])

        return script_gen.generate_script_from_text(
            text_content=full_text,
            source_name=f"YouTube: {req.content}",
            podcast_style=req.podcast_style,
            target_duration=req.target_duration,
            target_language=req.target_language
        )

    # ---------------- FILE ----------------
    if req.input_type == "file":
        if not os.path.exists(req.content):
            raise HTTPException(400, f"File not found: {req.content}")

        return script_gen.generate_script_from_document(
            document_path=req.content,
            podcast_style=req.podcast_style,
            target_duration=req.target_duration
        )

    # ---------------- COLLECTION (NEW CLEAN VERSION) ----------------
    if req.input_type == "collection":
        collection_row = db.execute(
            text("""
                SELECT id FROM collections 
                WHERE collection_name = :name AND user_id = :uid
            """),
            {"name": req.collection_name, "uid": str(current_user.id)}
        ).fetchone()

        if not collection_row:
            raise HTTPException(404, f"Collection '{req.collection_name}' not found.")

        collection_id = collection_row[0]

        rows = db.execute(
            text("""
                SELECT content FROM chunks
                WHERE collection_id = :cid AND user_id = :uid 
                ORDER BY document_id, chunk_index
            """),
            {"cid": collection_id, "uid": str(current_user.id)}
        ).fetchall()

        if not rows:
            raise HTTPException(404, "No documents/chunks found in this collection.")

        # OPTION A — FULL TEXT MERGE
        full_text = "\n\n".join([row[0] for row in rows])

        return script_gen.generate_script_from_text(
            text_content=full_text,
            source_name=req.collection_name,
            podcast_style=req.podcast_style,
            target_duration=req.target_duration,
            target_language=req.target_language
        )

    raise HTTPException(400, "Invalid input_type")

def get_merged_chunks(document_ids, db, current_user):
    rows = db.execute(text("""
        SELECT content
        FROM chunks
        WHERE document_id = ANY(ARRAY(SELECT UNNEST(:doc_ids))::uuid[])

        AND user_id = :uid
        ORDER BY document_id, chunk_index
    """), {
        "doc_ids": document_ids,
        "uid": str(current_user.id)
    }).fetchall()

    if not rows:
        raise HTTPException(404, "No chunks found for the provided document_ids.")

    combined_text = "\n\n".join([row[0] for row in rows])
    return combined_text

def get_collection_id_from_documents(document_ids, db, current_user):
    row = db.execute(text("""
        SELECT DISTINCT collection_id
        FROM documents
        WHERE id = ANY(ARRAY(SELECT UNNEST(:doc_ids))::uuid[])
          AND user_id = :uid
    """), {
        "doc_ids": document_ids,
        "uid": str(current_user.id)
    }).fetchone()

    if not row:
        raise HTTPException(400, "Unable to resolve source collection.")

    return row[0]


@router.post("/podcast/generate")
async def generate_podcast(
    req: PodcastChunkRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    start_time = time.time()
    track_podcast_request()
    
    openai_key = os.getenv("OPENAI_API_KEY")
    sarvam_key = os.getenv("SARVAM_API_KEY")

    if not openai_key or not sarvam_key:
        raise HTTPException(500, "Missing API Keys.")

    try:  # ✅ ADD THIS LINE HERE
        script_gen = PodcastScriptGenerator(openai_api_key=openai_key)

        # ---------------------------------------------------------
        # 1️⃣ Merge selected document chunks
        # ---------------------------------------------------------
        combined_text = get_merged_chunks(
            req.selected_document_ids, db, current_user
        )

        if not combined_text.strip():
            raise HTTPException(400, "No text found in selected chunks.")

        # ---------------------------------------------------------
        # 2️⃣ Generate script
        # ---------------------------------------------------------
        podcast_script = script_gen.generate_script_from_text(
            text_content=combined_text,
            source_name="Merged Sources",
            podcast_style=req.podcast_style,
            target_duration=req.target_duration,
            target_language=req.target_language
        )

        # ---------------------------------------------------------
        # 3️⃣ Generate Audio (TTS)
        # ---------------------------------------------------------
        safe_name = "merged_sources"
        output_dir = f"temp_outputs/{safe_name}"
        os.makedirs(output_dir, exist_ok=True)

        tts_gen = PodcastTTSGenerator(lang_code="en-IN")

        tts_script = TTSPodcastScript(
            script=podcast_script.script,
            source_document=podcast_script.source_document,
            total_lines=podcast_script.total_lines,
            estimated_duration=podcast_script.estimated_duration
        )

        audio_files = tts_gen.generate_podcast_audio(
            podcast_script=tts_script,
            output_dir=output_dir,
            combine_audio=True
        )

        final_audio = audio_files[-1]   # complete_podcast.wav

        # ---------------------------------------------------------
        # 4️⃣ Save script + audio to DB
        # ---------------------------------------------------------
        new_collection_id = uuid4()
        document_id = uuid4()
        audio_id = uuid4()

        # Create a new "podcast output" collection
        db.execute(text("""
            INSERT INTO collections (id, user_id, collection_name, source_type)
            VALUES (:cid, :uid, :name, 'podcast_single')
        """), {
            "cid": new_collection_id,
            "uid": str(current_user.id),
            "name": f"Podcast-From-Chunks-{safe_name}"
        })

        # Save script as a document entry
        db.execute(text("""
            INSERT INTO documents (id, collection_id, user_id, file_name, file_type, chunk_count)
            VALUES (:id, :cid, :uid, :name, 'podcast_script', 1)
        """), {
            "id": document_id,
            "cid": new_collection_id,
            "uid": str(current_user.id),
            "name": podcast_script.source_document
        })

        # Save final audio file path
        db.execute(text("""
            INSERT INTO audio_files (id, user_id, document_id, audio_url)
            VALUES (:id, :uid, :doc, :url)
        """), {
            "id": audio_id,
            "uid": str(current_user.id),
            "doc": document_id,
            "url": final_audio
        })

        db.commit()

        # ---------------------------------------------------------
        # 5️⃣ Return final audio file
        # ---------------------------------------------------------
        track_podcast_duration(time.time() - start_time)
        return FileResponse(
            final_audio,
            media_type="audio/wav",
            filename=f"{safe_name}_podcast.wav"
        )
    
    except HTTPException:  # ✅ ADD THIS BLOCK HERE
        # Re-raise HTTPExceptions without tracking (they're handled errors)
        raise
    except Exception as e:  # ✅ ADD THIS BLOCK HERE
        track_podcast_failure()
        logger.error(f"❌ Podcast generation failed: {str(e)}")
        raise HTTPException(500, f"Podcast generation failed: {str(e)}")

# -------------------------------------------------
# Generate Script Endpoint
# -------------------------------------------------
# @router.post("/podcast/generate-script", response_model=ScriptResponse)
# async def generate_script(req: ScriptRequest, current_user=Depends(get_current_user), db=Depends(get_db)):
#     openai_key = os.getenv("OPENAI_API_KEY")
#     if not openai_key:
#         raise HTTPException(500, "OPENAI_API_KEY not set.")

#     try:
#         script_gen = PodcastScriptGenerator(openai_api_key=openai_key)

#         podcast_script = extract_content_for_podcast(req, script_gen, db, current_user)

#         # Create new collection for storing generated script
#         new_collection_id = uuid4()
#         new_document_id = uuid4()

#         db.execute(text("""
#             INSERT INTO collections (id, user_id, collection_name, source_type)
#             VALUES (:cid, :uid, :name, 'podcast')
#         """), {
#             "cid": new_collection_id,
#             "uid": str(current_user.id),
#             "name": f"Podcast Script - {req.collection_name or uuid4()}"
#         })

#         db.execute(text("""
#             INSERT INTO documents (id, collection_id, user_id, file_name, file_type, chunk_count)
#             VALUES (:did, :cid, :uid, :fname, 'podcast_script', 1)
#         """), {
#             "did": new_document_id,
#             "cid": new_collection_id,
#             "uid": str(current_user.id),
#             "fname": podcast_script.source_document
#         })

#         full_script_text = "\n".join(
#             f"{speaker}: {text}"
#             for line in podcast_script.script
#             for speaker, text in line.items()
#         )

#         db.execute(text("""
#             INSERT INTO chunks (id, document_id, collection_id, user_id,
#                                 chunk_index, start_char, end_char, content, vector, source_type)
#             VALUES (:id, :doc, :cid, :uid, 0, 0, :end, :content, NULL, 'podcast')
#         """), {
#             "id": uuid4(),
#             "doc": new_document_id,
#             "cid": new_collection_id,
#             "uid": str(current_user.id),
#             "end": len(full_script_text),
#             "content": full_script_text
#         })

#         db.commit()

#         return ScriptResponse(
#             script=podcast_script.script,
#             source_document=podcast_script.source_document,
#             total_lines=podcast_script.total_lines,
#             estimated_duration=podcast_script.estimated_duration
#         )

#     except Exception as e:
#         db.rollback()
#         logger.error(f"Error generating podcast: {e}")
#         raise HTTPException(500, str(e))


# # -------------------------------------------------
# # FULL WORKFLOW: Script + TTS
# # -------------------------------------------------
# @router.post("/podcast/process-full")
# async def process_full(req: ScriptRequest, current_user=Depends(get_current_user), db=Depends(get_db)):
#     openai_key = os.getenv("OPENAI_API_KEY")
#     sarvam_key = os.getenv("SARVAM_API_KEY")

#     if not openai_key or not sarvam_key:
#         raise HTTPException(500, "Missing API Keys.")

#     try:
#         # STEP 1 — Generate script
#         script_gen = PodcastScriptGenerator(openai_api_key=openai_key)
#         podcast_script = extract_content_for_podcast(req, script_gen, db, current_user)

#         #safe_name = req.collection_name.replace(" ", "_")[:50]
#         safe_name = (
#             req.collection_name.replace(" ", "_")[:40]
#             + "_"
#             + str(uuid4())[:8]
#         )


#         output_dir = f"temp_outputs/{safe_name}"
#         os.makedirs(output_dir, exist_ok=True)

#         # STEP 2 — TTS
#         tts_gen = PodcastTTSGenerator(lang_code="en-IN")
#         tts_script = TTSPodcastScript(
#             script=podcast_script.script,
#             source_document=podcast_script.source_document,
#             total_lines=podcast_script.total_lines,
#             estimated_duration=podcast_script.estimated_duration
#         )

#         files = tts_gen.generate_podcast_audio(tts_script, output_dir, combine_audio=True)
#         final_audio = files[-1]

#         # STEP 3 — Save audio in DB
#         collection_id = uuid4()
#         document_id = uuid4()
#         audio_id = uuid4()

#         db.execute(text("""
#             INSERT INTO collections (id, user_id, collection_name, source_type)
#             VALUES (:cid, :uid, :name, 'podcast')
#         """), {
#             "cid": collection_id,
#             "uid": str(current_user.id),
#             "name": f"Podcast Audio - {safe_name}"
#         })

#         db.execute(text("""
#             INSERT INTO documents (id, collection_id, user_id, file_name, file_type, chunk_count)
#             VALUES (:id, :cid, :uid, :name, 'podcast_audio', 0)
#         """), {
#             "id": document_id,
#             "cid": collection_id,
#             "uid": str(current_user.id),
#             "name": safe_name
#         })

#         db.execute(text("""
#             INSERT INTO audio_files (id, user_id, document_id, audio_url)
#             VALUES (:id, :uid, :doc, :url)
#         """), {
#             "id": audio_id,
#             "uid": str(current_user.id),
#             "doc": document_id,
#             "url": final_audio
#         })

#         db.commit()

#         return FileResponse(final_audio, media_type="audio/wav")

#     except Exception as e:
#         db.rollback()
#         logger.error(f"Error in full workflow: {e}")
#         raise HTTPException(500, str(e))

# @router.post("/podcast/generate-from-collection1", response_model=ScriptResponse)
# async def generate_from_collection(
#     req: CollectionPodcastRequest,
#     current_user=Depends(get_current_user),
#     db=Depends(get_db)
# ):
#     openai_key = os.getenv("OPENAI_API_KEY")
#     if not openai_key:
#         raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set.")

#     script_gen = PodcastScriptGenerator(openai_api_key=openai_key)

#     # 1️⃣ FIRST: Get collection_id FROM collection_name
#     collection_row = db.execute(text("""
#         SELECT id
#         FROM collections
#         WHERE collection_name = :cname AND user_id = :uid
#         LIMIT 1
#     """), {
#         "cname": req.collection_name,
#         "uid": str(current_user.id)
#     }).fetchone()

#     if not collection_row:
#         raise HTTPException(404, f"Collection '{req.collection_name}' not found.")

#     collection_id = str(collection_row[0])

#     # 2️⃣ Fetch documents under this collection_id
#     documents = db.execute(text("""
#         SELECT id, file_name
#         FROM documents
#         WHERE collection_id = :cid AND user_id = :uid
#     """), {
#         "cid": collection_id,
#         "uid": str(current_user.id)
#     }).fetchall()

#     if not documents:
#         raise HTTPException(404, "No documents found in this collection.")

#     # 3️⃣ Determine selected documents
#     if not req.selected_document_ids:
#         selected_docs = [str(d[0]) for d in documents]  # Use all documents
#     else:
#         selected_docs = req.selected_document_ids

#     # 4️⃣ Fetch chunks for selected documents
#     chunk_rows = db.execute(text("""
#         SELECT content
#         FROM chunks
#         WHERE document_id = ANY(ARRAY[:doc_ids]::uuid[]) 
#         AND user_id = :uid
#         ORDER BY document_id, chunk_index
#     """), {
#         "doc_ids": selected_docs,
#         "uid": str(current_user.id)
#     }).fetchall()


#     if not chunk_rows:
#         raise HTTPException(400, "No chunks found for selected documents.")

#     # 5️⃣ Merge all chunks into a single combined text
#     combined_text = "\n\n".join([row[0] for row in chunk_rows])

#     # 6️⃣ Generate the podcast script using combined text
#     podcast_script = script_gen.generate_script_from_text(
#         text_content=combined_text,
#         source_name=f"Collection: {req.collection_name}",
#         podcast_style=req.podcast_style,
#         target_duration=req.target_duration,
#         target_language=req.target_language
#     )

#     # 7️⃣ Return response
#     return ScriptResponse(
#         script=podcast_script.script,
#         source_document=podcast_script.source_document,
#         total_lines=podcast_script.total_lines,
#         estimated_duration=podcast_script.estimated_duration
#     )

# @router.post("/podcast/generate-from-collection")
# async def generate_from_collection_full(
#     req: CollectionPodcastRequest,
#     current_user=Depends(get_current_user),
#     db=Depends(get_db)
# ):
#     openai_key = os.getenv("OPENAI_API_KEY")
#     sarvam_key = os.getenv("SARVAM_API_KEY")

#     if not openai_key or not sarvam_key:
#         raise HTTPException(500, "Missing API Keys.")

#     script_gen = PodcastScriptGenerator(openai_api_key=openai_key)

#     # 1️⃣ Get collection_id from collection_name
#     collection_row = db.execute(text("""
#         SELECT id FROM collections
#         WHERE collection_name = :cname AND user_id = :uid
#         LIMIT 1
#     """), {
#         "cname": req.collection_name,
#         "uid": str(current_user.id)
#     }).fetchone()

#     if not collection_row:
#         raise HTTPException(404, f"Collection '{req.collection_name}' not found.")

#     collection_id = str(collection_row[0])

#     # 2️⃣ Fetch documents in collection
#     documents = db.execute(text("""
#         SELECT id, file_name
#         FROM documents
#         WHERE collection_id = :cid AND user_id = :uid
#     """), {
#         "cid": collection_id,
#         "uid": str(current_user.id)
#     }).fetchall()

#     if not documents:
#         raise HTTPException(404, "No documents found in this collection.")

#     # 3️⃣ Determine selected docs
#     if not req.selected_document_ids:
#         selected_docs = [str(d[0]) for d in documents]
#     else:
#         selected_docs = req.selected_document_ids

#     # 4️⃣ Fetch chunks for selected docs
#     chunk_rows = db.execute(text("""
#         SELECT content
#         FROM chunks
#         WHERE document_id = ANY(ARRAY(SELECT UNNEST(:doc_ids))::uuid[]) 
#         AND user_id = :uid
#         ORDER BY document_id, chunk_index
#     """), {
#         "doc_ids": selected_docs,
#         "uid": str(current_user.id)
#     }).fetchall()

#     if not chunk_rows:
#         raise HTTPException(400, "No chunks found for selected documents.")

#     combined_text = "\n\n".join([row[0] for row in chunk_rows])

#     # 5️⃣ Generate script
#     podcast_script = script_gen.generate_script_from_text(
#         text_content=combined_text,
#         source_name=f"Collection: {req.collection_name}",
#         podcast_style=req.podcast_style,
#         target_duration=req.target_duration,
#         target_language=req.target_language
#     )

#     # ---------------------------------------------------------
#     # 6️⃣ Generate Audio (Bulbul)
#     # ---------------------------------------------------------
#     safe_name = req.collection_name.replace(" ", "_")[:50]
#     output_dir = f"temp_outputs/{safe_name}"
#     os.makedirs(output_dir, exist_ok=True)

#     tts_gen = PodcastTTSGenerator(lang_code="en-IN")

#     tts_script = TTSPodcastScript(
#         script=podcast_script.script,
#         source_document=podcast_script.source_document,
#         total_lines=podcast_script.total_lines,
#         estimated_duration=podcast_script.estimated_duration
#     )

#     audio_files = tts_gen.generate_podcast_audio(
#         podcast_script=tts_script,
#         output_dir=output_dir,
#         combine_audio=True
#     )

#     final_audio = audio_files[-1]  # complete_podcast.wav

#     # ---------------------------------------------------------
#     # 7️⃣ Save script + audio to DB
#     # ---------------------------------------------------------
#     new_collection_id = uuid4()
#     document_id = uuid4()
#     audio_id = uuid4()

#     db.execute(text("""
#         INSERT INTO collections (id, user_id, collection_name, source_type)
#         VALUES (:cid, :uid, :name, 'podcast_full')
#     """), {
#         "cid": new_collection_id,
#         "uid": str(current_user.id),
#         "name": f"Podcast-Full-{safe_name}"
#     })

#     # Insert document entry for script
#     db.execute(text("""
#         INSERT INTO documents (id, collection_id, user_id, file_name, file_type, chunk_count)
#         VALUES (:id, :cid, :uid, :name, 'podcast_script', 1)
#     """), {
#         "id": document_id,
#         "cid": new_collection_id,
#         "uid": str(current_user.id),
#         "name": podcast_script.source_document
#     })

#     # Insert audio entry
#     db.execute(text("""
#         INSERT INTO audio_files (id, user_id, document_id, audio_url)
#         VALUES (:id, :uid, :doc, :url)
#     """), {
#         "id": audio_id,
#         "uid": str(current_user.id),
#         "doc": document_id,
#         "url": final_audio
#     })

#     db.commit()

#     # ---------------------------------------------------------
#     # 8️⃣ Return file
#     # ---------------------------------------------------------
#     return FileResponse(
#         final_audio,
#         media_type="audio/wav",
#         filename=f"{safe_name}_podcast.wav"
#     )


# @router.post("/podcast/generate(final)")
# async def generate_podcast(req: PodcastChunkRequest,
#                            current_user=Depends(get_current_user),
#                            db=Depends(get_db)):

#     openai_key = os.getenv("OPENAI_API_KEY")
#     sarvam_key = os.getenv("SARVAM_API_KEY")

#     if not openai_key or not sarvam_key:
#         raise HTTPException(500, "Missing API Keys.")

#     script_gen = PodcastScriptGenerator(openai_api_key=openai_key)

#     # ---------------------------------------------------------
#     # 1️⃣ RESOLVE DOCUMENT IDS
#     # ---------------------------------------------------------
#     if req.collection_name:
#         # Get collection_id
#         collection_row = db.execute(text("""
#             SELECT id FROM collections
#             WHERE collection_name = :cname AND user_id = :uid
#             LIMIT 1
#         """), {
#             "cname": req.collection_name,
#             "uid": str(current_user.id)
#         }).fetchone()

#         if not collection_row:
#             raise HTTPException(404, f"Collection '{req.collection_name}' not found.")

#         collection_id = str(collection_row[0])

#         # Get documents inside collection
#         docs = db.execute(text("""
#             SELECT id FROM documents
#             WHERE collection_id = :cid AND user_id = :uid
#         """), {
#             "cid": collection_id,
#             "uid": str(current_user.id)
#         }).fetchall()

#         if not docs:
#             raise HTTPException(404, "No documents found in this collection.")

#         document_ids = [str(d[0]) for d in docs]

#     else:
#         if not req.document_ids:
#             raise HTTPException(400, "Either document_ids or collection_name must be provided.")
#         document_ids = req.document_ids

#     # ---------------------------------------------------------
#     # 2️⃣ FETCH CHUNKS
#     # ---------------------------------------------------------
#     chunk_rows = db.execute(text("""
#         SELECT content
#         FROM chunks
#         WHERE document_id = ANY(:doc_ids)
#         AND user_id = :uid
#         ORDER BY document_id, chunk_index
#     """), {
#         "doc_ids": document_ids,
#         "uid": str(current_user.id)
#     }).fetchall()

#     if not chunk_rows:
#         raise HTTPException(400, "No chunks found for selected documents.")

#     combined_text = "\n\n".join([c[0] for c in chunk_rows])

#     # ---------------------------------------------------------
#     # 3️⃣ GENERATE PODCAST SCRIPT
#     # ---------------------------------------------------------
#     podcast_script = script_gen.generate_script_from_text(
#         text_content=combined_text,
#         source_name=req.collection_name or "Merged Sources",
#         podcast_style=req.podcast_style,
#         target_duration=req.target_duration,
#         target_language=req.target_language
#     )

#     # ---------------------------------------------------------
#     # 4️⃣ GENERATE AUDIO USING BULBUL
#     # ---------------------------------------------------------
#     safe_name = (req.collection_name or "Merged-Sources").replace(" ", "_")[:50]
#     output_dir = f"temp_outputs/{safe_name}"
#     os.makedirs(output_dir, exist_ok=True)

#     tts_gen = PodcastTTSGenerator(lang_code="en-IN")

#     tts_script = TTSPodcastScript(
#         script=podcast_script.script,
#         source_document=podcast_script.source_document,
#         total_lines=podcast_script.total_lines,
#         estimated_duration=podcast_script.estimated_duration
#     )

#     audio_files = tts_gen.generate_podcast_audio(
#         podcast_script=tts_script,
#         output_dir=output_dir,
#         combine_audio=True
#     )

#     final_audio = audio_files[-1]  # complete_podcast.wav

#     # ---------------------------------------------------------
#     # 5️⃣ SAVE SCRIPT + AUDIO TO DB
#     # ---------------------------------------------------------
#     new_collection_id = uuid4()
#     script_doc_id = uuid4()
#     audio_id = uuid4()

#     db.execute(text("""
#         INSERT INTO collections (id, user_id, collection_name, source_type)
#         VALUES (:cid, :uid, :name, 'podcast_full')
#     """), {
#         "cid": new_collection_id,
#         "uid": str(current_user.id),
#         "name": f"Podcast-Full-{safe_name}"
#     })

    # # Insert script as document
    # db.execute(text("""
    #     INSERT INTO documents (id, collection_id, user_id, file_name, file_type, chunk_count)
    #     VALUES (:id, :cid, :uid, :name, 'podcast_script', 1)
    # """), {
    #     "id": script_doc_id,
    #     "cid": new_collection_id,
    #     "uid": str(current_user.id),
    #     "name": podcast_script.source_document
    # })

    # db.execute(text("""
    #     INSERT INTO audio_files (id, user_id, document_id, audio_url)
    #     VALUES (:id, :uid, :doc, :url)
    # """), {
    #     "id": audio_id,
    #     "uid": str(current_user.id),
    #     "doc": script_doc_id,
    #     "url": final_audio
    # })

    # db.commit()

    # # ---------------------------------------------------------
    # # 6️⃣ RETURN THE AUDIO FILE
    # # ---------------------------------------------------------
    # return FileResponse(
    #     final_audio,
    #     media_type="audio/wav",
    #     filename=f"{safe_name}_podcast.wav"
    # )