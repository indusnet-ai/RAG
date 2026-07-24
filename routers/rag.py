from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
from uuid import uuid4
import logging
from dotenv import load_dotenv
import re
load_dotenv()
 
from services.rag_generation import RAGGenerator, RAGResult
from services.embedding_generator import EmbeddingGenerator
from services.memory_service import PersistentMemoryLayer
from routers.dependencies import get_current_user
from sqlalchemy import text
from db import get_db
import json
from services.metrics import (
    track_query_executed, track_rag_duration,
    track_sources_count, track_query_duration_by_length  # ✅ ADD THESE
)
import time
from services.ragas_evaluator import RAGAsEvaluator
import asyncio

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S,%f'[:-3]
)
 
logger = logging.getLogger(__name__)
 
router = APIRouter(tags=["Query"])
 
 
def generate_chat_title(query: str, max_length: int = 60) -> str:
    """
    Generate a concise chat title from the first user query.
   
    Args:
        query: The user's first question
        max_length: Maximum length for the title
       
    Returns:
        A short, meaningful title
    """
    # Clean the query
    title = query.strip()
   
    # Remove common question prefixes
    question_prefixes = [
        "what is", "what are", "what's", "how do", "how can", "how to",
        "why is", "why are", "when is", "when was", "where is", "where are",
        "who is", "who are", "can you", "could you", "please", "tell me about",
        "explain", "describe"
    ]
   
    title_lower = title.lower()
    for prefix in question_prefixes:
        if title_lower.startswith(prefix):
            title = title[len(prefix):].strip()
            break
   
    # Capitalize first letter
    if title:
        title = title[0].upper() + title[1:]
   
    # Remove trailing question marks and periods
    title = title.rstrip('?!.')
   
    # Truncate if too long (at word boundary)
    if len(title) > max_length:
        title = title[:max_length].rsplit(' ', 1)[0] + '...'
   
    # Fallback if title is empty or too short
    if len(title) < 3:
        title = query[:max_length]
        if len(title) > max_length:
            title = title[:max_length] + '...'
   
    return title
 
 
def calculate_dynamic_top_k(
    db,
    user_id: str,
    collection_id: str,
    min_top_k: int = 5,
    max_top_k: int = 40
) -> int:
    """
    HYBRID approach: Calculate top_k based on BOTH chunk count AND source diversity.
   
    This is the optimal strategy because:
    - Chunk count = Total content volume
    - Source count = Diversity of sources
   
    Examples:
    - 500 chunks from 1 source → top_k = 20 (concentrated content)
    - 500 chunks from 50 sources → top_k = 30 (need diversity)
    - 50 chunks from 10 sources → top_k = 8 (small but diverse)
   
    Strategy:
    1. Calculate base top_k from chunk count (volume)
    2. Apply diversity multiplier based on source count
    3. Balance between coverage and precision
   
    Args:
        db: Database session
        user_id: User ID
        collection_id: Collection ID
        base_top_k: Base value if user specifies (default: 10)
        min_top_k: Minimum top_k value (default: 5)
        max_top_k: Maximum top_k value (default: 40)
       
    Returns:
        Calculated top_k value
    """
    try:
        # Get both chunk count AND source count in a single query
        result = db.execute(text("""
            SELECT
                COUNT(*) as chunk_count,
                COUNT(DISTINCT source_file) as source_count
            FROM chunks
            WHERE collection_id = :cid
              AND user_id = :uid
              AND (is_deleted = FALSE OR is_deleted IS NULL)
        """), {"cid": collection_id, "uid": user_id})
       
        row = result.fetchone()
        chunk_count = row.chunk_count if row else 0
        source_count = row.source_count if row else 0
       
        # Calculate average chunks per source
        avg_chunks_per_source = chunk_count / source_count if source_count > 0 else 0
       
        logger.info(f"📊 Collection: {chunk_count} chunks from {source_count} sources (avg: {avg_chunks_per_source:.1f} chunks/source)")
       
        # STEP 1: Calculate base top_k from chunk count (volume-based)
        if chunk_count < 50:
            base_from_chunks = 8
        elif chunk_count < 200:
            base_from_chunks = 12
        elif chunk_count < 500:
            base_from_chunks = 18
        elif chunk_count < 1000:
            base_from_chunks = 25
        elif chunk_count < 2000:
            base_from_chunks = 30
        else:
            base_from_chunks = 35
       
        # STEP 2: Calculate diversity multiplier from source count
        # More sources = need more chunks to ensure all sources are represented
        if source_count <= 3:
            # Very few sources: content is concentrated
            diversity_multiplier = 0.85  # Reduce top_k by 30%
        elif source_count <= 10:
            # Small diversity: moderate adjustment
            diversity_multiplier = 1.0
        elif source_count <= 25:
            # Medium diversity: baseline
            diversity_multiplier = 1.2
        elif source_count <= 50:
            # High diversity: need more chunks
            diversity_multiplier = 1.3
        else:
            # Very high diversity: maximize coverage
            diversity_multiplier = 1.4
       
        # STEP 3: Apply diversity multiplier
        calculated_top_k = int(base_from_chunks * diversity_multiplier)
       
        # STEP 4: Additional adjustment for chunks-per-source ratio
        # If sources are very small (few chunks each), reduce top_k
        # If sources are very large (many chunks each), increase top_k
        if avg_chunks_per_source < 5:
            # Many small sources: reduce to avoid over-retrieval
            calculated_top_k = int(calculated_top_k * 0.8)
        elif avg_chunks_per_source > 50:
            # Few large sources: increase for better coverage within each
            calculated_top_k = int(calculated_top_k * 1.1)
       
        # STEP 5: Apply bounds
        calculated_top_k = max(min_top_k, min(calculated_top_k, max_top_k))
       
        # STEP 6: Respect user preference if higher
        # if base_top_k > calculated_top_k:
        #     final_top_k = min(base_top_k, max_top_k)
        #     logger.info(
        #         f"🎯 Using user-specified top_k: {final_top_k} "
        #         f"(calculated: {calculated_top_k}, chunks: {chunk_count}, sources: {source_count})"
        #     )
        # else:
        final_top_k = calculated_top_k
        logger.info(
            f"🎯 Using hybrid top_k: {final_top_k} "
            f"(chunks: {chunk_count}, sources: {source_count}, "
            f"avg: {avg_chunks_per_source:.1f} chunks/source)"
        )
       
        return final_top_k
       
    except Exception as e:
        logger.error(f"❌ Error calculating dynamic top_k: {str(e)}")
        # Fallback to base value
        return min_top_k
 
 
class RAGSummaryRequest(BaseModel):
    collection_name: str = Field(..., description="Collection name to summarize")
    max_chunks: int = Field(15, ge=5, le=30, description="Maximum chunks for summary")
    summary_length: str = Field("medium", pattern="^(short|medium|long)$", description="Summary length")
    include_complete_response: bool = Field(True, description="Include complete response at the end of stream")
class RAGQueryRequest(BaseModel):
    query: str = Field(..., description="The question to answer using RAG")
    selected_document_ids: Optional[List[str]] = None
    collection_name: str = Field(..., description="Collection name to search in")
    response_language: Optional[str] = Field(
        "english",
        description="Response language (english, hindi, tamil, telugu, kannada, malayalam, french, spanish, arabic)"
    )
    Conversational_style: Optional[str] = Field(
        "default",
        description="style/role/goal"
    )
    chat_length: Optional[str] = Field(
        "default",
        description="shorter/longer"
    )
    # top_k: REMOVED!
    include_complete_response: bool = Field(True)
    



@router.post("/rag/query")
async def stream_rag_query(
    req: RAGQueryRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    SUPPORTED_LANGUAGES = {
    "english": "English",
    "hindi": "Hindi",
    "tamil": "Tamil",
    "telugu": "Telugu",
    "kannada": "Kannada",
    "malayalam": "Malayalam",
    "french": "French",
    "spanish": "Spanish",
    "arabic": "Arabic"
    }

    lang_key = (req.response_language or "english").lower()

    if lang_key not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported response_language: {req.response_language}"
        )

    response_language = SUPPORTED_LANGUAGES[lang_key]

    

    """
    Stream RAG response in real-time with memory and automatic chat title generation.
   
    Features:
    - HYBRID dynamic top_k: Considers both chunk count (volume) and source count (diversity)
    - Memory integration for conversation continuity
    - Automatic chat title generation
    - Real-time streaming response
    """
    async def stream_rag_response():
        # Track response data for logging
        start_time = time.time()
        full_response = ""
        sources_used = []
        memory_sources = []
        query_id = uuid4()
        raw_response = ""
        clean_response = ""
        reference_map = {}  # ✅ ADD THIS
        yield f"{json.dumps({'type': 'query_id', 'query_id': str(query_id)})}\n"
        logger.info(f"✅ Sent query_id to frontend: {query_id}")
       
        try:
            user_uuid = str(current_user.id)
            logger.info(f"📝 Streaming RAG query for user {user_uuid}: {req.query[:50]}...")
 
            # Verify collection exists and get chat_title
            try:
                collection_result = db.execute(text("""
                    SELECT id, chat_title FROM collections
                    WHERE collection_name = :name AND user_id = :uid
                """), {"name": req.collection_name, "uid": user_uuid})
 
                collection_row = collection_result.fetchone()
            except Exception as db_error:
                logger.error(f"❌ Database error while fetching collection: {str(db_error)}")
                error_data = {"type": "error", "content": f"Database error: {str(db_error)}"}
                yield f"{json.dumps(error_data)}\n"
                return
 
            if not collection_row:
                logger.warning(f"⚠️ Collection '{req.collection_name}' not found")
                error_data = {"type": "error", "content": f"Collection '{req.collection_name}' not found."}
                yield f"{json.dumps(error_data)}\n"
                return
 
            collection_id = str(collection_row.id)
            current_chat_title = collection_row.chat_title
            logger.info(f"✅ Collection: {collection_id}, chat_title: {current_chat_title}")
 
            # ✅ CALCULATE HYBRID DYNAMIC TOP_K (CHUNKS + SOURCES)
            dynamic_top_k = calculate_dynamic_top_k(
                db=db,
                user_id=user_uuid,
                collection_id=collection_id,
                min_top_k=5,
                max_top_k=40
            )
           
            # Override the request's top_k with the calculated value
            effective_top_k = dynamic_top_k
            logger.info(f"🎯 Effective top_k: {effective_top_k}")
 
            # ✅ GENERATE AND SAVE CHAT TITLE ON FIRST QUERY
            try:
                query_count_result = db.execute(text("""
                    SELECT COUNT(*) as count FROM queries
                    WHERE collection_id = :cid AND user_id = :uid
                    AND (is_deleted = FALSE OR is_deleted IS NULL)
                """), {"cid": collection_id, "uid": user_uuid})
               
                query_count = query_count_result.fetchone().count
               
                if query_count == 0 and not current_chat_title:
                    chat_title = generate_chat_title(req.query)
                    logger.info(f"📝 Generated chat title: '{chat_title}'")
                   
                    # Save to database
                    db.execute(text("""
                        UPDATE collections SET chat_title = :title WHERE id = :cid
                    """), {"title": chat_title, "cid": collection_id})
                   
                    db.commit()
                    logger.info(f"✅ Chat title saved to database")
                   
                    # Send to client
                    yield f"{json.dumps({'type': 'chat_title', 'title': chat_title})}\n"
                   
            except Exception as title_error:
                logger.error(f"❌ Error with chat title: {str(title_error)}")
                try:
                    db.rollback()
                except:
                    pass
 
            # Initialize memory layer
            memory_layer = None
            relevant_memories = []
            memory_context = ""
           
            try:
                memory_layer = PersistentMemoryLayer(
                    user_id=user_uuid,
                    collection_id=collection_id
                )
                logger.info("✅ Memory layer initialized")
            except Exception as mem_error:
                logger.error(f"❌ Memory error: {str(mem_error)}")
                memory_layer = None
 
            # Retrieve memories
            memory_context = ""
 
            # Retrieve memories
            if memory_layer:
                try:
                    relevant_memories = memory_layer.get_relevant_memories(req.query, limit=3)
                    logger.info(f"📊 Found {len(relevant_memories)} memories")
 
                    memory_sources = memory_layer.get_memory_sources(relevant_memories)
                    memory_context = ""
 
                    if relevant_memories:
                        memory_parts = []
 
                        for mem in relevant_memories:
                            mem_content = mem.get("content", "")
 
                            if "SOURCE_METADATA:" in mem_content:
                                mem_content = mem_content[:mem_content.find("SOURCE_METADATA:")].strip()
 
                            memory_parts.append(mem_content)
 
                        memory_context = "\n\n".join(memory_parts)
 
                except Exception as mem_error:
                    logger.error(f"❌ Error retrieving memories: {str(mem_error)}")
                    memory_context = ""
                    memory_sources = []
                    relevant_memories = []
            else:
                memory_context = ""
                memory_sources = []
                relevant_memories = []
 
            # Build memory chunks
            memory_chunks = []
 
            for idx, mem in enumerate(relevant_memories):
                content = mem.get("content", "")
 
                if "SOURCE_METADATA:" in content:
                    content = content[:content.find("SOURCE_METADATA:")].strip()
 
                memory_chunks.append({
                    "id": f"memory-{idx}",
                    "content": content,
                    "score": mem.get("score", 0.0),
                    "citation": {
                        "source_file": "memory",
                        "source_type": "memory",
                        "page_number": None
                    }
                })
 
            # Initialize RAG generator
            try:
                embedder = EmbeddingGenerator()
                rag_generator = RAGGenerator(
                    embedding_generator=embedder,
                    db=db,
                    memory_layer=memory_layer
                )
                logger.info("✅ RAG generator initialized")
            except Exception as gen_error:
                logger.error(f"❌ RAG generator error: {str(gen_error)}")
                error_data = {"type": "error", "content": f"Error: {str(gen_error)}"}
                yield f"{json.dumps(error_data)}\n"
                return
 
            # Stream response with hybrid dynamic top_k
            try:
                logger.info(f"🎯 Router passing selected docs: {req.selected_document_ids}")
 
                async for chunk_data in rag_generator.generate_response_stream(
                    query=req.query,
                    memory_context=memory_context,
                    top_k=effective_top_k,  # ✅ Use hybrid dynamic top_k
                    include_complete_response=req.include_complete_response,
                    selected_document_ids=req.selected_document_ids,  # ✅ THIS WAS MISSING
                    user_id=user_uuid,
                    collection_id=collection_id,
                    response_language=response_language,
                    conversational_style=req.Conversational_style,  # ✅ ADD
                    chat_length=req.chat_length                      # ✅ ADD
                ):
                    if chunk_data.get("type") == "chunk":
                        raw_response += chunk_data.get("content", "")
                        yield f"{json.dumps(chunk_data)}\n"
                   
                    elif chunk_data.get("type") == "sources":
                        document_sources = [
                            s for s in chunk_data.get("sources_used", [])
                            if s.get("source_type") != "memory"
                        ]
 
                        # Merge sources
                        all_sources = []
                        seen_sources = set()
                       
                        for source in document_sources:
                            source_key = f"{source.get('source_file')}_{source.get('page_number', 'N/A')}"
                            if source_key not in seen_sources:
                                seen_sources.add(source_key)
                                all_sources.append(source)
                       
                        for source in memory_sources:
                            source_key = f"{source.get('source_file')}_{source.get('page_number', 'N/A')}"
                            if source_key not in seen_sources:
                                seen_sources.add(source_key)
                                source_with_context = source.copy()
                                source_with_context['from_memory'] = True
                                all_sources.append(source_with_context)
                       
                        sources_used = all_sources
                        chunk_data['sources_used'] = all_sources
                        reference_map = chunk_data.get("reference_map", {})
                        yield f"{json.dumps(chunk_data)}\n"
                   
                    else:
                        yield f"{json.dumps(chunk_data)}\n"
               
                logger.info("✅ RAG streaming completed")
            except Exception as stream_error:
                logger.error(f"❌ Streaming error: {str(stream_error)}")
                error_data = {"type": "error", "content": f"Error: {str(stream_error)}"}
                yield f"{json.dumps(error_data)}\n"
                return
 
            # # Save to memory
            # if memory_layer:
            #     try:
            #         sources_to_save = [s for s in sources_used if not s.get('from_memory', False)]
            #         memory_layer.save_semantic_memory(
            #             user_query=req.query,
            #             assistant_response=full_response,
            #             sources_used=sources_to_save
            #         )
            #         logger.info(f"✅ Saved to memory")
            #     except Exception as mem_error:
            #         logger.error(f"❌ Memory save error: {str(mem_error)}")
 
            # Log query
            clean_response = re.sub(
                r'<FOLLOW_UP_QUESTIONS>[\s\S]*?</FOLLOW_UP_QUESTIONS>',
                '',
                raw_response,
                flags=re.IGNORECASE
            ).strip()
            # try:
            #     db.execute(text("""
            #         INSERT INTO queries (
            #             id, user_id, collection_id,
            #             query_text, response_text, sources_used, created_at
            #         )
            #         VALUES (:id, :uid, :cid, :query, :response, :sources, CURRENT_TIMESTAMP)
            #     """), {
            #         "id": query_id,
            #         "uid": user_uuid,
            #         "cid": collection_id,
            #         "query": req.query,
            #         "response": clean_response,
            #         "sources": json.dumps(sources_used)
            #     })
            #     db.commit()
            #     logger.info(f"✅ Query logged")
            # except Exception as log_error:
            #     logger.error(f"❌ Query log error: {str(log_error)}")
            #     try:
            #         db.rollback()
            #     except:
            #         pass
            # Around line 450 (in stream_rag_response function)
            try:
                # Insert query into database
                db.execute(text("""
                    INSERT INTO queries (
                        id, user_id, collection_id,
                        query_text, response_text, sources_used,
                        reference_map, created_at  
                    )
                    VALUES (:id, :uid, :cid, :query, :response, :sources, :ref_map, CURRENT_TIMESTAMP)
                """), {
                    "id": query_id,
                    "uid": user_uuid,
                    "cid": collection_id,
                    "query": req.query,
                    "response": clean_response,
                    "sources": json.dumps(sources_used),
                    "ref_map": json.dumps(reference_map)
                })
                db.commit()
                
                # Track metrics
                duration = time.time() - start_time
                track_rag_duration(duration)
                track_query_executed()
                track_sources_count(len(sources_used))
                track_query_duration_by_length(len(req.query), duration)
                
                # ✅ RAGAs Evaluation (background)
                enable_ragas = os.getenv("ENABLE_RAGAS", "false").lower() == "true"
                
                if enable_ragas:
                    async def evaluate_in_background():
                        try:
                            evaluator = RAGAsEvaluator(db)
                            await evaluator.evaluate_query(
                                query_id=str(query_id),
                                query=req.query,
                                response=clean_response,
                                sources_used=sources_used,
                                ground_truth=None
                            )
                        except Exception as eval_error:
                            logger.error(f"Background evaluation error: {eval_error}")
                    
                    asyncio.create_task(evaluate_in_background())
                    logger.info(f"🎯 RAGAs evaluation queued for query {query_id}")
                
                logger.info(f"✅ Query logged with reference_map")
                
            except Exception as log_error:
                logger.error(f"❌ Query log error: {str(log_error)}")
                try:
                    db.rollback()
                except:
                    pass
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
            error_data = {"type": "error", "content": f"Error: {str(e)}"}
            yield f"{json.dumps(error_data)}\n"
 
    return StreamingResponse(stream_rag_response(), media_type="application/x-ndjson")