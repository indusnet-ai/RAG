"""
Web Source Discovery API Router
Endpoints for discovering and curating web sources
"""

import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
import logging

from sqlalchemy import text

from db import get_db
from services.web_discovery_service import WebDiscoveryService, WebSource
from routers.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/web-discovery", tags=["Web Discovery"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class DiscoveryRequest(BaseModel):
    """Request model for source discovery"""
    query: str = Field(
        ...,
        description="Natural language query to search for sources",
        min_length=3,
        max_length=500,
        example="Latest developments in quantum computing 2024"
    )
    max_sources: int = Field(
        10,
        description="Maximum number of sources to return",
        ge=1,
        le=50
    )
    results_per_intent: int = Field(
        15,
        description="Search results to fetch per intent",
        ge=5,
        le=30
    )
    num_intents: int = Field(
        4,
        description="Number of search angle variations",
        ge=1,
        le=8
    )


class SourceResponse(BaseModel):
    """Response model for a single source"""
    source_id: str
    title: str
    url: str
    publisher: str
    content_type: str
    source_format: str  # ✅ ADD THIS LINE
    relevance_reason: str
    published_date: Optional[str] = None
    snippet: Optional[str] = None


class DiscoveryResponse(BaseModel):
    """Response model for source discovery"""
    query: str
    total_sources: int
    sources: List[SourceResponse]
    metadata: dict


class DiscoveryStatsResponse(BaseModel):
    """Statistics about discovery service"""
    status: str
    available: bool
    message: str

# ============================================================================
# SOURCE INGESTION (Using Existing Services)
# ============================================================================

class IngestSourceRequest(BaseModel):
    """Request to ingest selected sources"""
    sources: List[dict] = Field(
        ...,
        description="List of sources to ingest (from discovery response)"
    )
    collection_name: str = Field(
        ...,
        description="Target collection name"
    )


class IngestSourceResponse(BaseModel):
    """Response for source ingestion"""
    source_url: str
    source_format: str
    title: str
    status: str
    document_id: Optional[str] = None
    chunks_created: Optional[int] = None
    error: Optional[str] = None

# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/discover", response_model=DiscoveryResponse)
async def discover_sources(
    request: DiscoveryRequest,
    current_user=Depends(get_current_user)
):
    """
    Discover and curate web sources for a given query.
    
    **Process:**
    1. Interprets query intent (time-sensitivity, domain)
    2. Generates multiple search angles
    3. Searches DuckDuckGo (free, no API key)
    4. Ranks by authority and relevance
    5. Ensures publisher diversity
    6. Returns structured sources
    
    **Features:**
    - No hallucination (all real URLs)
    - Authority-based ranking
    - Publisher diversity
    - Time-sensitive detection
    
    **Example Request:**
```json
    {
        "query": "Latest AI safety research",
        "max_sources": 10
    }
```
    
    **Example Response:**
```json
    {
        "query": "Latest AI safety research",
        "total_sources": 10,
        "sources": [
            {
                "source_id": "src_001",
                "title": "AI Safety Research at OpenAI",
                "url": "https://openai.com/research/ai-safety",
                "publisher": "openai.com",
                "content_type": "article",
                "relevance_reason": "Authoritative source; Technical authority"
            }
        ],
        "metadata": {
            "time_sensitive": true,
            "domain": "tech"
        }
    }
```
    """
    try:
        logger.info(f"📥 Discovery request from user {current_user.id}: '{request.query}'")
        
        # Initialize service
        service = WebDiscoveryService()
        
        # Discover sources
        sources = service.discover_sources(
            user_query=request.query,
            max_sources=request.max_sources,
            results_per_intent=request.results_per_intent,
            num_intents=request.num_intents
        )
        
        # Convert to response model
        source_responses = [
            SourceResponse(
                source_id=source.source_id,
                title=source.title,
                url=source.url,
                publisher=source.publisher,
                content_type=source.content_type,
                source_format=source.source_format,  # ✅ ADD THIS LINE
                relevance_reason=source.relevance_reason,
                published_date=source.published_date,
                snippet=source.snippet
            )
            for source in sources
        ]
        
        # Build response
        response = DiscoveryResponse(
            query=request.query,
            total_sources=len(source_responses),
            sources=source_responses,
            metadata={
                "user_id": str(current_user.id),
                "time_sensitive": any('recent' in request.query.lower() or 'latest' in request.query.lower() for _ in [1]),
                "domain": "general"  # Can be enhanced
            }
        )
        
        logger.info(f"✅ Discovery complete: {len(sources)} sources returned")
        return response
        
    except Exception as e:
        logger.error(f"❌ Discovery error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Source discovery failed: {str(e)}"
        )





@router.post("/ingest", response_model=List[IngestSourceResponse])
async def ingest_selected_sources(
    request: IngestSourceRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Ingest selected sources into a collection using existing services.
    
    **Supported Formats:**
    - `pdf`: Downloads and processes PDF (DocumentProcessor)
    - `youtube`: Transcribes video (YouTubeTranscriber)
    - `web`: Scrapes webpage (WebScraper with crawl4ai)
    
    **Example Request:**
```json
    {
        "sources": [
            {
                "url": "https://arxiv.org/pdf/2401.12345.pdf",
                "title": "Quantum Computing Paper",
                "source_format": "pdf"
            },
            {
                "url": "https://youtube.com/watch?v=abc123",
                "title": "Quantum Computing Lecture",
                "source_format": "youtube"
            },
            {
                "url": "https://mit.edu/quantum-research",
                "title": "MIT Quantum Lab",
                "source_format": "web"
            }
        ],
        "collection_name": "Quantum Research"
    }
```
    """
    try:
        user_uuid = str(current_user.id)
        logger.info(f"📥 Ingest request: {len(request.sources)} sources → '{request.collection_name}'")
        
        # Verify collection exists
        collection_result = db.execute(text("""
            SELECT id FROM collections 
            WHERE collection_name = :name AND user_id = :uid
        """), {"name": request.collection_name, "uid": user_uuid})
        
        collection_row = collection_result.fetchone()
        if not collection_row:
            raise HTTPException(
                status_code=404,
                detail=f"Collection '{request.collection_name}' not found. Please create it first."
            )
        
        collection_id = collection_row.id
        
        # Import existing services
        from services.document_service import DocumentService
        from services.youtube_transcriber import YouTubeTranscriber
        from services.web_scraper import WebScraper
        from services.embedding_generator import EmbeddingGenerator
        import requests
        import tempfile
        import asyncio
        from uuid import uuid4
        import json
        
        # Initialize services
        doc_service = DocumentService()
        embedder = EmbeddingGenerator()
        
        # Initialize YouTube transcriber if needed
        sarvam_api_key = os.getenv("SARVAM_API_KEY")
        youtube_api_key = os.getenv("YOUTUBE_API_KEY")
        yt_transcriber = None
        
        # Initialize web scraper if needed
        web_scraper = None
        
        results = []
        
        for source in request.sources:
            try:
                url = source.get('url')
                title = source.get('title', 'Untitled')
                source_format = source.get('source_format', 'web')
                
                logger.info(f"🔄 Processing {source_format}: {title}")
                
                chunks = []
                document_id = uuid4()
                
                # ================================================================
                # ROUTE TO APPROPRIATE SERVICE BASED ON FORMAT
                # ================================================================
                
                if source_format == 'pdf':
                    # ✅ PDF: Download → Process with DocumentService
                    try:
                        logger.info(f"📄 Downloading PDF from {url}")
                        response = requests.get(url, timeout=30, headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        })
                        response.raise_for_status()
                        
                        # Save to temp file
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                            tmp.write(response.content)
                            tmp_path = tmp.name
                        
                        # ✅ Use existing DocumentService
                        chunks = doc_service.process_uploaded_file(tmp_path, f"{title}.pdf")
                        
                        # Cleanup
                        os.remove(tmp_path)
                        
                        logger.info(f"✅ PDF processed: {len(chunks)} chunks")
                        
                    except Exception as e:
                        logger.error(f"❌ PDF processing error: {str(e)}")
                        results.append(IngestSourceResponse(
                            source_url=url,
                            source_format=source_format,
                            title=title,
                            status="failed",
                            error=f"PDF download/processing failed: {str(e)}"
                        ))
                        continue
                
                elif source_format == 'youtube':
                    # ✅ YouTube: Use existing YouTubeTranscriber
                    try:
                        if yt_transcriber is None:
                            if not sarvam_api_key:
                                raise Exception("SARVAM_API_KEY not configured")
                            yt_transcriber = YouTubeTranscriber(
                                sarvam_api_key=sarvam_api_key,
                                youtube_api_key=youtube_api_key
                            )
                        
                        logger.info(f"🎬 Transcribing YouTube: {url}")
                        
                        # ✅ Use existing YouTubeTranscriber (returns chunks + video_title)
                        chunks, video_title = yt_transcriber.transcribe_youtube_video(
                            url=url,
                            cleanup_audio=True,
                            language="en-IN",
                            enable_diarization=False,
                            num_speakers=1
                        )
                        
                        # Use video title if available
                        if video_title:
                            title = video_title
                        
                        logger.info(f"✅ YouTube transcribed: {len(chunks)} chunks")
                        
                    except Exception as e:
                        logger.error(f"❌ YouTube transcription error: {str(e)}")
                        results.append(IngestSourceResponse(
                            source_url=url,
                            source_format=source_format,
                            title=title,
                            status="failed",
                            error=f"YouTube transcription failed: {str(e)}"
                        ))
                        continue
                
                elif source_format == 'web':
                    # ✅ Web: Use existing WebScraper (crawl4ai)
                    try:
                        if web_scraper is None:
                            # Initialize crawl4ai-based scraper
                            web_scraper = WebScraper()
                        
                        logger.info(f"🌐 Scraping web: {url}")
                        
                        # ✅ Use existing WebScraper (async method)
                        chunks = await web_scraper.scrape_url(
                            url=url,
                            chunk_size=1000,
                            chunk_overlap=100
                        )
                        
                        logger.info(f"✅ Web scraped: {len(chunks)} chunks")
                        
                    except Exception as e:
                        logger.error(f"❌ Web scraping error: {str(e)}")
                        results.append(IngestSourceResponse(
                            source_url=url,
                            source_format=source_format,
                            title=title,
                            status="failed",
                            error=f"Web scraping failed: {str(e)}"
                        ))
                        continue
                
                else:
                    results.append(IngestSourceResponse(
                        source_url=url,
                        source_format=source_format,
                        title=title,
                        status="failed",
                        error=f"Unsupported format: {source_format}"
                    ))
                    continue
                
                # ================================================================
                # GENERATE EMBEDDINGS (Same for all formats)
                # ================================================================
                
                embedded_chunks = embedder.generate_embeddings(chunks)
                
                # ================================================================
                # STORE IN DATABASE
                # ================================================================
                
                # Insert document record
                db.execute(text("""
                    INSERT INTO documents (
                        id, collection_id, user_id, file_name,
                        source_url, file_type, chunk_count
                    )
                    VALUES (:id, :cid, :uid, :fname, :url, :ftype, :count)
                """), {
                    "id": document_id,
                    "cid": collection_id,
                    "uid": user_uuid,
                    "fname": title,
                    "url": url,
                    "ftype": source_format,
                    "count": len(embedded_chunks)
                })
                
                # Insert chunks
                for emb in embedded_chunks:
                    c = emb.chunk
                    vector_data = emb.embedding.tolist()
                    vector_str = f"[{','.join(map(str, vector_data))}]"
                    
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
                        "stype": source_format,
                        "source_file": title,
                        "page_num": c.page_number if hasattr(c, 'page_number') else None,
                        "emb_model": "text-embedding-3-large",
                        "metadata": metadata_json
                    })
                
                db.commit()
                
                results.append(IngestSourceResponse(
                    source_url=url,
                    source_format=source_format,
                    title=title,
                    status="success",
                    document_id=str(document_id),
                    chunks_created=len(embedded_chunks)
                ))
                
                logger.info(f"✅ Ingested: {title} ({len(embedded_chunks)} chunks)")
                
            except Exception as e:
                db.rollback()
                logger.error(f"❌ Ingestion error for {source.get('url')}: {str(e)}", exc_info=True)
                results.append(IngestSourceResponse(
                    source_url=source.get('url', 'unknown'),
                    source_format=source.get('source_format', 'unknown'),
                    title=source.get('title', 'unknown'),
                    status="failed",
                    error=str(e)
                ))
        
        successful = len([r for r in results if r.status == 'success'])
        logger.info(f"🎉 Ingestion complete: {successful}/{len(results)} successful")
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ingestion failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion failed: {str(e)}"
        )
