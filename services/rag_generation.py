import logging
from typing import List, Dict, Any, Optional, Tuple, AsyncGenerator
from dataclasses import dataclass
from sqlalchemy import text
import json
from services.metrics import track_external_service_failure
from services.reranker import FlashRankReranker
from services.embedding_generator import EmbeddingGenerator
from services.model_manager import get_model_manager
from dotenv import load_dotenv
from services.chat_history_service import fetch_recent_chat_history
from services.hybrid_search import search_chunks_hybrid
from context_builder import build_diverse_context, map_reduce_extractions
import re


load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class RAGResult:
    query: str
    response: str
    sources_used: List[Dict[str, Any]]
    retrieval_count: int
    follow_up_questions: Optional[List[str]] = None  # ✅ ADDED from file 2
    generation_tokens: Optional[int] = None
    provider_used: Optional[str] = None  # Track which provider was used

    def get_citation_summary(self) -> str:
        """Generate a human-readable summary of sources cited"""
        if not self.sources_used:
            return "No sources cited"
        source_summary = []
        for source in self.sources_used:
            source_info = f"• {source.get('source_file', 'Unknown')} ({source.get('source_type', 'unknown')})"
            if source.get('pages'):
                pages = source['pages']
                if len(pages) == 1:
                    source_info += f" - Page {pages[0]}"
                else:
                    source_info += f" - Pages {', '.join(map(str, pages))}"
            source_summary.append(source_info)
        return "\n".join(source_summary)


def calculate_dynamic_rerank_limit(
    top_k: int,
    min_rerank: int = 5,
    max_rerank: int = 40
) -> int:
    """
    Calculate dynamic reranking limit based on retrieval size.
    
    Strategy: Scale reranking with how many chunks were retrieved.
    
    Args:
        top_k: Number of chunks retrieved from database
        min_rerank: Minimum chunks to keep (default: 5)
        max_rerank: Maximum chunks to keep (default: 40)
        
    Returns:
        Number of chunks to keep after reranking
        
    Examples:
        >>> calculate_dynamic_rerank_limit(10)
        10  # Keep all (small retrieval)
        
        >>> calculate_dynamic_rerank_limit(20)
        12  # Keep 60%
        
        >>> calculate_dynamic_rerank_limit(50)
        20  # Keep 40% (capped)
    """
    
    if top_k <= 10:
        # Small retrieval: keep everything
        rerank_n = top_k
        
    elif top_k <= 20:
        # Medium retrieval: keep 60-80%
        rerank_n = int(top_k * 0.9)
        
    else:
        # Large retrieval: keep 30-50%
        rerank_n = int(top_k * 0.9)
    
    # Apply bounds
    rerank_n = max(min_rerank, min(rerank_n, max_rerank))
    
    # Don't return more than what we have
    rerank_n = min(rerank_n, top_k)
    
    return rerank_n


class RAGGenerator:
    """
    Combined RAG Generator with:
    - Dynamic model management (OpenAI/Anthropic fallback)
    - Advanced citation handling with file-level grouping
    - YouTube metadata support
    - Document filtering for focused retrieval
    - Summary generation capabilities
    - Memory layer integration
    - Dynamic reranking limits (scales with retrieval size)
    - Follow-up question generation
    - Reference mapping for citations
    """
    
    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        db,
        config_path: str = "config.yaml",
        memory_layer: Optional[Any] = None
    ):
        self.embedding_generator = embedding_generator
        self.db = db
        self.memory_layer = memory_layer
        self.model_manager = get_model_manager(config_path)
        self.rag_config = self.model_manager.config.get('rag_config', {})
        self.enable_hybrid_search = self.rag_config.get('enable_hybrid_search', False)
        self.hybrid_weights = self.rag_config.get('hybrid_weights', {'semantic': 0.6, 'keyword': 0.4})
        
        # ✅ ADD THIS
        try:
            self.reranker = FlashRankReranker()
            self.use_reranking = True
        except Exception as e:
            logger.warning(f"Reranker disabled: {e}")
            self.use_reranking = False
    
        # self.top_k = self.rag_config.get('top_k', 10)
        self.enable_document_filtering = self.rag_config.get('enable_document_filtering', False)
        
        logger.info(f"RAG Generator initialized with provider: {self.model_manager.get_current_llm_provider()}")
        # logger.info(f"RAG Config: max_chunks={self.max_chunks}, max_context={self.max_context_chars}, top_k={self.top_k}")
        logger.info(f"Document filtering: {'enabled' if self.enable_document_filtering else 'disabled'}")
    
    
    def _search_chunks(
    self,
    query_text: str,  # ✅ ADD THIS (raw query string)
    query_vector: List[float],
    user_id: str,
    collection_id: str,
    limit: int = 10,
    selected_document_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
        if limit == 0:
            logger.info("Skipping chunk search because limit is 0.")
            return []
        """
        Search chunks - can use hybrid (BM25+Vector) or semantic-only.
        Fallback gracefully if hybrid fails.
        """
        try:
            # ✅ IF HYBRID ENABLED, TRY IT FIRST
            if self.enable_hybrid_search:
                try:
                    logger.info("🔍 Using HYBRID search (BM25 + Vector)")
                    search_results = search_chunks_hybrid(
                        db=self.db,
                        query_text=query_text,  # ✅ Pass raw query
                        query_vector=query_vector,
                        user_id=user_id,
                        collection_id=collection_id,
                        limit=limit,
                        selected_document_ids=selected_document_ids,
                        semantic_weight=self.hybrid_weights.get('semantic', 0.6),
                        keyword_weight=self.hybrid_weights.get('keyword', 0.4)
                    )
                    logger.info(f"✅ Hybrid search returned {len(search_results)} results")
                    return search_results
                except Exception as hybrid_error:
                    logger.warning(f"⚠️ Hybrid search failed, falling back to semantic: {hybrid_error}")
                    # Fall through to semantic-only below
            
            # ✅ SEMANTIC-ONLY FALLBACK (original code)
            if self.db.bind.dialect.name == "sqlite":
                from services.hybrid_search import _search_semantic
                logger.info("🔍 Using SQLite fallback semantic search")
                return _search_semantic(
                    db=self.db,
                    query_vector=query_vector,
                    user_id=user_id,
                    collection_id=collection_id,
                    limit=limit,
                    selected_document_ids=selected_document_ids
                )

            vector_str = f"[{','.join(map(str, query_vector))}]"

            doc_filter_sql = ""
            params = {
                "query_vector": vector_str,
                "uid": user_id,
                "cid": collection_id,
                "limit": limit
            }

            if selected_document_ids:
                doc_filter_sql = """
                    AND c.document_id = ANY(
                        ARRAY(SELECT UNNEST(:doc_ids))::uuid[]
                    )
                """
                params["doc_ids"] = selected_document_ids

            result = self.db.execute(text(f"""
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
            search_results = []

            for row in rows:
                source_file = row.source_file

                if not source_file and row.document_id:
                    doc_result = self.db.execute(text("""
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

                search_results.append({
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

            logger.info(f"Found {len(search_results)} chunks (semantic-only)")
            return search_results

        except Exception as e:
            logger.error(f"Error searching chunks: {str(e)}")
            raise

    
    def build_chat_history_block(
        self,
        chat_rows: List[Dict[str, Any]],
        max_turns: int = 3
    ) -> str:
        """
        Build an ordered chat history block for prompt injection.
        Oldest → newest, clearly labeled.
        """
        if not chat_rows:
            return ""

        recent = chat_rows[-max_turns:]

        lines = []
        for i, row in enumerate(recent, start=1):
            q = row.get("query_text")
            q = q.strip() if isinstance(q, str) else ""

            a = row.get("response_text")
            a = a.strip() if isinstance(a, str) else ""

            if not q and not a:
                continue

            lines.append(f"Turn {i} — User:\n{q}")
            lines.append(f"Turn {i} — Assistant:\n{a}")

        return "\n\n".join(lines)

    def _filter_to_best_document(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter search results to keep only chunks from the most relevant document.
        This improves focus by avoiding mixing content from multiple documents.
        
        Args:
            search_results: List of search results
            
        Returns:
            Filtered list containing only chunks from the best document
        """
        if not search_results or not self.enable_document_filtering:
            return search_results
        
        # Group chunks by source file
        doc_groups = {}
        for result in search_results:
            source_file = result["citation"]["source_file"]
            doc_groups.setdefault(source_file, []).append(result)
        
        # Find document with highest cumulative relevance score
        best_doc_chunks = max(
            doc_groups.values(),
            key=lambda group: sum(
                1.0 / (1.0 + item["score"]) for item in group if item["score"] is not None
            )
        )
        
        logger.info(f"Filtered to best document with {len(best_doc_chunks)} chunks")
        return best_doc_chunks
    
    def _format_timestamp(self, seconds: float) -> str:
        """
        Convert seconds to HH:MM:SS or MM:SS format for YouTube timestamps.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Formatted timestamp string
        """
        if seconds is None:
            return "0:00"
        
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"
    
    def _format_context_with_citations(
        self,
        search_results: List[Dict[str, Any]]
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:  # ✅ ADDED reference_map to return type
        """
        Format search results into context with citation references and group sources by file.
        This advanced version:
        - Groups sources by file (not by individual chunks/pages)
        - Handles YouTube metadata (timestamps, speakers, video URLs)
        - Creates clickable timestamp links for YouTube content
        - Maintains all chunk references for granular tracking
        - Returns reference map for citation tracking
        
        Args:
            search_results: List of search results with content and metadata
            
        Returns:
            Tuple of (formatted_context, grouped_sources_info, reference_map)
        """
        context_parts = []
        raw_sources_info = []
        total_chars = 0
        reference_map = {}  # ✅ ADDED from file 2

        # ===================================================================
        # STEP 1: BUILD CONTEXT AND COLLECT RAW SOURCES (one per chunk)
        # ===================================================================
        for i, result in enumerate(search_results):
            citation_info = result.get('citation', {}) if isinstance(result, dict) else {}
            metadata = citation_info.get('metadata', {}) or {}

            source_file = citation_info.get('source_file', 'Unknown Source')
            source_type = citation_info.get('source_type', 'unknown')
            page_number = citation_info.get('page_number')

            citation_ref = f"[{i+1}]"
            chunk_content = result.get('content')

            if not isinstance(chunk_content, str):
                chunk_content = ""

            chunk_text = f"{citation_ref} {chunk_content}"
            
            # ✅ ADDED reference_map building from file 2
            reference_map[citation_ref] = {
                "text": chunk_content,
                "source_file": source_file,
                "source_type": source_type,
                "page_number": page_number,
                "chunk_id": str(result.get("id")),
                "start_char": citation_info.get("start_char"),
                "end_char": citation_info.get("end_char")
            }

            # # Enforce max context size
            # if total_chars + len(chunk_text) > max_context_chars and context_parts:
            #     break

            context_parts.append(chunk_text)
            total_chars += len(chunk_text)

            # Base source info for this chunk
            source_info = {
                "reference": citation_ref,
                "source_file": source_file,
                "source_type": source_type,
                "page_number": page_number,
                "chunk_id": str(result.get("id")) if isinstance(result, dict) else None,
                "relevance_score": result.get("score")
            }

            # ===================================================================
            # YOUTUBE METADATA HANDLING
            # ===================================================================
            if source_type == 'youtube' and metadata:
                start_time = metadata.get('start_timestamp')
                end_time = metadata.get('end_timestamp')
                video_url = metadata.get('video_url')
                video_id = metadata.get('video_id')
                speakers = metadata.get('speakers', [])

                if start_time is not None:
                    source_info["start_timestamp"] = start_time
                    source_info["end_timestamp"] = end_time
                    source_info["timestamp_display"] = self._format_timestamp(start_time)
                    source_info["speakers"] = speakers

                    # Create clickable YouTube URL with timestamp
                    if video_url:
                        start_seconds = int(start_time)
                        if "?" in video_url:
                            source_info["timestamp_url"] = f"{video_url}&t={start_seconds}s"
                        else:
                            source_info["timestamp_url"] = f"{video_url}?t={start_seconds}s"

                    if video_id:
                        source_info["video_id"] = video_id
                    
                    if video_url:
                        source_info["source_url"] = video_url

            raw_sources_info.append(source_info)
            raw_sources_info = [
                s for s in raw_sources_info
                if s.get("source_type") not in ("memory", "mem")
                and not str(s.get("source_file", "")).startswith("memory")
                and not str(s.get("chunk_id", "")).startswith("memory")
            ]

        formatted_context = "\n\n".join(context_parts)

        # ===================================================================
        # STEP 2: GROUP SOURCES BY FILE (NOT BY PAGE OR CHUNK)
        # ===================================================================
        grouped_sources = {}

        for src in raw_sources_info:
            key = (src["source_file"], src["source_type"])

            if key not in grouped_sources:
                grouped_sources[key] = {
                    "source_file": src["source_file"],
                    "source_type": src["source_type"],
                    "pages": set(),
                    "references": [],
                    "chunk_ids": [],
                    "relevance_scores": [],
                    "youtube_details": [],
                    "source_url": None
                }

            # Collect PDF/Web pages
            if src.get("page_number") is not None:
                grouped_sources[key]["pages"].add(src["page_number"])

            grouped_sources[key]["references"].append(src["reference"])
            grouped_sources[key]["chunk_ids"].append(src["chunk_id"])
            grouped_sources[key]["relevance_scores"].append(src["relevance_score"])

            # Collect YouTube fields if present
            if src["source_type"] == "youtube":
                youtube_detail = {
                    "start_timestamp": src.get("start_timestamp"),
                    "end_timestamp": src.get("end_timestamp"),
                    "timestamp_display": src.get("timestamp_display"),
                    "timestamp_url": src.get("timestamp_url"),
                    "video_id": src.get("video_id"),
                    "speakers": src.get("speakers")
                }
                # Only add if it has meaningful data
                if youtube_detail["start_timestamp"] is not None:
                    grouped_sources[key]["youtube_details"].append(youtube_detail)
                
                if src.get("source_url") and not grouped_sources[key]["source_url"]:
                    grouped_sources[key]["source_url"] = src.get("source_url")

        # ===================================================================
        # STEP 3: BUILD FINAL UNIQUE SOURCE LIST
        # ===================================================================
        deduped_sources = []
        for key, value in grouped_sources.items():
            source_entry = {
                "source_file": value["source_file"],
                "source_type": value["source_type"],
                "pages": sorted(list(value["pages"])) if value["pages"] else None,
                "references": value["references"],
                "chunk_ids": value["chunk_ids"],
                "relevance_scores": value["relevance_scores"]
            }
            
            # Add YouTube details only if present
            if value["source_type"] == "youtube" and value["youtube_details"]:
                source_entry["youtube_details"] = value["youtube_details"]
            
            if value.get("source_url"):
                source_entry["source_url"] = value["source_url"]
            
            deduped_sources.append(source_entry)

        return formatted_context, deduped_sources, reference_map  # ✅ ADDED reference_map to return

    def _strip_follow_up_block(self, text: str) -> str:
        """
        Remove the FOLLOW_UP_QUESTIONS block from response text.
        ✅ ADDED from file 2
        """
        if not text:
            return text

        # Remove inline or multiline FOLLOW_UP_QUESTIONS block
        text = re.sub(
            r'\s*<FOLLOW_UP_QUESTIONS>\s*\[[\s\S]*?\]\s*</FOLLOW_UP_QUESTIONS>\s*',
            '',
            text,
            flags=re.IGNORECASE
        )

        return text.strip()

        
    def _create_rag_prompt(
            self,
            query: str,
            context: str,
            memory_context: str = "",
            chat_history_text: str = "",
            response_language: str = "English",
            conversational_style: str = "default",
            chat_length: str = "default"
        ) -> str:
        """
        Create production-grade RAG prompt optimized for comprehensive, well-structured responses.
        ✅ UPDATED with follow-up question generation from file 2
        
        Args:
            query: User's question
            context: Retrieved context with citation references
            memory_context: Previous conversation context (optional)
            chat_history_text: Recent chat history (optional)
            
        Returns:
            Formatted prompt string
        """
        # -----------------------------------
        # CONVERSATION STYLE CONTROL
        # -----------------------------------
        DEFAULT_STYLE = "Professional, neutral, and helpful."

        raw_style = (conversational_style or "").strip()

        if not raw_style or raw_style.lower() == "default":
            style_instruction = DEFAULT_STYLE
        else:
            # Safety guard: prevent runaway instructions
            style_instruction = raw_style[:200]

        # -----------------------------------
        # RESPONSE LENGTH CONTROL
        # -----------------------------------
        length_map = {
            "short": "Keep the response concise.It must be like a summary of the response. Avoid unnecessary explanations.",
            "default": "Provide a balanced level of detail with clear structure and explanations.",
            "long": "Provide a highly detailed, in-depth response with full explanations, examples, and structured sections."
        }

        length_instruction = length_map.get(
            (chat_length or "default").lower(),
            length_map["default"]
        )

        # Memory section
        memory_section = ""
        if memory_context and memory_context.strip():
            memory_section = f"""
    CONVERSATION MEMORY (do NOT cite this in your answer):
    The following text summarizes earlier messages from the user.
    Use it ONLY to interpret the current question.
    Do NOT treat it as a factual source and do NOT cite it:

    {memory_context}

    """
        
        # Chat history section
        chat_history_section = ""
        if chat_history_text and chat_history_text.strip():
            chat_history_section = f"""
    CHAT HISTORY (do NOT cite this in your answer):
    The following are the most recent conversation turns, ordered from OLDEST to MOST RECENT.
    Use this to:
    - Resolve vague or underspecified questions
    - Understand what the user is referring to
    - Maintain conversational continuity

    Do NOT treat this as a factual source.
    Do NOT cite this section.

    {chat_history_text}
    """
        
        # Check if query is a summary request (Phase 10)
        is_summary = any(w in query.lower() for w in ["summarize", "summary", "overview", "key points", "key findings"])
        
        if is_summary:
            prompt = f"""You are an expert analyst. Your task is to generate a comprehensive, well-structured summary of the provided document content.

    Before writing, read the entire CONTEXT carefully and:
    1. Identify the document's main topic, type, and purpose.
    2. Extract all key sections, concepts, and entities mentioned.
    3. Structure the summary around what is ACTUALLY in the document — do NOT impose a fixed template.

    SUMMARY RULES:
    - Base your summary ENTIRELY on the CONTEXT provided below.
    - Do NOT assume the document is about RAG, architectures, or any specific topic unless it is explicitly in the context.
    - Use headings and bullet points to organize the actual content found.
    - Cite EVERY factual claim with [1], [2], [3] etc. placed immediately after the statement.
    - Writing style: {style_instruction}
    - Do NOT add a "References" section. Only cite from the CONTEXT block below.

    LANGUAGE REQUIREMENT (MANDATORY):
    - Generate the entire response in {response_language}
    - Do NOT use any other language

    {chat_history_section}

    {memory_section}

    CONTEXT (with citation references):
    {context}

    QUESTION:
    {query}

    Provide a complete, well-structured summary grounded strictly in the context above.

    FOLLOW-UP QUESTION RULES:
    - Base them ONLY on the question and the provided context
    - Do NOT introduce new topics
    - Do NOT repeat the original question
    - Do NOT ask yes/no questions
    - Keep each question under 15 words
    - Generate at most 3 questions

    OUTPUT FORMAT (MANDATORY):
    - DO NOT include headings, markdown, or explanatory text around the follow-up questions
    - Output ONLY valid JSON inside the FOLLOW_UP_QUESTIONS tags

    <FOLLOW_UP_QUESTIONS>
    [
    "Question 1?",
    "Question 2?",
    "Question 3?"
    ]
    </FOLLOW_UP_QUESTIONS>
    """
        else:
            prompt = f"""You are an expert AI assistant that provides thorough, well-researched answers based on source documents.
    
        LANGUAGE REQUIREMENT (MANDATORY):
        - Generate the entire response in {response_language}
        - Do NOT use any other language
        - Do NOT explain or mention the language choice
    
        RESPONSE GUIDELINES:
        1. THOROUGHNESS: Provide comprehensive answers that fully address the question
        - Include ALL relevant information from the context
        - Don't omit important details, dates, names, or action items
        - If multiple sources discuss the topic, synthesize all perspectives
        - Cover the topic in appropriate depth based on available information
    
        2. STRUCTURE & FORMATTING:
        - Use clear organization with logical flow
        - Use markdown headers (##, ###) for main topics and subtopics
        - Use bullet points (•) or numbered lists (1., 2., 3.) for multiple items
        - Use tables for comparative or structured data when appropriate
        - Use **bold** to highlight the key words that are in the response.
        - Ensure readability with proper spacing and sections
    
        3. ACCURACY & CITATIONS (MANDATORY):
        - Cite EVERY factual claim with [1], [2], [3] etc.
        - Place citations immediately after the statement: "The meeting was held on June 27 [3]."
        - For multiple supporting sources, list all: "This was confirmed [1], [2], [3]."
        - Do NOT add a "References" section
        - Only cite from the CONTEXT block below
        - If information is not in the context, explicitly state: "The provided documents do not contain information about..."
    
        4. COMPLETENESS:
        - Answer all parts of multi-part questions
        - Provide context and background when helpful
        - Include relevant examples, specifics, and supporting details
        - Don't just list items - explain them when context allows
    
        5. PROFESSIONALISM & STYLE:
        - Writing style must follow this tone: {style_instruction}
        - Response length guideline: {length_instruction}
        - Maintain clarity, accuracy, and logical structure
        - Make responses easy to scan and understand
    
    
        {chat_history_section}
    
        {memory_section}
    
        CONTEXT (with citation references):
        {context}
    
        QUESTION:
        {query}
    
        Provide a complete, well-structured answer with proper citations for every factual claim.
    
        FOLLOW-UP QUESTION RULES:
        - Base them ONLY on the question and the provided context
        - Do NOT introduce new topics
        - Do NOT repeat the original question
        - Do NOT ask yes/no questions
        - Keep each question under 15 words
        - Generate at most 3 questions
    
        OUTPUT FORMAT (MANDATORY):
        - DO NOT include headings, markdown, or explanatory text around the follow-up questions
        - Output ONLY valid JSON inside the FOLLOW_UP_QUESTIONS tags
    
        <FOLLOW_UP_QUESTIONS>
        [
        "Question 1?",
        "Question 2?",
        "Question 3?"
        ]
        </FOLLOW_UP_QUESTIONS>
        """
        
        return prompt
   
 
    
    def generate_response(
        self,
        query: str,
        top_k: Optional[int] = None,  # ✅ Keep only this
        user_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        selected_document_ids: Optional[List[str]] = None,  # ✅ NEW
        memory_chunks: Optional[List[Dict[str, Any]]] = None,
        memory_context: str = "",
        response_language: str = "English",
        conversational_style: str = "default",  # ✅ ADD
        chat_length: str = "default"            # ✅ ADD
        
    ) -> RAGResult:
        """
        Generate a non-streaming response to a query using RAG.
        ✅ UPDATED with follow-up question extraction from file 2
        
        Args:
            query: User's question
            top_k: Number of chunks to retrieve (defaults to config)
            user_id: User ID for filtering
            collection_id: Collection ID for filtering
            memory_chunks: Previously relevant chunks from memory
            memory_context: Previous conversation context
            
        Returns:
            RAGResult with response, sources, and metadata
        """
        # Use provided values or defaults from config
        if top_k is None:
            top_k = 10
        
        if not query.strip():
            return RAGResult(
                query=query,
                response="Please provide a valid question.",
                sources_used=[],
                retrieval_count=0,
                provider_used=self.model_manager.get_current_llm_provider()
            )
        
        try:
            logger.info(f"Generating response for: '{query[:50]}...'")
            
            if top_k == 0:
                # Direct generation without any retrieval; treat the query as the full prompt.
                messages = [{"role": "user", "content": query}]
                completion = self.model_manager.get_chat_completion(messages=messages, stream=False)
                if hasattr(completion, "choices"):
                    response_text = completion.choices[0].message.content
                else:
                    response_text = str(completion)
                return RAGResult(
                    query=query,
                    response=response_text,
                    sources_used=[],
                    retrieval_count=0,
                    provider_used=self.model_manager.get_current_llm_provider(),
                )

            # Generate query embedding
            query_vector = self.embedding_generator.generate_query_embedding(query)
            
            # If it is a summary request or if we want to ensure high coverage, increase retrieval limit (Phase 9)
            is_summary = any(w in query.lower() for w in ["summarize", "summary", "overview", "key points", "key findings"])
            actual_limit = 200 if is_summary else top_k




            search_results = self._search_chunks(
                query_text=query,
                query_vector=query_vector.tolist(),
                user_id=user_id,
                collection_id=collection_id,
                limit=actual_limit,
                selected_document_ids=selected_document_ids
            )

            # Apply BGE Reranker v2 (Phase 8) in non-streaming flow too
            if self.use_reranking and search_results and not is_summary:
                rerank_n = calculate_dynamic_rerank_limit(
                    top_k=len(search_results),
                    min_rerank=5,
                    max_rerank=40
                )
                search_results = self.reranker.rerank(
                    query=query,
                    documents=search_results,
                    top_n=rerank_n
                )

            # Apply document filtering if enabled
            search_results = self._filter_to_best_document(search_results)
            
            if not search_results:
                return RAGResult(
                    query=query,
                    response="I couldn't find any relevant information in the available documents to answer your question.",
                    sources_used=[],
                    retrieval_count=0,
                    provider_used=self.model_manager.get_current_llm_provider()
                )

            # If this is a summary request, use Map‑Reduce flow
            if is_summary:
                return map_reduce_extractions(
                    rag_generator=self,
                    query=query,
                    chunks=search_results,
                    batch_size=5
                )

            # Build diverse context (Phase 9)
            diverse_chunks = build_diverse_context(
                chunks=search_results,
                max_context_chars=16000
            )

            # Combine with memory chunks
            results_to_use = (memory_chunks or []) + diverse_chunks

            # Format context with advanced citation handling
            context, sources_info, reference_map = self._format_context_with_citations(
                results_to_use
            )
            
            chat_rows = fetch_recent_chat_history(
                db=self.db,
                user_id=user_id,
                collection_id=collection_id,
                limit=3
            )

            chat_history_text = self.build_chat_history_block(chat_rows)

            # Create prompt with memory context
            prompt = self._create_rag_prompt(
                        query=query,
                        context=context,
                        memory_context=memory_context,
                        chat_history_text=chat_history_text,
                        response_language=response_language,
                        conversational_style=conversational_style,
                        chat_length=chat_length
                    )

            # Use ModelManager for completion with fallback
            messages = [{"role": "user", "content": prompt}]
            completion = self.model_manager.get_chat_completion(
                messages=messages,
                stream=False
            )
            
            # Extract response
            if hasattr(completion, 'choices'):
                response = completion.choices[0].message.content
            else:
                response = str(completion)

            # ✅ ADDED follow-up question extraction from file 2
            follow_up_questions = []
            match = re.search(
                r'<FOLLOW_UP_QUESTIONS>(.*?)</FOLLOW_UP_QUESTIONS>',
                response,
                re.DOTALL
            )

            if match:
                try:
                    follow_up_questions = json.loads(match.group(1).strip())

                    # 🔥 REMOVE FOLLOW-UP TAG + ANY ADJACENT TEXT
                    response = re.sub(
                        r'###\s*Follow-Up Questions[\s\S]*?<FOLLOW_UP_QUESTIONS>[\s\S]*?</FOLLOW_UP_QUESTIONS>',
                        '',
                        response,
                        flags=re.IGNORECASE
                    ).strip()

                    # 🔥 Fallback: remove tag block if no heading exists
                    response = re.sub(
                        r'<FOLLOW_UP_QUESTIONS>[\s\S]*?</FOLLOW_UP_QUESTIONS>',
                        '',
                        response,
                        flags=re.IGNORECASE
                    ).strip()

                except Exception as e:
                    logger.warning(f"Failed to parse follow-up questions: {e}")

            # Save to memory if available
            if self.memory_layer and response and len(response) > 50:
                try:
                    self.memory_layer.save_semantic_memory(
                        user_query=query, 
                        assistant_response=response, 
                        sources_used=sources_info
                    )
                except Exception as e:
                    logger.warning(f"Failed to save memory: {e}")

            return RAGResult(
                query=query,
                response=response,
                sources_used=sources_info,
                retrieval_count=len(results_to_use),
                follow_up_questions=follow_up_questions,  # ✅ ADDED
                provider_used=self.model_manager.get_current_llm_provider()
            )

        except Exception as e:
            track_external_service_failure("llm")
            logger.error(f"Error generating response: {str(e)}")
            return RAGResult(
                query=query,
                response=f"I encountered an error while processing your question: {str(e)}",
                sources_used=[],
                retrieval_count=0,
                provider_used=self.model_manager.get_current_llm_provider()
            )
        
    async def generate_response_stream(
        self,
        query: str,
        memory_context: str = "",
        top_k: Optional[int] = None,  # ✅ Keep only this
        include_complete_response: bool = True,
        user_id: Optional[str] = None,
        selected_document_ids: Optional[List[str]] = None,  # ✅ NEW
        collection_id: Optional[str] = None,
        memory_chunks: Optional[List[Dict[str, Any]]] = None,
        response_language: str = "English",
        conversational_style: str = "default",  # ✅ ADD
        chat_length: str = "default"            # ✅ ADD
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generate a streaming response to a query using RAG.
        ✅ UPDATED with follow-up question streaming from file 2
        
        Args:
            query: User's question
            memory_context: Previous conversation context
            top_k: Number of chunks to retrieve (defaults to config)
            include_complete_response: Whether to yield complete response at end
            user_id: User ID for filtering
            collection_id: Collection ID for filtering
            memory_chunks: Previously relevant chunks from memory
            
        Yields:
            Dictionary with type and content/metadata
        """
        # Use provided values or defaults from config
        top_k = top_k or 10
        
        streamed_response = ""   # 🔴 raw LLM output
        clean_response = ""      # ✅ persisted version
        used_sources = [] 
        
        if not query.strip():
            yield {"type": "chunk", "content": "Please provide a valid question."}
            yield {
                "type": "done",
                "sources_used": [],
                "retrieval_count": 0,
                "provider_used": self.model_manager.get_current_llm_provider()
            }
            return
        
        try:
            logger.info(f"Streaming response for: '{query[:50]}...'")


            # Generate query embedding with fallback
            query_vector = self.embedding_generator.generate_query_embedding(query)

            # Search chunks (get 10)
            # If it is a summary request or if we want to ensure high coverage, increase retrieval limit (Phase 9)
            is_summary = any(w in query.lower() for w in ["summarize", "summary", "overview", "key points", "key findings"])
            actual_limit = 200 if is_summary else top_k

            search_results = self._search_chunks(
                query_text=query,
                query_vector=query_vector.tolist(), 
                user_id=user_id, 
                collection_id=collection_id, 
                selected_document_ids=selected_document_ids,
                limit=actual_limit
            )

            # Apply BGE Reranker v2 (Phase 8)
            if self.use_reranking and search_results and not is_summary:
                rerank_n = calculate_dynamic_rerank_limit(
                    top_k=len(search_results),
                    min_rerank=5,
                    max_rerank=40
                )
                search_results = self.reranker.rerank(
                    query=query,
                    documents=search_results,
                    top_n=rerank_n
                )
            
            # Apply document filtering if enabled
            search_results = self._filter_to_best_document(search_results)
            
            if not search_results:
                msg = "I couldn't find any relevant information in the available documents to answer your question."
                yield {"type": "chunk", "content": msg}
                yield {
                    "type": "done",
                    "sources_used": [],
                    "retrieval_count": 0,
                    "provider_used": self.model_manager.get_current_llm_provider()
                }
                if include_complete_response:
                    yield {
                        "type": "complete_response",
                        "response": msg,
                        "sources_used": [],
                        "retrieval_count": 0,
                        "provider_used": self.model_manager.get_current_llm_provider()
                    }
                return

            # If this is a summary request, run Map-Reduce flow in streaming mode
            if is_summary:
                map_reduce_result = map_reduce_extractions(
                    rag_generator=self,
                    query=query,
                    chunks=search_results,
                    batch_size=5
                )
                response_text = map_reduce_result.response
                words = re.split(r'(\s+)', response_text)
                for word in words:
                    yield {"type": "chunk", "content": word}
                yield {
                    "type": "sources",
                    "sources_used": [],
                    "reference_map": {}
                }
                yield {
                    "type": "done",
                    "sources_used": [],
                    "retrieval_count": len(search_results),
                    "provider_used": self.model_manager.get_current_llm_provider()
                }
                if include_complete_response:
                    yield {
                        "type": "complete_response",
                        "response": response_text,
                        "sources_used": [],
                        "retrieval_count": len(search_results),
                        "provider_used": self.model_manager.get_current_llm_provider()
                    }
                return

            # Build diverse context (Phase 9)
            diverse_chunks = build_diverse_context(
                chunks=search_results,
                max_context_chars=16000
            )
            
            # Combine with memory chunks
            results_to_use = (memory_chunks or []) + diverse_chunks
            
            # Format context with advanced citation handling
            context, sources_info, reference_map = self._format_context_with_citations(
                results_to_use
            )
            
            chat_rows = fetch_recent_chat_history(
                db=self.db,
                user_id=user_id,
                collection_id=collection_id,
                limit=3
            )

            chat_history_text = self.build_chat_history_block(chat_rows)

            # Create prompt with memory context
            prompt = self._create_rag_prompt(
                query=query,
                context=context,
                memory_context=memory_context,
                chat_history_text=chat_history_text,
                response_language=response_language,
                conversational_style=conversational_style,
                chat_length=chat_length
            )

            # Stream response using ModelManager
            messages = [{"role": "user", "content": prompt}]
            
            stream = self.model_manager.get_chat_completion(
                messages=messages,
                stream=True
            )
            
            # Stream chunks
            for chunk in stream:
                if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    content = delta.content if hasattr(delta, 'content') else ""
                elif hasattr(chunk, 'content'):
                    content = chunk.content
                else:
                    content = ""
                
                if content:
                    streamed_response += content
                    yield {"type": "chunk", "content": content}
            
            # ✅ ADDED follow-up question extraction
            follow_up_questions = []
            clean_response = self._strip_follow_up_block(streamed_response)

            match = re.search(
                r'<FOLLOW_UP_QUESTIONS>(.*?)</FOLLOW_UP_QUESTIONS>',
                streamed_response,
                re.DOTALL
            )

            if match:
                try:
                    follow_up_questions = json.loads(match.group(1).strip())
                    clean_response = re.sub(
                        r'###\s*Follow-Up Questions[\s\S]*?<FOLLOW_UP_QUESTIONS>[\s\S]*?</FOLLOW_UP_QUESTIONS>',
                        '',
                        streamed_response,
                        flags=re.IGNORECASE
                    ).strip()
                except Exception as e:
                    logger.warning(f"Failed to parse follow-ups: {e}")

            # ✅ Send follow-ups separately
            if follow_up_questions:
                yield {
                    "type": "follow_up",
                    "questions": follow_up_questions
                }
            
            # 🚫 FINAL SAFETY FILTER — REMOVE ANY MEMORY SOURCES
            clean_sources = [
                s for s in sources_info
                if s.get("source_type") not in ("memory", "mem")
                and not str(s.get("source_file", "")).startswith("memory")
                and not any(str(cid).startswith("memory") for cid in s.get("chunk_ids", []))
            ]

            # Step 2: Extract citation numbers that LLM actually used: [1], [2], [3]
            citations_found = re.findall(r'\[(\d+)\]', streamed_response)
            citation_numbers = set(int(c) for c in citations_found)

            logger.info(f"📊 LLM cited {len(citation_numbers)} references: {sorted(citation_numbers)}")

            if citation_numbers and clean_sources:
                # ✅ Filter to only cited sources (existing logic)
                
                for source in clean_sources:
                    all_source_refs = source.get('references', [])
                    
                    all_ref_numbers = set()
                    for ref in all_source_refs:
                        try:
                            num = int(ref.strip('[]'))
                            all_ref_numbers.add(num)
                        except (ValueError, AttributeError):
                            continue
                    
                    cited_refs_nums = all_ref_numbers & citation_numbers
                    
                    if cited_refs_nums:
                        filtered_source = source.copy()
                        cited_refs_str = [f"[{num}]" for num in sorted(cited_refs_nums)]
                        filtered_source['references'] = cited_refs_str
                        
                        # Build mapping
                        ref_to_idx = {}
                        for idx, ref in enumerate(all_source_refs):
                            try:
                                num = int(ref.strip('[]'))
                                ref_to_idx[num] = idx
                            except:
                                continue
                        
                        cited_indices = [ref_to_idx[num] for num in cited_refs_nums if num in ref_to_idx]
                        cited_indices.sort()
                        
                        # Filter arrays
                        if 'chunk_ids' in filtered_source and filtered_source['chunk_ids']:
                            filtered_source['chunk_ids'] = [
                                filtered_source['chunk_ids'][i] 
                                for i in cited_indices 
                                if i < len(filtered_source['chunk_ids'])
                            ]
                        
                        if 'relevance_scores' in filtered_source and filtered_source['relevance_scores']:
                            filtered_source['relevance_scores'] = [
                                filtered_source['relevance_scores'][i] 
                                for i in cited_indices 
                                if i < len(filtered_source['relevance_scores'])
                            ]
                        
                        if 'youtube_details' in filtered_source and filtered_source['youtube_details']:
                            filtered_source['youtube_details'] = [
                                filtered_source['youtube_details'][i]
                                for i in cited_indices
                                if i < len(filtered_source['youtube_details'])
                            ]
                        
                        logger.info(
                            f"✅ {filtered_source['source_file']}: "
                            f"Filtered from {len(all_source_refs)} to {len(cited_refs_str)} refs"
                        )
                        
                        used_sources.append(filtered_source)
                
                logger.info(
                    f"📋 Final sources: {len(used_sources)}/{len(clean_sources)} files "
                    f"with {sum(len(s.get('references', [])) for s in used_sources)} total refs"
                )
    
                yield {
                    "type": "sources",
                    "sources_used": used_sources,
                    "reference_map": reference_map,
                    "retrieval_count": len(used_sources)
                }

            # ✅ ADD THIS NEW FALLBACK BLOCK
            elif clean_sources and not citation_numbers:
                # 🆕 FALLBACK: No citations found, but we retrieved sources
                # This happens with Excel/CSV data where LLM doesn't cite naturally
                logger.warning(
                    f"⚠️ No citations found in response, but {len(clean_sources)} sources were retrieved. "
                    f"Showing all sources (likely Excel/CSV or structured data)."
                )
                
                # Show all sources since LLM used the data but didn't cite
                used_sources = clean_sources
                
                yield {
                    "type": "sources",
                    "sources_used": used_sources,
                    "reference_map": reference_map,
                    "retrieval_count": len(used_sources)
                }

            else:
                # No sources retrieved at all
                logger.info(f"⚠️ No citations found or no sources - hiding all sources")
                yield {
                    "type": "sources",
                    "sources_used": used_sources,  # Will be []
                    "reference_map": {},
                    "retrieval_count": 0
                }

            # Ensure citations flush immediately to client
            import asyncio
            await asyncio.sleep(0)
            
            # Yield done
            yield {
                "type": "done",
                "provider_used": self.model_manager.get_current_llm_provider()
            }
            
            # Optionally yield complete response
            if include_complete_response:
                yield {
                    "type": "complete_response",
                    "response": clean_response,
                    "sources_used": used_sources,  # ✅ Now always defined
                    "retrieval_count": len(used_sources),
                    "provider_used": self.model_manager.get_current_llm_provider()
                }
                        
            # Save to memory (non-critical)
            if self.memory_layer and clean_response and len(clean_response) > 50:
                try:
                    self.memory_layer.save_semantic_memory(
                        user_query=query,
                        assistant_response=clean_response,
                        sources_used=sources_info
                    )
                except Exception as e:
                    logger.warning(f"Failed to persist memory after streaming (non-critical): {e}")
            
            logger.info(f"Streaming complete (sources used: {len(sources_info)})")
            
        except Exception as e:
            track_external_service_failure("llm")  # ✅ ADD THIS LINE
            logger.error(f"Error in streaming response: {str(e)}")
            yield {"type": "error", "content": f"Error: {str(e)}"}
    
    def generate_summary(
        self,
        max_chunks: int = 15,
        summary_length: str = "medium",
        user_id: Optional[str] = None,
        collection_id: Optional[str] = None
    ) -> RAGResult:
        """
        Generate a summary of documents in the collection.
        
        Args:
            max_chunks: Maximum chunks to use for summary
            summary_length: Length of summary ('short', 'medium', 'long')
            user_id: User ID for filtering
            collection_id: Collection ID for filtering
            
        Returns:
            RAGResult with summary and sources
        """
        try:
            # Use broad query to get representative chunks
            summary_query = "main topics key findings important information overview"
            query_vector = self.embedding_generator.generate_query_embedding(summary_query)
            
            # Search chunks
            search_results = self._search_chunks(
                query_vector=query_vector.tolist(),
                user_id=user_id,
                collection_id=collection_id,
                limit=max_chunks
            )
            
            if not search_results:
                return RAGResult(
                    query="Document Summary",
                    response="No documents available for summarization.",
                    sources_used=[],
                    retrieval_count=0,
                    provider_used=self.model_manager.get_current_llm_provider()
                )
            
            # Format context with citations
            context, sources_info, reference_map = self._format_context_with_citations(
                search_results  # ✅ Only this
            )
            
            # Length instructions
            length_instructions = {
                'short': "Provide a concise 2-3 paragraph summary highlighting the most important points.",
                'medium': "Provide a comprehensive 4-5 paragraph summary covering key topics and findings.",
                'long': "Provide a detailed summary with multiple sections covering all major topics and supporting details."
            }
            
            summary_prompt = f"""You are tasked with creating a summary of the provided document content. Follow these guidelines:

1. {length_instructions.get(summary_length, length_instructions['medium'])}
2. Include citations [1], [2], etc. for all factual claims
3. Organize information logically with clear topics
4. Focus on the most important and relevant information
5. Maintain accuracy and cite sources properly

DOCUMENT CONTENT (with citation references):
{context}

Please provide a well-structured summary with proper citations:"""
            
            # Use ModelManager for completion
            messages = [{"role": "user", "content": summary_prompt}]
            completion = self.model_manager.get_chat_completion(
                messages=messages,
                stream=False
            )
            
            # Extract response
            if hasattr(completion, 'choices'):
                response = completion.choices[0].message.content
            else:
                response = str(completion)
            
            return RAGResult(
                query="Document Summary",
                response=response,
                sources_used=sources_info,
                retrieval_count=len(search_results),
                provider_used=self.model_manager.get_current_llm_provider()
            )
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return RAGResult(
                query="Document Summary",
                response=f"Error generating summary: {str(e)}",
                sources_used=[],
                retrieval_count=0,
                provider_used=self.model_manager.get_current_llm_provider()
            )
    
    async def generate_summary_stream(
        self,
        max_chunks: int = 15,
        summary_length: str = "medium",
        include_complete_response: bool = True,
        user_id: Optional[str] = None,
        collection_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generate document summary with streaming output.
        
        Args:
            max_chunks: Maximum chunks to use for summary
            summary_length: Length of summary ('short', 'medium', 'long')
            include_complete_response: Whether to yield complete response at end
            user_id: User ID for filtering
            collection_id: Collection ID for filtering
            
        Yields:
            Dictionary with type and content/metadata
        """
        try:
            logger.info(f"Streaming document summary (length: {summary_length})...")
            
            # Use broad query to get representative chunks
            summary_query = "main topics key findings important information overview"
            query_vector = self.embedding_generator.generate_query_embedding(summary_query)
            
            # Search chunks
            search_results = self._search_chunks(
                query_vector=query_vector.tolist(),
                user_id=user_id,
                collection_id=collection_id,
                limit=max_chunks
            )
            
            if not search_results:
                yield {
                    "type": "chunk",
                    "content": "No documents available for summarization."
                }
                yield {
                    "type": "done",
                    "sources_used": [],
                    "retrieval_count": 0,
                    "provider_used": self.model_manager.get_current_llm_provider()
                }
                if include_complete_response:
                    yield {
                        "type": "complete_response",
                        "response": "No documents available for summarization.",
                        "sources_used": [],
                        "retrieval_count": 0,
                        "provider_used": self.model_manager.get_current_llm_provider()
                    }
                return
            
            # Format context with citations
            context, sources_info, reference_map = self._format_context_with_citations(
                search_results
            )
            
            # Length instructions
            length_instructions = {
                'short': "Provide a concise 2-3 paragraph summary highlighting the most important points.",
                'medium': "Provide a comprehensive 4-5 paragraph summary covering key topics and findings.",
                'long': "Provide a detailed summary with multiple sections covering all major topics and supporting details."
            }
            
            summary_prompt = f"""You are tasked with creating a summary of the provided document content. Follow these guidelines:

1. {length_instructions.get(summary_length, length_instructions['medium'])}
2. Include citations [1], [2], etc. for all factual claims
3. Organize information logically with clear topics
4. Focus on the most important and relevant information
5. Maintain accuracy and cite sources properly

DOCUMENT CONTENT (with citation references):
{context}

Please provide a well-structured summary with proper citations:"""
            
            # Stream response using ModelManager
            full_summary = ""
            messages = [{"role": "user", "content": summary_prompt}]
            
            stream = self.model_manager.get_chat_completion(
                messages=messages,
                stream=True
            )
            
            for chunk in stream:
                if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    content = delta.content if hasattr(delta, 'content') else ""
                elif hasattr(chunk, 'content'):
                    content = chunk.content
                else:
                    content = ""
                
                if content:
                    full_summary += content
                    yield {"type": "chunk", "content": content}
            
            yield {
                "type": "sources",
                "sources_used": sources_info,
                "retrieval_count": len(search_results)
            }
            
            yield {
                "type": "done",
                "sources_used": sources_info,
                "retrieval_count": len(search_results),
                "provider_used": self.model_manager.get_current_llm_provider()
            }
            
            if include_complete_response:
                yield {
                    "type": "complete_response",
                    "response": full_summary,
                    "sources_used": sources_info,
                    "retrieval_count": len(search_results),
                    "provider_used": self.model_manager.get_current_llm_provider()
                }
            
            logger.info(f"Streaming summary completed using {len(sources_info)} sources")
            
        except Exception as e:
            logger.error(f"Error in streaming summary: {str(e)}")
            yield {
                "type": "error",
                "content": f"Error generating summary: {str(e)}"
            }


if __name__ == "__main__":
    # Test RAG generator
    from services.embedding_generator import EmbeddingGenerator
    
    embedding_generator = EmbeddingGenerator()
    print(f"Embedding provider: {embedding_generator.get_current_provider()}")
    print(f"Embedding dimension: {embedding_generator.get_embedding_dimension()}")