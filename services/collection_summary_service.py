"""
Collection Summary Service
Generates NotebookLM-style summaries of all documents in a collection

Features:
- Automatically updates when new sources are added
- Stores summary in database
- Intelligently samples from all documents
- Handles large collections with token management
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy import text
from openai import OpenAI
import os

logger = logging.getLogger(__name__)


class CollectionSummaryService:
    """
    Generates comprehensive summaries for collections.
    
    Similar to NotebookLM's automatic summary feature.
    """
    
    def __init__(self, db):
        self.db = db
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Token limits
        self.max_context_tokens = 120000  # GPT-4 context limit
        self.max_summary_tokens = 2000     # Target summary length
        self.chars_per_token = 4           # Rough estimate
        
    def generate_collection_summary(
        self,
        collection_id: str,
        user_id: str,
        force_regenerate: bool = False
    ) -> Dict[str, any]:
        """
        Generate or retrieve collection summary.
        
        Args:
            collection_id: Collection UUID
            user_id: User UUID
            force_regenerate: If True, regenerate even if summary exists
            
        Returns:
            Dict with summary and metadata
        """
        try:
            # Get collection info
            collection = self.db.execute(text("""
                SELECT 
                    id, collection_name, chat_title,
                    summary, summary_generated_at, summary_source_count
                FROM collections
                WHERE id = :cid AND user_id = :uid
                AND (is_deleted = FALSE OR is_deleted IS NULL)
            """), {"cid": collection_id, "uid": user_id}).fetchone()
            
            if not collection:
                raise ValueError("Collection not found")
            
            # Count current documents
            doc_count_result = self.db.execute(text("""
                SELECT COUNT(*) as count
                FROM documents
                WHERE collection_id = :cid
                AND (is_deleted = FALSE OR is_deleted IS NULL)
            """), {"cid": collection_id}).fetchone()
            
            current_doc_count = doc_count_result.count
            
            # Check if we need to regenerate
            needs_regeneration = (
                force_regenerate or
                not collection.summary or
                current_doc_count != collection.summary_source_count
            )
            
            if not needs_regeneration:
                logger.info(f"✅ Using cached summary for collection {collection_id}")
                return {
                    "summary": collection.summary,
                    "generated_at": collection.summary_generated_at.isoformat() if collection.summary_generated_at else None,
                    "source_count": collection.summary_source_count,
                    "cached": True
                }
            
            # Generate new summary
            logger.info(f"🔄 Generating new summary for collection {collection_id} ({current_doc_count} documents)")
            
            # Get document content
            documents = self._get_document_content(collection_id)
            
            if not documents:
                logger.warning(f"No documents found for collection {collection_id}")
                return {
                    "summary": "No sources have been added to this collection yet.",
                    "generated_at": None,
                    "source_count": 0,
                    "cached": False
                }
            
            # Generate summary
            summary_text = self._generate_summary_from_documents(
                documents,
                collection_name=collection.collection_name
            )
            
            # Store in database
            self.db.execute(text("""
                UPDATE collections
                SET 
                    summary = :summary,
                    summary_generated_at = CURRENT_TIMESTAMP,
                    summary_source_count = :count
                WHERE id = :cid
            """), {
                "summary": summary_text,
                "count": current_doc_count,
                "cid": collection_id
            })
            
            self.db.commit()
            
            logger.info(f"✅ Summary generated and stored for collection {collection_id}")
            
            return {
                "summary": summary_text,
                "generated_at": datetime.utcnow().isoformat(),
                "source_count": current_doc_count,
                "cached": False
            }
            
        except Exception as e:
            logger.error(f"❌ Error generating summary: {e}", exc_info=True)
            self.db.rollback()
            raise
    
    def _get_document_content(self, collection_id: str) -> List[Dict]:
        """
        Get representative content from all documents in collection.
        
        Strategy:
        - Get all documents
        - Sample chunks intelligently to stay within token limits
        - Prioritize variety (all documents represented)
        """
        try:
            # Check if sqlite or postgres
            is_sqlite = "sqlite" in str(self.db.bind.url).lower() if hasattr(self.db, "bind") and self.db.bind else True
            
            if is_sqlite:
                docs_query = text("""
                    SELECT d.id as doc_id, d.file_name, d.file_type, d.chunk_count
                    FROM documents d
                    WHERE d.collection_id = :cid AND (d.is_deleted = FALSE OR d.is_deleted IS NULL)
                    ORDER BY d.uploaded_at
                """)
                doc_rows = self.db.execute(docs_query, {"cid": collection_id}).fetchall()
                documents = []
                for drow in doc_rows:
                    chunks_query = text("""
                        SELECT content FROM chunks
                        WHERE document_id = :did AND (is_deleted = FALSE OR is_deleted IS NULL)
                        ORDER BY chunk_index
                    """)
                    c_rows = self.db.execute(chunks_query, {"did": drow.doc_id}).fetchall()
                    chunk_contents = [c[0] for c in c_rows if c[0]]
                    documents.append({
                        "doc_id": str(drow.doc_id),
                        "file_name": drow.file_name,
                        "file_type": drow.file_type,
                        "chunk_count": drow.chunk_count or len(chunk_contents),
                        "chunks": chunk_contents
                    })
                return documents
            else:
                # PostgreSQL
                documents_query = text("""
                    SELECT 
                        d.id as doc_id,
                        d.file_name,
                        d.file_type,
                        d.chunk_count,
                        array_agg(c.content ORDER BY c.chunk_index) as chunk_contents
                    FROM documents d
                    LEFT JOIN chunks c ON d.id = c.document_id
                        AND (c.is_deleted = FALSE OR c.is_deleted IS NULL)
                    WHERE d.collection_id = :cid
                    AND (d.is_deleted = FALSE OR d.is_deleted IS NULL)
                    GROUP BY d.id, d.file_name, d.file_type, d.chunk_count
                    ORDER BY d.uploaded_at
                """)
                rows = self.db.execute(documents_query, {"cid": collection_id}).fetchall()
                documents = []
                for row in rows:
                    documents.append({
                        "doc_id": str(row.doc_id),
                        "file_name": row.file_name,
                        "file_type": row.file_type,
                        "chunk_count": row.chunk_count or 0,
                        "chunks": row.chunk_contents or []
                    })
                return documents
            
        except Exception as e:
            logger.error(f"Error fetching document content: {e}")
            raise
    
    def _generate_summary_from_documents(
        self,
        documents: List[Dict],
        collection_name: str
    ) -> str:
        """
        Generate comprehensive summary from documents.
        
        Uses intelligent sampling to handle large collections.
        """
        try:
            # Build context from all documents
            context_parts = []
            total_tokens = 0
            max_tokens = self.max_context_tokens - self.max_summary_tokens - 1000  # Reserve for prompt
            
            # Calculate tokens per document (fair distribution)
            tokens_per_doc = max_tokens // len(documents) if documents else 0
            
            for doc in documents:
                doc_name = doc['file_name']
                doc_type = doc['file_type']
                chunks = doc['chunks']
                
                if not chunks:
                    continue
                
                # Sample chunks from this document
                sampled_content = self._sample_chunks(
                    chunks,
                    max_tokens=tokens_per_doc
                )
                
                context_parts.append(f"### Source: {doc_name} ({doc_type})\n{sampled_content}")
            
            combined_context = "\n\n".join(context_parts)
            
            # Generate summary using GPT
            prompt = f"""You are analyzing a collection of documents titled "{collection_name}".

Below are excerpts from all {len(documents)} documents in this collection:

{combined_context}

Generate a comprehensive summary that:
1. Provides a high-level overview of what these documents cover
2. Identifies main themes and topics across all sources
3. Highlights key concepts and important information
4. Maintains an objective, informative tone
5. Is 2-3 paragraphs long

Write the summary as if introducing someone to this collection of materials. Focus on breadth - cover what the collection as a whole contains, not just one document.

Summary:"""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that creates comprehensive summaries of document collections. You focus on identifying overarching themes and key concepts across multiple sources."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=self.max_summary_tokens
            )
            
            summary = response.choices[0].message.content.strip()
            
            logger.info(f"✅ Generated summary ({len(summary)} chars)")
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary from documents: {e}")
            raise
    
    def _sample_chunks(self, chunks: List[str], max_tokens: int) -> str:
        """
        Intelligently sample chunks to stay within token limit.
        
        Strategy:
        - If total content fits, use all
        - Otherwise, sample evenly from beginning, middle, end
        """
        if not chunks:
            return ""
        
        # Estimate total size
        total_chars = sum(len(chunk) for chunk in chunks)
        max_chars = max_tokens * self.chars_per_token
        
        # If everything fits, use it all
        if total_chars <= max_chars:
            return "\n\n".join(chunks)
        
        # Otherwise, sample strategically
        # Take from beginning, middle, and end
        sample_size = max(1, len(chunks) // 3)
        
        beginning = chunks[:sample_size]
        middle_start = len(chunks) // 2 - sample_size // 2
        middle = chunks[middle_start:middle_start + sample_size]
        end = chunks[-sample_size:]
        
        sampled = beginning + middle + end
        
        # Join and truncate if needed
        combined = "\n\n".join(sampled)
        
        if len(combined) > max_chars:
            combined = combined[:max_chars] + "..."
        
        return combined
    
    def delete_summary(self, collection_id: str):
        """
        Delete summary for a collection (e.g., when collection is deleted).
        """
        try:
            self.db.execute(text("""
                UPDATE collections
                SET 
                    summary = NULL,
                    summary_generated_at = NULL,
                    summary_source_count = 0
                WHERE id = :cid
            """), {"cid": collection_id})
            
            self.db.commit()
            logger.info(f"✅ Summary deleted for collection {collection_id}")
            
        except Exception as e:
            logger.error(f"Error deleting summary: {e}")
            self.db.rollback()
            raise
    
    def trigger_summary_update(self, collection_id: str, user_id: str):
        """
        Trigger summary update asynchronously (can be called after upload).
        
        This is the hook that gets called when a new source is added.
        """
        try:
            logger.info(f"🔄 Triggering summary update for collection {collection_id}")
            
            # Generate summary (this will overwrite existing one)
            self.generate_collection_summary(
                collection_id=collection_id,
                user_id=user_id,
                force_regenerate=True
            )
            
            logger.info(f"✅ Summary updated for collection {collection_id}")
            
        except Exception as e:
            logger.error(f"❌ Error triggering summary update: {e}")
            # Don't raise - summary update failure shouldn't break upload