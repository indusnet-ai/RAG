import logging
import os
import time
from typing import Optional, Any, Dict, List
from dataclasses import dataclass
from datetime import datetime
import json

from langmem import create_memory_store_manager
from langgraph.store.memory import InMemoryStore
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ConversationTurn:
    """Represents a single conversation turn with context."""
    user_query: str
    assistant_response: str
    sources_used: List[Dict[str, Any]]
    timestamp: str
    session_id: str

class PersistentMemoryLayer:
    def __init__(
        self,
        user_id: str,
        session_id: str,
        model_for_memory: str = "openai:gpt-4o-mini",
        namespace: Optional[tuple] = None,
        indexing_wait_time: int = 10,
        embedding_model: str = "openai:text-embedding-3-large",
        embedding_dims: int = 3072
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.indexing_wait_time = indexing_wait_time
        self.is_enabled = True  # Track if memory is working

        if namespace is None:
            namespace = ("user_mem", user_id, session_id)
        self.namespace = namespace

        try:
            # Set up memory store
            self.store = InMemoryStore(
                index={
                    "dims": embedding_dims,
                    "embed": embedding_model,
                }
            )
            # Wait for indexing to complete
            time.sleep(self.indexing_wait_time)
            
            # Track conversation history with original sources
            self._conversation_sources_map = {}

            # Create store manager to persist conversation summaries
            self.store_manager = create_memory_store_manager(
                model_for_memory,
                namespace=self.namespace,
                store=self.store,
                schemas=None,
                instructions=(
                    "Summarize each assistant response and store it persistently. "
                    "Include contextual cues, user intent, and references used."
                ),
                enable_inserts=True,
            )

            logger.info(f"PersistentMemoryLayer initialized for user {user_id}, session {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to initialize memory layer: {e}")
            logger.warning("Memory functionality will be disabled for this session")
            self.is_enabled = False
            self.store = None
            self.store_manager = None

    def save_conversation_summary(
        self, 
        user_query: str, 
        assistant_response: str, 
        sources_used: Optional[List[Dict[str, Any]]] = None
    ):
        """
        ✅ IMPROVED: Better error handling for quota/rate limit issues
        """
        if not self.is_enabled:
            logger.warning("Memory layer disabled - skipping save")
            return
        
        try:
            timestamp = datetime.now().isoformat()
            
            # Store original sources with timestamp as key
            if sources_used:
                # Extract actual document sources (not memory paths)
                actual_sources = [
                    source for source in sources_used 
                    if source.get('source_type') != 'memory' and 
                       not source.get('source_file', '').startswith('/mnt/data/')
                ]
                self._conversation_sources_map[timestamp] = actual_sources
            
            # Format sources properly
            sources_summary = self._summarize_sources(sources_used)
            
            summary_message = (
                f"[{timestamp}]\n"
                f"User asked: {user_query}\n"
                f"Assistant responded: {assistant_response}\n"
                f"Sources referenced: {sources_summary}\n"
                f"SOURCE_METADATA: {json.dumps(sources_used or [])}"
            )

            self.store_manager.invoke(
                {"messages": [
                    {"role": "user", "content": user_query},
                    {"role": "assistant", "content": summary_message},
                ]},
                config={"configurable": {"user_id": self.user_id}},
            )

            logger.info(f"✅ Conversation summary stored for session {self.session_id} with {len(sources_used or [])} sources")
            
        except Exception as e:
            error_msg = str(e)
            
            # ✅ Handle specific error types
            if "429" in error_msg or "quota" in error_msg.lower():
                logger.error(f"❌ OpenAI quota exceeded - cannot save to memory: {e}")
                logger.warning("⚠️  Memory saving disabled due to quota limits. Consider:")
                logger.warning("   1. Adding credits to your OpenAI account")
                logger.warning("   2. Using a different embedding model (e.g., FastEmbed)")
                logger.warning("   3. Disabling memory layer temporarily")
                self.is_enabled = False  # Disable to prevent repeated errors
                
            elif "rate_limit" in error_msg.lower():
                logger.error(f"❌ Rate limit hit - memory save failed: {e}")
                logger.warning("⚠️  Too many requests - memory temporarily unavailable")
                
            else:
                logger.error(f"❌ Error saving conversation summary: {e}")
            
            # Don't raise - let the application continue without memory

    def _summarize_sources(self, sources_used: Optional[List[Dict[str, Any]]]) -> str:
        """Format sources for storage - only include actual document sources."""
        if not sources_used:
            return "No external sources used."
        
        try:
            files = []
            for source in sources_used:
                if isinstance(source, dict):
                    source_file = source.get("source_file", "Unknown")
                    source_type = source.get("source_type", "")
                    
                    # Skip memory sources when summarizing
                    if source_type == "memory" or source_file.startswith("/mnt/data/"):
                        continue
                    
                    files.append(source_file)
                elif isinstance(source, str):
                    if not source.startswith("/mnt/data/"):
                        files.append(source)
                else:
                    logger.warning(f"Unexpected source type: {type(source)}")
                    files.append(str(source))
            
            # Remove duplicates while preserving order
            files = list(dict.fromkeys(files))
            
            if not files:
                return "Context from previous conversation"
            
            if len(files) <= 3:
                return f"Referenced {len(files)} source(s): {', '.join(files)}"
            else:
                return f"Referenced {len(files)} sources: {', '.join(files[:3])} and {len(files) - 3} more"
        except Exception as e:
            logger.error(f"Error summarizing sources: {e}")
            return "Error processing sources"

    def get_relevant_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        ✅ IMPROVED: Better error handling for quota/rate limit issues
        Retrieve relevant memories with ORIGINAL source information extracted.
        """
        if not self.is_enabled or not self.store:
            logger.warning("Memory layer disabled - returning empty results")
            return []
        
        try:
            results = self.store.search(self.namespace, query=query, limit=limit)
            
            memories = []
            for m in results:
                memory_content = m.value
                
                # Extract original sources from the stored metadata
                original_sources = []
                if "SOURCE_METADATA:" in memory_content:
                    try:
                        # Extract the JSON metadata from the content
                        metadata_start = memory_content.find("SOURCE_METADATA:") + len("SOURCE_METADATA:")
                        metadata_json = memory_content[metadata_start:].strip()
                        stored_sources = json.loads(metadata_json)
                        
                        # Filter to only actual document sources
                        original_sources = [
                            source for source in stored_sources
                            if source.get('source_type') != 'memory' and 
                               not source.get('source_file', '').startswith('/mnt/data/')
                        ]
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(f"Could not parse source metadata: {e}")
                
                memories.append({
                    "content": memory_content,
                    "score": m.score,
                    "created_at": m.created_at,
                    "original_sources": original_sources
                })
            
            return memories
            
        except Exception as e:
            error_msg = str(e)
            
            # ✅ Handle specific error types
            if "429" in error_msg or "quota" in error_msg.lower():
                logger.error(f"❌ OpenAI quota exceeded - cannot retrieve memories: {e}")
                logger.warning("⚠️  Memory retrieval disabled due to quota limits")
                self.is_enabled = False
                return []
                
            elif "rate_limit" in error_msg.lower():
                logger.error(f"❌ Rate limit hit - memory retrieval failed: {e}")
                logger.warning("⚠️  Too many requests - returning no memories")
                return []
                
            else:
                logger.error(f"Error retrieving memories: {e}")
                return []

    def get_memory_sources(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract all unique original document sources from retrieved memories.
        Returns a list of source dictionaries suitable for citation.
        """
        all_sources = []
        seen_sources = set()
        
        for memory in memories:
            original_sources = memory.get("original_sources", [])
            for source in original_sources:
                source_key = f"{source.get('source_file')}_{source.get('page_number', 'N/A')}"
                if source_key not in seen_sources:
                    seen_sources.add(source_key)
                    all_sources.append(source)
        
        return all_sources
    
    def is_available(self) -> bool:
        """Check if memory layer is currently available"""
        return self.is_enabled


if __name__ == "__main__":
    from types import SimpleNamespace

    memory = PersistentMemoryLayer(
        user_id="test_user",
        session_id="test_session_1",
    )

    if memory.is_available():
        mock_response = SimpleNamespace(
            query="What are the benefits of meditation?",
            response="Meditation improves focus, reduces stress, and enhances emotional regulation.",
            sources_used=[
                {"source_file": "mindfulness_study.pdf", "source_type": "pdf", "page_number": 5},
                {"source_file": "wellness_guide.pdf", "source_type": "pdf", "page_number": 12}
            ]
        )

        memory.save_conversation_summary(
            user_query=mock_response.query,
            assistant_response=mock_response.response,
            sources_used=mock_response.sources_used,
        )

        relevant = memory.get_relevant_memories("meditation benefits")
        print(f"\nRelevant Memories Found: {len(relevant)}")
        
        # Extract original sources
        sources = memory.get_memory_sources(relevant)
        print(f"\nOriginal Document Sources: {sources}")
    else:
        print("Memory layer is not available - check logs for details")