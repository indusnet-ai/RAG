# import os
# from langgraph.store.postgres import PostgresStore
# from langmem import create_memory_store_manager
# from pydantic import BaseModel
# from typing import Optional
# import logging
# import json
# # Initialize the logger for this specific module
# logger = logging.getLogger(__name__)
# from typing import Optional, Literal
# from pydantic import BaseModel

# class Triple(BaseModel):
#     kind: Literal["triple"] = "triple"
#     subject: str
#     predicate: str
#     object: str
#     confidence: Optional[float] = None

# from contextlib import ExitStack

# class PersistentMemoryLayer:
#     def __init__(self, user_id: str, collection_id: str, model_for_memory="openai:gpt-4o-mini"):
#         self.user_id = user_id
#         self.collection_id = collection_id

#         database_url = os.getenv("DATABASE_URL")
#         if not database_url:
#             raise RuntimeError("DATABASE_URL not set")

#         self._stack = ExitStack()
#         self.store = self._stack.enter_context(
#             PostgresStore.from_conn_string(
#                 database_url,
#                 index={
#                     "dims": 1536,
#                     "embed": "openai:text-embedding-3-small",
#                     "fields": ["subject", "predicate", "object"],  # ← THIS IS REQUIRED
#                 }
#             )
#         )
#         self.store.setup()

#         self.namespace = (
#             "memory",
#             "user", user_id,
#             "collection", collection_id,
#             "triples"
#         )

#         self.manager = create_memory_store_manager(
#             model_for_memory,              # positional ✔
#             namespace=self.namespace,
#             schemas=[Triple],
#             instructions=(
#                 "Extract long-term user facts, preferences, goals, and events "
#                 "that are relevant within this conversation. "
#                 "Ignore document content, citations, and assistant explanations."
#             ),
#             enable_inserts=True,
#             enable_deletes=True,
#             store=self.store,               # ← IMPORTANT
#         )


#     def write_memory(self, user_query: str, assistant_response: str, **kwargs):
#         try:
#             # Create the messages payload
#             input_data = {
#                 "messages": [
#                     {"role": "user", "content": user_query},
#                     {"role": "assistant", "content": assistant_response},
#                 ]
#             }

#             # Use the manager as a runnable. 
#             # This triggers the LLM to extract the Triple and save it to self.store.
#             self.manager.invoke(
#                 {
#                     "messages": [
#                         {"role": "user", "content": user_query},
#                         {"role": "assistant", "content": assistant_response},
#                     ]
#                 },
#                 config={"configurable": {"thread_id": self.user_id}},
#             )


#             logger.info("✅ LangMem state updated successfully")
            
#         except Exception as e:
#             # If you still get 'kind', it's because LangMem expects 
#             # a 'kind' key in the messages or metadata.
#             logger.error(f"❌ LangMem put error: {str(e)}")
    

#     def retrieve_memory(self, query: str, limit: int = 5):
#         try:
#             # Ensure search is looking in the exact same namespace
#             results = self.store.search(
#                 self.namespace,
#                 query=query,
#                 limit=limit
#             )

#             formatted_memories = []
#             for r in results:
#                 val = r.value
                
#                 # Handle potential stringified JSON
#                 if isinstance(val, str):
#                     try:
#                         val = json.loads(val)
#                     except:
#                         continue

#                 if isinstance(val, dict):
#                     # Check for Triple fields
#                     s = val.get("subject")
#                     p = val.get("predicate")
#                     o = val.get("object")
#                     if s and p and o:
#                         formatted_memories.append(f"{s} {p} {o}")
                
#                 # Handle Pydantic objects if returned directly
#                 elif hasattr(val, "subject"):
#                     formatted_memories.append(f"{val.subject} {val.predicate} {val.object}")

#             logger.info(f"Retrieved {len(formatted_memories)} memory items")
#             return formatted_memories

#         except Exception as e:
#             logger.error(f"❌ Memory retrieval error: {str(e)}")
#             return []

import os
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv
import json
import numpy as np

from langchain_community.vectorstores.pgvector import PGVector
from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI
from sqlalchemy import create_engine, text


from services.embedding_generator import EmbeddingGenerator  
load_dotenv()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class SQLiteVectorStore:
    def __init__(self, connection_string, collection_name, embedding_function):
        self.connection_string = connection_string
        self.collection_name = collection_name
        self.embedding_function = embedding_function
        
        # Initialize SQLite DB connection
        db_path = connection_string.replace("sqlite:///./", "").replace("sqlite:///", "").replace("sqlite://", "")
        if not db_path:
            db_path = "rag_local.db"
        import sqlite3
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        # Create table if not exists
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS langchain_sqlite_embeddings (
                    uuid TEXT PRIMARY KEY,
                    collection_name TEXT,
                    document TEXT,
                    cmetadata TEXT,
                    embedding TEXT
                )
            """)

    def add_texts(self, texts, metadatas=None):
        import uuid
        import json
        with self.conn:
            for i, text in enumerate(texts):
                doc_uuid = str(uuid.uuid4())
                metadata = metadatas[i] if metadatas else {}
                emb = self.embedding_function.embed_query(text)
                self.conn.execute("""
                    INSERT INTO langchain_sqlite_embeddings (uuid, collection_name, document, cmetadata, embedding)
                    VALUES (?, ?, ?, ?, ?)
                """, (doc_uuid, self.collection_name, text, json.dumps(metadata), json.dumps(emb)))

    def similarity_search(self, query, k=5, filter=None):
        import json
        import numpy as np
        
        # Retrieve only items in THIS collection (scoped per user+session)
        cur = self.conn.cursor()
        try:
            cur.execute("""
                SELECT uuid, document, cmetadata, embedding 
                FROM langchain_sqlite_embeddings 
                WHERE collection_name = ?
            """, (self.collection_name,))
            rows = cur.fetchall()
        finally:
            cur.close()
            
        # Parse query embedding
        q_emb = np.array(self.embedding_function.embed_query(query))
        
        # Filter and score
        from langchain_core.documents import Document
        scored_docs = []
        for row in rows:
            meta = json.loads(row["cmetadata"])
            
            # Apply filter
            if filter:
                match = True
                for fk, fv in filter.items():
                    if meta.get(fk) != fv:
                        match = False
                        break
                if not match:
                    continue
                    
            emb_str = row["embedding"]
            if not emb_str:
                continue
            row_emb = np.array(json.loads(emb_str))
            
            norm_a = np.linalg.norm(row_emb)
            norm_b = np.linalg.norm(q_emb)
            if norm_a > 0 and norm_b > 0:
                similarity = np.dot(row_emb, q_emb) / (norm_a * norm_b)
                distance = 1.0 - similarity
            else:
                distance = 1.0
                
            scored_docs.append((distance, Document(page_content=row["document"], metadata=meta)))
            
        # Sort by distance (ascending)
        scored_docs.sort(key=lambda x: x[0])
        return [doc for dist, doc in scored_docs[:k]]


@dataclass
class ConversationTurn:
    user_query: str
    assistant_response: str
    sources_used: List[Dict[str, Any]]
    timestamp: str
    session_id: str

memory_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
)

class PersistentMemoryLayer:
    def __init__(
        self,
        user_id: str,
        collection_id: str,
        llm=memory_llm,
        collection_name: str = "semantic_memory",
    ):
        self.user_id = user_id
        self.collection_id = collection_id
        # Scope memory per user+collection so sessions never cross-contaminate
        self.collection_name = f"mem_{user_id[:8]}_{collection_id[:8]}"
        self.memory_llm = llm

        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL not set")

        # Your embedding generator
        self.embedding_generator = EmbeddingGenerator()

        # Wrap for LangChain compatibility
        class LCEmbeddingWrapper(Embeddings):
            def embed_documents(_, texts: List[str]):
                return [self.embedding_generator.generate_query_embedding(t).tolist() for t in texts]

            def embed_query(_, text: str):
                return self.embedding_generator.generate_query_embedding(text).tolist()

        self.embedding_wrapper = LCEmbeddingWrapper()

        if db_url.startswith("sqlite"):
            logger.info(f"🔗 Connecting SQLiteVectorStore: table={collection_name}")
            self.vector_store = SQLiteVectorStore(
                connection_string=db_url,
                collection_name=self.collection_name,
                embedding_function=self.embedding_wrapper,
            )
        else:
            logger.info(f"🔗 Connecting PGVector store: table={collection_name}")
            self.vector_store = PGVector(
                connection_string=db_url,
                collection_name=self.collection_name,
                embedding_function=self.embedding_wrapper,
            )

    # -----------------------------
    # Save memory as embedding
    # -----------------------------
    def save_conversation_summary(
        self,
        user_query: str,
        assistant_response: str,
        sources_used: Optional[List[Dict[str, Any]]] = None,
    ):
        try:
            timestamp = datetime.utcnow().isoformat()

            summary = (
                f"User asked: {user_query}\n"
                f"Assistant responded: {assistant_response}\n"
                f"SOURCES: {sources_used}"
            )

            metadata = {
                "user_id": self.user_id,
                "collection_id": self.collection_id,
                "timestamp": timestamp,
            }

            self.vector_store.add_texts(
                texts=[summary],
                metadatas=[metadata]
            )

            logger.info("💾 Saved semantic memory via PGVector.")

        except Exception as e:
            logger.error(f"Error saving memory: {e}", exc_info=True)
            
    def extract_semantic_memory(self, user_query: str, assistant_response: str) -> str:
        prompt = f"""
    You are creating long-term semantic memory for an AI assistant.

    Extract ONLY the important, reusable information from the exchange below.
    Do NOT include conversational phrasing.
    Do NOT include questions.
    Do NOT include filler or explanations.

    Return a compact paragraph or bullet list capturing the core meaning.

    Conversation:
    User: {user_query}
    Assistant: {assistant_response}

    Semantic memory:
    """
        response = self.memory_llm.invoke(prompt)
        return response.content.strip()

    
    def save_semantic_memory(
    self,
    user_query: str,
    assistant_response: str,
    sources_used: Optional[List[Dict[str, Any]]] = None,
):
        try:
            timestamp = datetime.utcnow().isoformat()

            semantic_memory = self.extract_semantic_memory(
                user_query, assistant_response
            )

            if not semantic_memory:
                logger.info("🧠 Empty semantic memory. Skipping save.")
                return

            # ✅ IMPROVEMENT: Extract searchable fields
            source_files = []
            chunk_ids = []
            
            for source in (sources_used or []):
                # Collect source files
                source_file = source.get("source_file")
                if source_file and source_file not in source_files:
                    source_files.append(source_file)
                
                # Collect all chunk IDs
                chunks = source.get("chunk_ids", [])
                chunk_ids.extend(chunks)

            metadata = {
                "user_id": self.user_id,
                "collection_id": self.collection_id,
                "timestamp": timestamp,
                "sources": sources_used or [],
                
                # ✅ NEW: Flat arrays for easier querying
                "source_files": source_files,        # ["file1.pdf", "file2.pdf"]
                "chunk_ids": list(set(chunk_ids)),   # ["uuid-1", "uuid-2", ...]
                
                "type": "semantic_summary",
            }

            self.vector_store.add_texts(
                texts=[semantic_memory],
                metadatas=[metadata],
            )

            logger.info(f"💾 Saved semantic memory with {len(source_files)} source files.")

        except Exception as e:
            logger.error(f"Error saving semantic memory: {e}", exc_info=True)

    def mark_memories_deleted(self, chunk_ids: List[str], source_file: str):
        """
        Mark all memories that reference a deleted document.
        Uses direct SQL UPDATE with JSON to JSONB casting.
        
        Args:
            chunk_ids: List of chunk IDs from the deleted document
            source_file: Name of the deleted file
        """
        try:
            connection_string = os.getenv("DATABASE_URL")
            if connection_string.startswith("sqlite"):
                import sqlite3
                db_path = connection_string.replace("sqlite:///./", "").replace("sqlite:///", "").replace("sqlite://", "")
                if not db_path:
                    db_path = "rag_local.db"
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT uuid as id, cmetadata FROM langchain_sqlite_embeddings")
                    memories = cur.fetchall()
                    updated_count = 0
                    
                    for memory in memories:
                        import json
                        metadata = json.loads(memory["cmetadata"]) if isinstance(memory["cmetadata"], str) else memory["cmetadata"]
                        
                        if (metadata.get("user_id") == self.user_id and 
                            metadata.get("collection_id") == self.collection_id and 
                            metadata.get("type") == "semantic_summary" and 
                            not metadata.get("is_deleted", False)):
                            
                            references_deleted = False
                            
                            source_files = metadata.get("source_files", [])
                            if source_file in source_files:
                                references_deleted = True
                            
                            if not references_deleted:
                                memory_chunk_ids = metadata.get("chunk_ids", [])
                                matching_chunks = set(chunk_ids) & set(memory_chunk_ids)
                                if matching_chunks:
                                    references_deleted = True
                            
                            if not references_deleted:
                                sources = metadata.get("sources", [])
                                for source in sources:
                                    if source.get("source_file") == source_file:
                                        references_deleted = True
                                        break
                                    source_chunk_ids = source.get("chunk_ids", [])
                                    if set(chunk_ids) & set(source_chunk_ids):
                                        references_deleted = True
                                        break
                            
                            if references_deleted:
                                metadata["is_deleted"] = True
                                metadata["deleted_at"] = datetime.utcnow().isoformat()
                                cur.execute("""
                                    UPDATE langchain_sqlite_embeddings
                                    SET cmetadata = ?
                                    WHERE uuid = ?
                                """, (json.dumps(metadata), memory["id"]))
                                updated_count += 1
                                logger.info(f"✅ Marked memory {str(memory['id'])[:8]}... as deleted (SQLite)")
                    conn.commit()
                finally:
                    conn.close()
                return updated_count

            # PostgreSQL path
            engine = create_engine(connection_string)
            with engine.connect() as conn:
                # Get all memories for this user/collection
                result = conn.execute(text("""
                    SELECT 
                        uuid as id,
                        cmetadata
                    FROM langchain_pg_embedding
                    WHERE 
                        (cmetadata->>'user_id') = :uid
                        AND (cmetadata->>'collection_id') = :cid
                        AND (cmetadata->>'type') = 'semantic_summary'
                        AND (cmetadata->>'is_deleted' IS NULL OR (cmetadata->>'is_deleted')::boolean = false)
                """), {
                    "uid": self.user_id,
                    "cid": self.collection_id
                })
                
                memories = result.fetchall()
                updated_count = 0
                
                for memory in memories:
                    import json
                    metadata = json.loads(memory.cmetadata) if isinstance(memory.cmetadata, str) else memory.cmetadata
                    
                    # Check if references deleted document
                    references_deleted = False
                    
                    # Check 1: source_files array
                    source_files = metadata.get("source_files", [])
                    if source_file in source_files:
                        references_deleted = True
                        logger.debug(f"✓ Match on source_file: {source_file}")
                    
                    # Check 2: chunk_ids array
                    if not references_deleted:
                        memory_chunk_ids = metadata.get("chunk_ids", [])
                        matching_chunks = set(chunk_ids) & set(memory_chunk_ids)
                        if matching_chunks:
                            references_deleted = True
                            logger.debug(f"✓ Match on chunk_ids: {len(matching_chunks)} chunks")
                    
                    # Check 3: sources array (fallback)
                    if not references_deleted:
                        sources = metadata.get("sources", [])
                        for source in sources:
                            if source.get("source_file") == source_file:
                                references_deleted = True
                                logger.debug(f"✓ Match on sources array: {source_file}")
                                break
                            source_chunk_ids = source.get("chunk_ids", [])
                            if set(chunk_ids) & set(source_chunk_ids):
                                references_deleted = True
                                logger.debug(f"✓ Match on sources.chunk_ids")
                                break
                    
                    if references_deleted:
                        # ✅ FIX: Cast JSON to JSONB before merging
                        timestamp = datetime.utcnow().isoformat()
                        conn.execute(text("""
                            UPDATE langchain_pg_embedding
                            SET cmetadata = (cmetadata::jsonb || 
                                jsonb_build_object(
                                    'is_deleted', true,
                                    'deleted_at', :timestamp
                                ))::json
                            WHERE uuid = :mem_id
                        """), {
                            "mem_id": str(memory.id),
                            "timestamp": timestamp
                        })
                        updated_count += 1
                        logger.info(f"✅ Marked memory {str(memory.id)[:8]}... as deleted")
                
                conn.commit()
            
            logger.info(f"🗑️ Marked {updated_count} memories as deleted for: {source_file}")
            return updated_count
            
        except Exception as e:
            logger.error(f"Error marking memories as deleted: {e}", exc_info=True)
            return 0
        
    def hard_delete_embeddings(self, chunk_ids: List[str], source_file: str) -> int:
        """
        Completely delete embedding rows from langchain_embedding table.
        
        Args:
            chunk_ids: List of chunk IDs to delete
            source_file: Source file name for additional filtering
        
        Returns:
            Number of rows deleted
        """
        try:
            if not chunk_ids:
                logger.warning("No chunk IDs provided for hard deletion")
                return 0
            
            connection_string = os.getenv("DATABASE_URL")
            if connection_string.startswith("sqlite"):
                import sqlite3
                db_path = connection_string.replace("sqlite:///./", "").replace("sqlite:///", "").replace("sqlite://", "")
                if not db_path:
                    db_path = "rag_local.db"
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT uuid as id, cmetadata FROM langchain_sqlite_embeddings")
                    memories = cur.fetchall()
                    deleted_count = 0
                    
                    for memory in memories:
                        import json
                        metadata = json.loads(memory["cmetadata"]) if isinstance(memory["cmetadata"], str) else memory["cmetadata"]
                        
                        if (metadata.get("user_id") == self.user_id and 
                            metadata.get("collection_id") == self.collection_id and 
                            metadata.get("type") == "semantic_summary"):
                            
                            memory_chunk_ids = metadata.get("chunk_ids", [])
                            matching_chunks = set(chunk_ids) & set(memory_chunk_ids)
                            matches_file = source_file and (source_file in metadata.get("source_files", []))
                            
                            if matching_chunks or matches_file:
                                cur.execute("DELETE FROM langchain_sqlite_embeddings WHERE uuid = ?", (memory["id"],))
                                deleted_count += 1
                                logger.info(f"🗑️ Hard deleted memory {str(memory['id'])[:8]}... (SQLite)")
                    conn.commit()
                finally:
                    conn.close()
                return deleted_count

            # PostgreSQL path
            engine = create_engine(connection_string)
            with engine.connect() as conn:
                # Delete embeddings where any chunk_id in the chunk_ids array matches
                # The metadata has chunk_ids as a JSON array, so we need to check if any overlap
                delete_query = """
                DELETE FROM langchain_pg_embedding
                WHERE (cmetadata->>'user_id') = :user_id
                AND (cmetadata->>'collection_id') = :collection_id
                AND (cmetadata->>'type') = 'semantic_summary'
                AND EXISTS (
                    SELECT 1 FROM jsonb_array_elements_text((cmetadata->'chunk_ids')::jsonb) AS chunk_id
                    WHERE chunk_id = ANY(:chunk_ids)
                )
                """
                
                # If source_file is provided, add it as an additional filter
                if source_file:
                    delete_query += " AND :source_file = ANY(SELECT jsonb_array_elements_text((cmetadata->'source_files')::jsonb))"
                
                params = {
                    "chunk_ids": chunk_ids,
                    "user_id": self.user_id,
                    "collection_id": self.collection_id
                }
                
                if source_file:
                    params["source_file"] = source_file
                
                result = conn.execute(text(delete_query), params)
                deleted_count = result.rowcount
                
                conn.commit()
                
                logger.info(f"🗑️ Hard deleted {deleted_count} embeddings for {len(chunk_ids)} chunks")
                return deleted_count
            
        except Exception as e:
            logger.error(f"Error in hard_delete_embeddings: {str(e)}", exc_info=True)
            raise


    def restore_memories(self, chunk_ids: List[str], source_file: str):
        """
        Restore memories associated with a restored document.
        Uses direct SQL UPDATE with JSON to JSONB casting.
        
        Args:
            chunk_ids: List of chunk IDs from the restored document
            source_file: Name of the restored file
        """
        try:
            connection_string = os.getenv("DATABASE_URL")
            if connection_string.startswith("sqlite"):
                import sqlite3
                db_path = connection_string.replace("sqlite:///./", "").replace("sqlite:///", "").replace("sqlite://", "")
                if not db_path:
                    db_path = "rag_local.db"
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT uuid as id, cmetadata FROM langchain_sqlite_embeddings")
                    memories = cur.fetchall()
                    restored_count = 0
                    
                    for memory in memories:
                        import json
                        metadata = json.loads(memory["cmetadata"]) if isinstance(memory["cmetadata"], str) else memory["cmetadata"]
                        
                        if (metadata.get("user_id") == self.user_id and 
                            metadata.get("collection_id") == self.collection_id and 
                            metadata.get("is_deleted", False)):
                            
                            references_restored = False
                            
                            source_files = metadata.get("source_files", [])
                            if source_file in source_files:
                                references_restored = True
                            
                            if not references_restored:
                                memory_chunk_ids = metadata.get("chunk_ids", [])
                                matching_chunks = set(chunk_ids) & set(memory_chunk_ids)
                                if matching_chunks:
                                    references_restored = True
                            
                            if not references_restored:
                                sources = metadata.get("sources", [])
                                for source in sources:
                                    if source.get("source_file") == source_file:
                                        references_restored = True
                                        break
                                    source_chunk_ids = source.get("chunk_ids", [])
                                    if set(chunk_ids) & set(source_chunk_ids):
                                        references_restored = True
                                        break
                            
                            if references_restored:
                                if "is_deleted" in metadata:
                                    del metadata["is_deleted"]
                                if "deleted_at" in metadata:
                                    del metadata["deleted_at"]
                                cur.execute("""
                                    UPDATE langchain_sqlite_embeddings
                                    SET cmetadata = ?
                                    WHERE uuid = ?
                                """, (json.dumps(metadata), memory["id"]))
                                restored_count += 1
                                logger.info(f"✅ Restored memory {str(memory['id'])[:8]}... (SQLite)")
                    conn.commit()
                finally:
                    conn.close()
                return restored_count

            # PostgreSQL path
            engine = create_engine(connection_string)
            with engine.connect() as conn:
                # Get deleted memories for this user/collection
                result = conn.execute(text("""
                    SELECT 
                        uuid as id,
                        cmetadata
                    FROM langchain_pg_embedding
                    WHERE 
                        (cmetadata->>'user_id') = :uid
                        AND (cmetadata->>'collection_id') = :cid
                        AND (cmetadata->>'is_deleted')::boolean = true
                """), {
                    "uid": self.user_id,
                    "cid": self.collection_id
                })
                
                memories = result.fetchall()
                restored_count = 0
                
                for memory in memories:
                    import json
                    metadata = json.loads(memory.cmetadata) if isinstance(memory.cmetadata, str) else memory.cmetadata
                    
                    # Check if references restored document
                    references_restored = False
                    
                    # Check source_file
                    source_files = metadata.get("source_files", [])
                    if source_file in source_files:
                        references_restored = True
                        logger.debug(f"✓ Match on source_file: {source_file}")
                    
                    # Check chunk_ids
                    if not references_restored:
                        memory_chunk_ids = metadata.get("chunk_ids", [])
                        matching_chunks = set(chunk_ids) & set(memory_chunk_ids)
                        if matching_chunks:
                            references_restored = True
                            logger.debug(f"✓ Match on chunk_ids: {len(matching_chunks)} chunks")
                    
                    # Check sources array (fallback)
                    if not references_restored:
                        sources = metadata.get("sources", [])
                        for source in sources:
                            if source.get("source_file") == source_file:
                                references_restored = True
                                logger.debug(f"✓ Match on sources array")
                                break
                            source_chunk_ids = source.get("chunk_ids", [])
                            if set(chunk_ids) & set(source_chunk_ids):
                                references_restored = True
                                logger.debug(f"✓ Match on sources.chunk_ids")
                                break
                    
                    if references_restored:
                        # ✅ FIX: Cast JSON to JSONB, remove fields, cast back to JSON
                        conn.execute(text("""
                            UPDATE langchain_pg_embedding
                            SET cmetadata = (cmetadata::jsonb - 'is_deleted' - 'deleted_at')::json
                            WHERE uuid = :mem_id
                        """), {
                            "mem_id": str(memory.id)
                        })
                        restored_count += 1
                        logger.info(f"✅ Restored memory {str(memory.id)[:8]}...")
                
                conn.commit()
            
            logger.info(f"♻️ Restored {restored_count} memories for: {source_file}")
            return restored_count
            
        except Exception as e:
            logger.error(f"Error restoring memories: {e}", exc_info=True)
            return 0

    # -----------------------------
    # Retrieve semantic memories
    # -----------------------------
    def get_relevant_memories(self, query: str, limit: int = 5):
        try:
            logger.info(f"🔍 Semantic search: '{query}'")

            results = self.vector_store.similarity_search(
                query=query,
                k=limit * 2,  # 🆕 Get more to account for filtering
                filter={
                    "user_id": self.user_id,
                    "collection_id": self.collection_id
                    # 🆕 Don't add is_deleted filter here - we'll filter in Python
                }
            )

            # 🆕 Filter out deleted memories
            active_results = [
                r for r in results 
                if not r.metadata.get("is_deleted", False)
            ][:limit]  # 🆕 Take only limit after filtering

            formatted = [
                {
                    "content": r.page_content,
                    "metadata": r.metadata
                }
                for r in active_results
            ]

            logger.info(f"🔍 Found {len(formatted)} active memories (filtered {len(results) - len(active_results)} deleted)")

            return formatted

        except Exception as e:
            logger.error(f"Error retrieving semantic memories: {e}", exc_info=True)
            return []

    # -----------------------------
    # Extract source metadata
    # -----------------------------
    def get_memory_sources(self, memories: List[Dict[str, Any]]):
        sources = []
        for mem in memories:
            content = mem.get("content", "")
            if "SOURCES:" in content:
                try:
                    import json
                    src = content.split("SOURCES:")[1].strip()
                    parsed = json.loads(src) if src else []
                    sources.extend(parsed)
                except:
                    continue
        return sources


if __name__ == "__main__":
    from types import SimpleNamespace

    memory = PersistentMemoryLayer("test_user", "session_1")

    mock = SimpleNamespace(
        query="What is meditation good for?",
        response="Meditation reduces stress and improves concentration.",
        sources_used=[{"source_file": "study.pdf"}],
    )

    memory.save_conversation_summary(
        user_query=mock.query,
        assistant_response=mock.response,
        sources_used=mock.sources_used,
    )

    print(memory.get_relevant_memories("stress reduction"))
