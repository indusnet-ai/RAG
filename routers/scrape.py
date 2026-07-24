from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Union
import os
import logging
from uuid import uuid4
from sqlalchemy import text
from dotenv import load_dotenv
from services.metrics import track_document_upload
load_dotenv()

from services.web_scraper import WebScraper
from services.embedding_generator import EmbeddingGenerator
from services.vector_db import VectorDB
from routers.dependencies import get_current_user
from db import get_db
from services.metrics import track_document_upload, track_upload_duration, track_web_crawl  # ✅ ADD THESE
import time

router = APIRouter(tags=["Source Upload"])
logger = logging.getLogger(__name__)

class WebScrapeRequest(BaseModel):
    urls: Union[str, List[str]]
    collection_name: str
    crawl: bool = False
    recursive_crawl: bool = False  # ✅ NEW: HTML link-based recursive crawling
    max_pages_per_url: int = 10

@router.post("/web/scrape")
async def scrape_web(
    req: WebScrapeRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Scrape web pages OR crawl entire sites.
    
    Parameters:
    - urls: Single URL or list of URLs to process
    - collection_name: Name of the collection to add content to
    - crawl: If False, scrapes only the exact URLs provided. If True, crawls all linked pages
    - max_pages_per_url: Maximum pages to crawl per URL (only used when crawl=True)
    
    Examples:
    Scrape mode: {"urls": "https://example.com", "collection_name": "docs", "crawl": false}
    Crawl mode: {"urls": "https://example.com", "collection_name": "docs", "crawl": true, "max_pages_per_url": 50}
    """
    try:
        # firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
        # if not firecrawl_api_key:
        #     raise HTTPException(
        #         status_code=500,
        #         detail="FIRECRAWL_API_KEY not found in environment variables."
        #     )

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

        scraper = WebScraper(use_undetected=True)
        embedder = EmbeddingGenerator()

        urls = req.urls if isinstance(req.urls, list) else [req.urls]
        urls = list(dict.fromkeys(urls))  # Remove duplicates

        if not urls:
            raise HTTPException(status_code=400, detail="Please provide at least one URL")

        results = []

        for url in urls:
            upload_start_time = time.time()
            try:
                crawled_urls = []  # Track all crawled pages
                
                # Choose between crawl and scrape mode
                # Choose between recursive crawl, crawl, or scrape mode
                if req.recursive_crawl:  # ✅ NEW: Check recursive_crawl FIRST
                    track_web_crawl("recursive")
                    logger.info(f"🔥 Recursive crawling Web URL: {url} (max {req.max_pages_per_url} pages)")
                    chunks, crawled_urls = await scraper.crawl_recursively(
                        url=url,
                        max_pages=req.max_pages_per_url
                    )
                elif req.crawl:  # ✅ Changed from 'if' to 'elif'
                    track_web_crawl("crawl")
                    logger.info(f"🔥 Crawling Web URL: {url} (max {req.max_pages_per_url} pages)")
                    chunks, crawled_urls = await scraper.crawl_url(
                        url=url,
                        max_pages=req.max_pages_per_url
                    )
                else:
                    track_web_crawl("scrape")
                    logger.info(f"🌐 Scraping Web URL: {url}")
                    chunks = await scraper.scrape_url(url=url)
                    crawled_urls = [url]  # Just the single page
                
                if not chunks:
                    logger.warning(f"⚠️ No content extracted from {url}")
                    results.append({
                        "url": url,
                        "status": "warning",
                        "message": "No content extracted"
                    })
                    continue
                
                embedded_chunks = embedder.generate_embeddings(chunks)

                document_id = uuid4()

                # Insert document record
                db.execute(text("""
                    INSERT INTO documents (
                        id, collection_id, user_id, file_name, source_url, file_type, chunk_count
                    ) VALUES (
                        :id, :cid, :uid, :name, :url, 'web', :count
                    )
                """), {
                    "id": document_id,
                    "cid": collection_id,
                    "uid": user_uuid,
                    "name": f"Crawled Site - {url}" if req.crawl else "Web Page Content",
                    "url": url,
                    "count": len(embedded_chunks)
                })

                # Insert all chunks
                for emb in embedded_chunks:
                    c = emb.chunk
                    vector_data = emb.embedding.tolist()
                    vector_str = f"[{','.join(map(str, vector_data))}]"

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
                        "source_file": c.metadata.get('original_url', url),  # Use actual page URL
                        "page_num": None,
                        "emb_model": "text-embedding-3-large",
                        "metadata": '{}'
                    })

                db.commit()
                track_document_upload("web")
                upload_duration = time.time() - upload_start_time
                track_upload_duration("web", upload_duration)

                # Build response
                result_data = {
                    "url": url,
                    "collection_id": str(collection_id),
                    "collection_name": req.collection_name,
                    "document_id": str(document_id),
                    "chunks_inserted": len(embedded_chunks),
                    "crawl_mode": req.crawl,
                    "status": "success"
                }
                
                # Add crawled pages info if in crawl mode
                if req.crawl or req.recursive_crawl:  # ✅ Added recursive_crawl
                    result_data["pages_crawled"] = len(crawled_urls)
                    result_data["crawled_urls"] = crawled_urls
                
                results.append(result_data)
                
                logger.info(f"✅ Successfully processed {url}: {len(embedded_chunks)} chunks inserted")

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
        logger.error(f"❌ Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))