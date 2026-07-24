# services/persistent_memory.py
import logging
from typing import Optional, Any, Dict, List
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4
from sqlalchemy import text


from langmem import create_memory_store_manager
from langgraph.store.memory import InMemoryStore

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
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
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.indexing_wait_time = indexing_wait_time

        if namespace is None:
            namespace = ("user_mem", user_id, session_id)
        self.namespace = namespace

        # Vector store config - adjust dims/embed if needed
        self.store = InMemoryStore(
            index={
                "dims": 3072,
                "embed": "openai:text-embedding-3-large",
            }
        )

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

    def save_conversation_summary(self, user_query: str, assistant_response: str, sources_used: Optional[List[Dict[str, Any]]] = None):
        """
        Create a summary from the conversation turn and insert into the memory vector store.
        """
        try:
            timestamp = datetime.now().isoformat()
            summary_message = (
                f"User asked: {user_query}\n"
                f"Assistant responded: {assistant_response}\n"
                f"Sources: {self._summarize_sources(sources_used)}"
            )

            # store_manager.invoke expects messages in an assistant/user pattern depending on implementation
            self.store_manager.invoke(
                {"messages": [
                    {"role": "user", "content": user_query},
                    {"role": "assistant", "content": summary_message},
                ]},
                config={"configurable": {"user_id": self.user_id}},
            )

            logger.info(f"Conversation summary stored into memory store for session {self.session_id}")
        except Exception as e:
            logger.error(f"Error saving conversation summary to vector memory: {e}")
            raise

    def _summarize_sources(self, sources_used: Optional[List[Dict[str, Any]]]) -> str:
        if not sources_used:
            return "No external sources used."
        files = []
        for source in sources_used:
            if isinstance(source, dict):
                files.append(source.get("source_file", "Unknown"))
            elif isinstance(source, str):
                files.append(source)
            else:
                files.append(str(source))
        files = list(set(files))
        return f"Referenced {len(files)} sources: {', '.join(files[:3])}{'...' if len(files) > 3 else ''}"

    def get_relevant_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Query the memory vector store for relevant summaries.
        Return list of dicts with at least keys: value, score, created_at
        """
        try:
            results = self.store.search(self.namespace, query=query, limit=limit)
            # Results objects shape depends on your store; adapt if necessary
            return [
                {
                    "value": getattr(m, "value", None) or m.get("value") if isinstance(m, dict) else str(m),
                    "score": float(getattr(m, "score", 0.0) if hasattr(m, "score") else (m.get("score", 0.0) if isinstance(m, dict) else 0.0)),
                    "created_at": getattr(m, "created_at", None) or (m.get("created_at") if isinstance(m, dict) else None)
                }
                for m in results
            ]
        except Exception as e:
            logger.error(f"Error retrieving memories: {e}")
            return []

    def persist_session_to_sql(self, db, user_uuid: str, session_id: str, summary_text: str, context_json: str):
        """
        Persist or upsert a record to your memory_sessions SQL table.
        Assumes memory_sessions has a unique constraint on (user_id, session_id).
        If you don't have such a unique constraint, change to an update/insert fallback.
        """
        try:
            # Using ON CONFLICT on (user_id, session_id) — ensure a unique constraint exists for those columns
            db.execute(
                text(
                """
                INSERT INTO memory_sessions (id, user_id, session_id, summary_text, context_state, updated_at)
                VALUES (:id, :uid, :sid, :summary, :context, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id, session_id)
                DO UPDATE SET
                    summary_text = EXCLUDED.summary_text,
                    context_state = EXCLUDED.context_state,
                    updated_at = CURRENT_TIMESTAMP;
                """),
                {
                    "id": str(uuid4()),
                    "uid": user_uuid,
                    "sid": session_id,
                    "summary": summary_text,
                    "context": context_json
                }
            )
            db.commit()
            logger.info("Memory session persisted to SQL successfully.")
        except Exception as e:
            logger.error(f"Failed to persist memory session to SQL: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            raise
