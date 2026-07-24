"""
Hybrid Search Module: BM25 (Keyword) + Vector (Semantic) Search
Uses PostgreSQL Full-Text Search (FTS) for BM25-like keyword matching
Uses Reciprocal Rank Fusion (RRF) for intelligent result merging
Seamlessly integrates with existing RAG pipeline
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import text
import json
import math

logger = logging.getLogger(__name__)


# ============================================================================
# SCORE NORMALIZATION
# ============================================================================

def _normalize_vector_score(distance: float) -> float:
    """
    Normalize PostgreSQL vector distance to 0-1 range (1 = best).
    
    Vector distance typically ranges 0-2:
    - 0.0 = identical vectors
    - 1.0 = orthogonal
    - 2.0 = opposite
    
    We invert: (1 - distance/2) so higher = better
    """
    if distance is None:
        return 0.0
    clamped = min(max(distance, 0), 2)
    return 1 - (clamped / 2)


def _normalize_fts_score(rank: float) -> float:
    """
    Normalize PostgreSQL ts_rank() to 0-1 range.
    PostgreSQL ts_rank() already returns 0-1 where 1 = best.
    """
    if rank is None:
        return 0.0
    return min(max(rank, 0), 1)


# ============================================================================
# RECIPROCAL RANK FUSION (RRF)
# ============================================================================

def _rrf_score(rank: int, k: int = 60) -> float:
    """
    Reciprocal Rank Fusion formula: 1 / (k + rank).
    
    Args:
        rank: Position in ranking (1-based, so first result = rank 1)
        k: Constant (default 60). Higher k = less difference between ranks
        
    Returns:
        RRF score (typically 0.01-0.017 range)
        
    Example:
        rank=1, k=60 → 1/61 = 0.0164
        rank=2, k=60 → 1/62 = 0.0161
        rank=10, k=60 → 1/70 = 0.0143
    """
    if rank < 1:
        rank = 1
    return 1.0 / (k + rank)


# ============================================================================
# RESULT MERGING WITH RRF + WEIGHTED FUSION
# ============================================================================

def _merge_results_with_rrf(
    semantic_results: List[Dict[str, Any]],
    keyword_results: List[Dict[str, Any]],
    semantic_weight: float = 0.6,
    keyword_weight: float = 0.4
) -> List[Dict[str, Any]]:
    """
    Merge semantic (vector) + keyword (BM25) results using RRF + weighted fusion.
    
    Strategy:
    1. Apply RRF to each ranking independently
    2. Normalize scores from both methods
    3. Combine with configurable weights
    4. Re-rank by final hybrid score
    
    Args:
        semantic_results: Results from vector search (ranked by distance)
        keyword_results: Results from FTS search (ranked by relevance)
        semantic_weight: Weight for semantic scores (0.0-1.0, default 0.6)
        keyword_weight: Weight for keyword scores (0.0-1.0, default 0.4)
    
    Returns:
        List of merged results sorted by hybrid score (best first)
    """
    merged = {}
    
    # ========================================================================
    # PROCESS SEMANTIC RESULTS (Vector Search)
    # ========================================================================
    for rank, result in enumerate(semantic_results, 1):
        chunk_id = str(result["id"])
        vec_distance = result.get("score", 2.0)
        
        # Normalize distance to 0-1 (1 = best)
        normalized_vec_score = _normalize_vector_score(vec_distance)
        
        # Apply RRF to this rank
        rrf_vec_score = _rrf_score(rank)
        
        merged[chunk_id] = {
            "data": result,
            "semantic_normalized_score": normalized_vec_score,
            "semantic_rrf_score": rrf_vec_score,
            "keyword_normalized_score": 0.0,
            "keyword_rrf_score": 0.0,
            "found_in": "semantic"
        }
    
    # ========================================================================
    # PROCESS KEYWORD RESULTS (FTS Search)
    # ========================================================================
    for rank, result in enumerate(keyword_results, 1):
        chunk_id = str(result["id"])
        fts_rank = result.get("score", 0.0)
        
        # Normalize FTS score to 0-1
        normalized_fts_score = _normalize_fts_score(fts_rank)
        
        # Apply RRF to this rank
        rrf_fts_score = _rrf_score(rank)
        
        if chunk_id in merged:
            # Chunk found in both results - merge keyword scores
            merged[chunk_id]["keyword_normalized_score"] = normalized_fts_score
            merged[chunk_id]["keyword_rrf_score"] = rrf_fts_score
            merged[chunk_id]["found_in"] = "both"
        else:
            # Chunk only in keyword results
            merged[chunk_id] = {
                "data": result,
                "semantic_normalized_score": 0.0,
                "semantic_rrf_score": 0.0,
                "keyword_normalized_score": normalized_fts_score,
                "keyword_rrf_score": rrf_fts_score,
                "found_in": "keyword"
            }
    
    # ========================================================================
    # CALCULATE FINAL HYBRID SCORE
    # ========================================================================
    for chunk_id, entry in merged.items():
        # Weighted combination of RRF scores
        final_score = (
            (entry["semantic_rrf_score"] * semantic_weight) +
            (entry["keyword_rrf_score"] * keyword_weight)
        )
        entry["final_hybrid_score"] = final_score
        
        # Add search method metadata to result
        entry["data"]["search_metadata"] = {
            "semantic_score": entry["semantic_normalized_score"],
            "keyword_score": entry["keyword_normalized_score"],
            "hybrid_score": final_score,
            "found_in": entry["found_in"]
        }
    
    # Sort by final score (highest first)
    sorted_results = sorted(
        merged.values(),
        key=lambda x: x["final_hybrid_score"],
        reverse=True
    )
    
    return [r["data"] for r in sorted_results]


# ============================================================================
# DATABASE SEARCH FUNCTIONS
# ============================================================================

def _search_semantic(
    db,
    query_vector: List[float],
    user_id: str,
    collection_id: str,
    limit: int,
    selected_document_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Search using vector similarity (semantic search).
    Returns top-k results sorted by distance (closest first).
    """
    try:
        if db.bind.dialect.name == "sqlite":
            import numpy as np
            doc_filter_sql = ""
            params = {
                "uid": user_id,
                "cid": collection_id,
            }
            
            if selected_document_ids:
                placeholders = ", ".join(f":doc_id_{i}" for i in range(len(selected_document_ids)))
                doc_filter_sql = f"AND c.document_id IN ({placeholders})"
                for i, did in enumerate(selected_document_ids):
                    params[f"doc_id_{i}"] = str(did)
            
            result = db.execute(text(f"""
                SELECT 
                    c.id,
                    c.content,
                    c.source_file,
                    c.source_type,
                    c.page_number,
                    c.chunk_index,
                    c.start_char,
                    c.end_char,
                    c.document_id,
                    c.metadata,
                    c.vector
                FROM chunks c
                WHERE c.user_id = :uid 
                AND c.collection_id = :cid
                AND (c.is_deleted = FALSE OR c.is_deleted IS NULL)
                {doc_filter_sql}
            """), params)
            
            rows = result.fetchall()
            semantic_results = []
            q_vec = np.array(query_vector)
            
            for row in rows:
                vec_str = row.vector
                if not vec_str:
                    continue
                try:
                    row_vec = np.array(json.loads(vec_str))
                except Exception:
                    continue
                
                if row_vec.shape != q_vec.shape:
                    if row_vec.shape[0] < q_vec.shape[0]:
                        row_vec = np.pad(row_vec, (0, q_vec.shape[0] - row_vec.shape[0]))
                    else:
                        row_vec = row_vec[:q_vec.shape[0]]

                distance = float(np.linalg.norm(row_vec - q_vec))
                
                source_file = row.source_file
                if not source_file and row.document_id:
                    doc_result = db.execute(text("""
                        SELECT file_name 
                        FROM documents 
                        WHERE id = :doc_id 
                        AND (is_deleted = FALSE OR is_deleted IS NULL)
                    """), {"doc_id": row.document_id})
                    doc_row = doc_result.fetchone()
                    source_file = doc_row.file_name if doc_row else "Unknown"
                
                metadata = {}
                try:
                    if row.metadata:
                        metadata = json.loads(row.metadata) if isinstance(row.metadata, str) else row.metadata
                except Exception as e:
                    logger.warning(f"Failed to parse metadata: {e}")
                
                semantic_results.append({
                    "id": row.id,
                    "content": row.content,
                    "score": distance,
                    "metadata": metadata,
                    "citation": {
                        "source_file": source_file or "Unknown",
                        "source_type": row.source_type or "document",
                        "page_number": row.page_number,
                        "chunk_index": row.chunk_index,
                        "start_char": row.start_char,
                        "end_char": row.end_char,
                        "document_id": str(row.document_id),
                        "metadata": metadata
                    }
                })
            
            semantic_results.sort(key=lambda x: x["score"])
            logger.info(f"🔎 Semantic search (SQLite): {len(semantic_results)} results")
            return semantic_results[:limit]

        # PostgreSQL logic
        vector_str = f"[{','.join(map(str, query_vector))}]"
        
        doc_filter_sql = ""
        params = {
            "query_vector": vector_str,
            "uid": user_id,
            "cid": collection_id,
            "limit": limit,
        }
        
        if selected_document_ids:
            doc_filter_sql = """
                AND c.document_id = ANY(
                    ARRAY(SELECT UNNEST(:doc_ids))::uuid[]
                )
            """
            params["doc_ids"] = selected_document_ids
        
        result = db.execute(text(f"""
            SELECT 
                c.id,
                c.content,
                c.source_file,
                c.source_type,
                c.page_number,
                c.chunk_index,
                c.start_char,
                c.end_char,
                c.document_id,
                c.metadata,
                c.vector <-> CAST(:query_vector AS vector) AS distance
            FROM chunks c
            WHERE c.user_id = :uid 
            AND c.collection_id = :cid
            AND (c.is_deleted = FALSE OR c.is_deleted IS NULL)
            {doc_filter_sql}
            ORDER BY c.vector <-> CAST(:query_vector AS vector)
            LIMIT :limit
        """), params)
        
        rows = result.fetchall()
        semantic_results = []
        
        for row in rows:
            source_file = row.source_file
            
            if not source_file and row.document_id:
                doc_result = db.execute(text("""
                    SELECT file_name 
                    FROM documents 
                    WHERE id = :doc_id 
                    AND (is_deleted = FALSE OR is_deleted IS NULL)
                """), {"doc_id": row.document_id})
                doc_row = doc_result.fetchone()
                source_file = doc_row.file_name if doc_row else "Unknown"
            
            metadata = {}
            try:
                if row.metadata:
                    metadata = json.loads(row.metadata) if isinstance(row.metadata, str) else row.metadata
            except Exception as e:
                logger.warning(f"Failed to parse metadata: {e}")
            
            semantic_results.append({
                "id": row.id,
                "content": row.content,
                "score": float(row.distance),
                "metadata": metadata,
                "citation": {
                    "source_file": source_file or "Unknown",
                    "source_type": row.source_type or "document",
                    "page_number": row.page_number,
                    "chunk_index": row.chunk_index,
                    "start_char": row.start_char,
                    "end_char": row.end_char,
                    "document_id": str(row.document_id),
                    "metadata": metadata
                }
            })
        
        logger.info(f"🔎 Semantic search: {len(semantic_results)} results")
        return semantic_results
        
    except Exception as e:
        logger.error(f"Error in semantic search: {str(e)}")
        raise


def _search_keyword(
    db,
    query_text: str,
    user_id: str,
    collection_id: str,
    limit: int,
    selected_document_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Search using PostgreSQL Full-Text Search (FTS) or SQLite standard LIKE.
    Simple keyword extraction for maximum compatibility.
    """
    try:
        # Extract meaningful keywords (remove stop words)
        stop_words = {
            'what', 'are', 'the', 'is', 'a', 'an', 'and', 'or', 'of', 'in', 'to', 'for',
            'tell', 'me', 'about', 'how', 'can', 'you', 'do', 'does', 'be', 'been',
            'have', 'has', 'we', 'i', 'it', 'that', 'this', 'with', 'by'
        }
        
        # Split query and filter
        keywords = [w.lower() for w in query_text.split() if w.lower() not in stop_words and len(w) > 2]
        
        if not keywords:
            logger.info(f"🔑 Keyword search: 0 results (no meaningful keywords)")
            return []
        
        is_sqlite = db.bind.dialect.name == "sqlite"
        like_op = "LIKE" if is_sqlite else "ILIKE"
        
        # Create OR condition: match ANY keyword
        or_conditions = " OR ".join([f"c.content {like_op} :kw{i}" for i in range(len(keywords))])
        
        doc_filter_sql = ""
        params = {
            "uid": user_id,
            "cid": collection_id,
            "limit": limit,
            "exact_phrase": f"%{query_text}%"
        }
        
        # Add keyword params
        for i, kw in enumerate(keywords):
            params[f"kw{i}"] = f"%{kw}%"
        
        if selected_document_ids:
            if is_sqlite:
                placeholders = ", ".join(f":doc_id_{i}" for i in range(len(selected_document_ids)))
                doc_filter_sql = f"AND c.document_id IN ({placeholders})"
                for i, did in enumerate(selected_document_ids):
                    params[f"doc_id_{i}"] = str(did)
            else:
                doc_filter_sql = """
                    AND c.document_id = ANY(
                        ARRAY(SELECT UNNEST(:doc_ids))::uuid[]
                    )
                """
                params["doc_ids"] = selected_document_ids
        
        sql = f"""
            SELECT 
                c.id,
                c.content,
                c.source_file,
                c.source_type,
                c.page_number,
                c.chunk_index,
                c.start_char,
                c.end_char,
                c.document_id,
                c.metadata,
                (
                    (CASE WHEN c.content {like_op} :exact_phrase THEN 3 ELSE 0 END) +
                    (
                        CASE 
                            WHEN c.content {like_op} '% ' || :kw0 || ' %' THEN 2
                            WHEN c.content {like_op} :kw0 THEN 1
                            ELSE 0
                        END
                    )
                ) as relevance_score
            FROM chunks c
            WHERE c.user_id = :uid 
            AND c.collection_id = :cid
            AND (c.is_deleted = FALSE OR is_deleted IS NULL)
            AND ({or_conditions})
            {doc_filter_sql}
            ORDER BY relevance_score DESC, c.chunk_index
            LIMIT :limit
        """
        
        result = db.execute(text(sql), params)
        
        rows = result.fetchall()
        keyword_results = []
        
        for row in rows:
            source_file = row.source_file
            
            if not source_file and row.document_id:
                doc_result = db.execute(text("""
                    SELECT file_name 
                    FROM documents 
                    WHERE id = :doc_id 
                    AND (is_deleted = FALSE OR is_deleted IS NULL)
                """), {"doc_id": row.document_id})
                doc_row = doc_result.fetchone()
                source_file = doc_row.file_name if doc_row else "Unknown"
            
            metadata = {}
            try:
                if row.metadata:
                    metadata = json.loads(row.metadata) if isinstance(row.metadata, str) else row.metadata
            except Exception as e:
                logger.warning(f"Failed to parse metadata: {e}")
            
            keyword_results.append({
                "id": row.id,
                "content": row.content,
                "score": float(row.relevance_score) if row.relevance_score else 0.5,
                "metadata": metadata,
                "citation": {
                    "source_file": source_file or "Unknown",
                    "source_type": row.source_type or "document",
                    "page_number": row.page_number,
                    "chunk_index": row.chunk_index,
                    "start_char": row.start_char,
                    "end_char": row.end_char,
                    "document_id": str(row.document_id),
                    "metadata": metadata
                }
            })
        
        logger.info(f"🔑 Keyword search: {len(keyword_results)} results from {len(keywords)} keywords: {keywords}")
        return keyword_results
        
    except Exception as e:
        logger.error(f"❌ Error in keyword search: {str(e)}")
        logger.warning("Keyword search failed, returning empty results")
        return []


# ============================================================================
# MAIN HYBRID SEARCH FUNCTION
# ============================================================================

def search_chunks_hybrid(
    db,
    query_text: str,
    query_vector: List[float],
    user_id: str,
    collection_id: str,
    limit: int = 10,
    selected_document_ids: Optional[List[str]] = None,
    semantic_weight: float = 0.6,
    keyword_weight: float = 0.4
) -> List[Dict[str, Any]]:
    """
    Hybrid search combining semantic (vector) + keyword (FTS/BM25) search.
    
    Flow:
    1. Run semantic search (vector similarity)
    2. Run keyword search (FTS)
    3. Merge results using RRF + weighted fusion
    4. Return merged list sorted by hybrid score
    
    Args:
        db: Database session
        query_text: Raw query text for keyword search
        query_vector: Embedding vector for semantic search
        user_id: User ID for filtering
        collection_id: Collection ID for filtering
        limit: Maximum number of results to retrieve per method
        selected_document_ids: Optional document filter list
        semantic_weight: Weight for semantic component (0.0-1.0)
        keyword_weight: Weight for keyword component (0.0-1.0)
    
    Returns:
        List of merged results sorted by hybrid score (best first)
    
    Raises:
        Exception: If both searches fail completely
    """
    
    logger.info(
        f"🔄 Starting hybrid search | query='{query_text[:50]}...' | "
        f"weights=[semantic:{semantic_weight}, keyword:{keyword_weight}]"
    )
    
    try:
        # ====================================================================
        # PARALLEL SEARCH EXECUTION
        # ====================================================================
        
        # Run semantic search (vector)
        semantic_results = _search_semantic(
            db=db,
            query_vector=query_vector,
            user_id=user_id,
            collection_id=collection_id,
            limit=limit,
            selected_document_ids=selected_document_ids
        )
        
        # Run keyword search (FTS)
        keyword_results = _search_keyword(
            db=db,
            query_text=query_text,
            user_id=user_id,
            collection_id=collection_id,
            limit=limit,
            selected_document_ids=selected_document_ids
        )
        
        # ====================================================================
        # SAFETY CHECK: At least one must succeed
        # ====================================================================
        if not semantic_results and not keyword_results:
            logger.warning("⚠️ Both semantic and keyword searches returned no results")
            return []
        
        logger.info(
            f"✅ Hybrid search complete | "
            f"semantic={len(semantic_results)} | "
            f"keyword={len(keyword_results)}"
        )
        
        # ====================================================================
        # MERGE RESULTS USING RRF
        # ====================================================================
        merged_results = _merge_results_with_rrf(
            semantic_results=semantic_results,
            keyword_results=keyword_results,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight
        )
        
        logger.info(
            f"📊 Merged results: {len(merged_results)} unique chunks | "
            f"Top score: {merged_results[0]['search_metadata']['hybrid_score']:.4f}" 
            if merged_results else "No results"
        )
        
        return merged_results
        
    except Exception as e:
        logger.error(f"❌ Hybrid search failed: {str(e)}")
        raise


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_search_method_breakdown(results: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Analyze which search method found each result.
    Useful for debugging and monitoring.
    
    Args:
        results: Results from hybrid search (with search_metadata)
    
    Returns:
        Dict with counts: {'semantic': int, 'keyword': int, 'both': int}
    """
    breakdown = {"semantic": 0, "keyword": 0, "both": 0}
    
    for result in results:
        metadata = result.get("search_metadata", {})
        found_in = metadata.get("found_in", "unknown")
        if found_in in breakdown:
            breakdown[found_in] += 1
    
    return breakdown


def log_hybrid_scores(results: List[Dict[str, Any]], top_n: int = 5):
    """
    Log top N results with their score breakdown.
    Useful for debugging score calculations.
    
    Args:
        results: Results from hybrid search
        top_n: Number of top results to log
    """
    logger.info(f"📈 Top {top_n} results by hybrid score:")
    for i, result in enumerate(results[:top_n], 1):
        metadata = result.get("search_metadata", {})
        sem_score = metadata.get("semantic_score", 0)
        kw_score = metadata.get("keyword_score", 0)
        hybrid_score = metadata.get("hybrid_score", 0)
        found_in = metadata.get("found_in", "unknown")
        
        content_preview = result.get("content", "")[:60].replace("\n", " ")
        
        logger.info(
            f"  [{i}] {found_in:8s} | "
            f"sem={sem_score:.3f} | "
            f"kw={kw_score:.3f} | "
            f"hybrid={hybrid_score:.4f} | "
            f"'{content_preview}...'"
        )


if __name__ == "__main__":
    # Example usage (for testing)
    print("Hybrid Search Module loaded successfully")
    print(f"RRF k parameter: 60")
    print(f"Score normalization: vector[0-2]→[0-1], FTS[0-1]→[0-1]")