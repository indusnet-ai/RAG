# [file name]: vector_db.py
import logging
from typing import List, Dict, Any, Optional
import json
import os
from pathlib import Path
import re

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from psycopg2.extensions import register_adapter, AsIs
import numpy as np
from dotenv import load_dotenv

from services.embedding_generator import EmbeddedChunk

schema_name = os.getenv("SCHEMA_NAME")
if not schema_name:
    raise ValueError("SCHEMA_NAME environment variable not set")

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VectorDB:
    def __init__(
        self, 
        db_path: str = None,
        collection_name: str = "chunks",  # Changed to match your table name
        embedding_dim: int = None
    ):
        # Get DATABASE_URL from environment
        self.connection_string = os.getenv("DATABASE_URL")
        if not self.connection_string:
            raise ValueError("DATABASE_URL not found in environment variables")
        
        self.is_sqlite = self.connection_string.startswith("sqlite")
        self.table_name = collection_name
        self.conn = None
        self.collection_exists = False
        
        if not self.is_sqlite:
            # Register numpy array adapter for psycopg2
            register_adapter(np.ndarray, self._adapt_numpy_array)
        
        self._initialize_client()
        
        # Don't set embedding_dim here - will be dynamic per chunk
        # Instead, check if table exists and get its dimension
        self._setup_collection(embedding_dim)
    
    def _adapt_numpy_array(self, numpy_array):
        """Adapter to convert numpy arrays to PostgreSQL vector format."""
        return AsIs(f"'[{','.join(map(str, numpy_array))}]'")
    
    def _initialize_client(self):
        """Initialize connection."""
        if self.is_sqlite:
            db_path = self.connection_string.replace("sqlite:///./", "").replace("sqlite:///", "").replace("sqlite://", "")
            if not db_path:
                db_path = "rag_local.db"
            import sqlite3
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            logger.info(f"SQLite local client initialized at {db_path}")
        else:
            try:
                self.conn = psycopg2.connect(self.connection_string)
                self.conn.autocommit = False
                
                # Enable pgvector extension
                with self.conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    self.conn.commit()
                
                logger.info("PostgreSQL client initialized")
                
            except Exception as e:
                logger.error(f"Failed to initialize PostgreSQL client: {str(e)}")
                raise
    
    def _setup_collection(self, initial_dim: Optional[int] = None):
        """Create table with pgvector support if it doesn't exist."""
        try:
            with self.conn.cursor() as cur:
                if self.is_sqlite:
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (self.table_name,))
                    table_exists = cur.fetchone() is not None
                else:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = %s
                        );
                    """, (self.table_name,))
                    table_exists = cur.fetchone()[0]
                
                if table_exists:
                    if self.is_sqlite:
                        logger.info(f"Table '{self.table_name}' exists in SQLite")
                        self.collection_exists = True
                        return
                    # Get the current vector dimension from table definition
                    cur.execute("""
                        SELECT atttypmod 
                        FROM pg_attribute 
                        WHERE attrelid = %s::regclass 
                        AND attname = 'vector'
                    """, (self.table_name,))
                    
                    result = cur.fetchone()
                    if result and result[0]:
                        # atttypmod gives dimension + 4 for vector type
                        current_dim = result[0] - 4
                        logger.info(f"Table '{self.table_name}' exists with vector dimension: {current_dim}")
                        self.collection_exists = True
                        return
                    else:
                        logger.info(f"Table '{self.table_name}' exists but vector dimension unknown")
                        self.collection_exists = True
                        return
                
                # Table doesn't exist, create it
                if self.is_sqlite:
                    create_table_query = f"""
                        CREATE TABLE IF NOT EXISTS {self.table_name} ( 
                            id TEXT PRIMARY KEY,
                            vector TEXT,
                            content TEXT,
                            source_file VARCHAR(512),
                            source_type VARCHAR(32),
                            page_number INTEGER,
                            chunk_index INTEGER,
                            start_char INTEGER,
                            end_char INTEGER,
                            metadata TEXT,
                            embedding_model VARCHAR(128),
                            embedding_provider VARCHAR(64),
                            document_id TEXT,
                            collection_id TEXT,
                            user_id TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """
                else:
                    # schema_name = 'suryavani_4eca84ab'
                    quoted_schema = f'"{schema_name}"'
                    
                    # Use provided dimension or default to 3072 (OpenAI large)
                    create_dim = initial_dim or 3072
                    
                    create_table_query = f"""
                        CREATE TABLE IF NOT EXISTS {quoted_schema}.{self.table_name} ( 
                            id UUID PRIMARY KEY,
                            vector vector({create_dim}),
                            content TEXT,
                            source_file VARCHAR(512),
                            source_type VARCHAR(32),
                            page_number INTEGER,
                            chunk_index INTEGER,
                            start_char INTEGER,
                            end_char INTEGER,
                            metadata JSONB,
                            embedding_model VARCHAR(128),
                            embedding_provider VARCHAR(64),
                            document_id UUID,
                            collection_id UUID,
                            user_id UUID,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """

                cur.execute(create_table_query)
                self.conn.commit()
                
                logger.info(f"Table '{self.table_name}' created successfully")
                self.collection_exists = True
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error setting up collection: {str(e)}")
            raise
    
    def _get_table_vector_dimension(self) -> Optional[int]:
        """Get the current vector dimension of the table"""
        if self.is_sqlite:
            return None
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT atttypmod 
                    FROM pg_attribute 
                    WHERE attrelid = %s::regclass 
                    AND attname = 'vector'
                """, (self.table_name,))
                
                result = cur.fetchone()
                if result and result[0]:
                    return result[0] - 4  # Subtract 4 for vector type overhead
        except Exception as e:
            logger.warning(f"Could not get table vector dimension: {e}")
        
        return None
    
    def _ensure_compatible_dimension(self, embedding_dim: int) -> bool:
        """Check if embedding dimension matches table dimension, resize if needed"""
        if self.is_sqlite:
            return True
        try:
            table_dim = self._get_table_vector_dimension()
            
            if table_dim is None:
                logger.warning("Could not determine table vector dimension")
                return False
            
            if table_dim == embedding_dim:
                return True
            
            logger.warning(f"Dimension mismatch: table={table_dim}, embedding={embedding_dim}")
            
            # For now, just log warning - in production you might want to:
            # 1. Create a new table with correct dimension
            # 2. Migrate data
            # 3. Use pgvector's casting if dimensions are close
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking dimension compatibility: {e}")
            return False
    
    def insert_chunks(self, chunks: List[Dict[str, Any]]) -> List[str]:
        """Insert document chunks with dynamic dimension checking"""
        if not chunks:
            return []
        
        try:
            # Check the dimension of first chunk to verify compatibility
            if chunks and 'vector' in chunks[0]:
                embedding_dim = len(chunks[0]['vector'])
                
                # Verify dimension compatibility
                if not self._ensure_compatible_dimension(embedding_dim):
                    # Log detailed error
                    table_dim = self._get_table_vector_dimension()
                    logger.error(f"CRITICAL: Cannot insert {embedding_dim}D embeddings into {table_dim}D table")
                    logger.error("Solution: Recreate table or use consistent embedding provider")
                    raise ValueError(f"Dimension mismatch: table expects {table_dim}D, got {embedding_dim}D")
            
            if self.is_sqlite:
                cur = self.conn.cursor()
                try:
                    insert_query = f"""
                        INSERT OR IGNORE INTO {self.table_name}
                        (id, vector, content, source_file, source_type, page_number,
                        chunk_index, start_char, end_char, metadata, embedding_model, 
                        embedding_provider, document_id, collection_id, user_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """
                    values = [
                        (
                            str(chunk['id']),
                            json.dumps(chunk['vector'] if isinstance(chunk['vector'], list) else chunk['vector'].tolist()) if 'vector' in chunk else None,
                            chunk['content'],
                            chunk['source_file'],
                            chunk['source_type'],
                            chunk['page_number'],
                            chunk['chunk_index'],
                            chunk['start_char'],
                            chunk['end_char'],
                            json.dumps(chunk['metadata']),
                            chunk['embedding_model'],
                            chunk.get('embedding_provider', 'unknown'),
                            str(chunk['document_id']),
                            str(chunk['collection_id']),
                            str(chunk['user_id'])
                        )
                        for chunk in chunks
                    ]
                    cur.executemany(insert_query, values)
                    self.conn.commit()
                finally:
                    cur.close()
            else:
                # Prepare batch insert
                with self.conn.cursor() as cur:
                    # schema_name = 'suryavani_4eca84ab'
                    quoted_schema = f'"{schema_name}"'
                    full_table_name = f"{quoted_schema}.{self.table_name}"

                    insert_query = f"""
                        INSERT INTO {full_table_name}
                        (id, vector, content, source_file, source_type, page_number,
                        chunk_index, start_char, end_char, metadata, embedding_model, 
                        embedding_provider, document_id, collection_id, user_id)
                        VALUES %s
                        ON CONFLICT (id) DO NOTHING;
                    """
                    
                    values = [
                        (
                            chunk['id'],
                            chunk['vector'],
                            chunk['content'],
                            chunk['source_file'],
                            chunk['source_type'],
                            chunk['page_number'],
                            chunk['chunk_index'],
                            chunk['start_char'],
                            chunk['end_char'],
                            json.dumps(chunk['metadata']),
                            chunk['embedding_model'],
                            chunk.get('embedding_provider', 'unknown'),
                            chunk['document_id'],
                            chunk['collection_id'],
                            chunk['user_id']
                        )
                        for chunk in chunks
                    ]
                    
                    execute_values(cur, insert_query, values)
                    self.conn.commit()
            
            inserted_ids = [chunk['id'] for chunk in chunks]
            logger.info(f"Inserted {len(inserted_ids)} chunks into database")
            
            return inserted_ids
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error inserting chunks: {str(e)}")
            raise
    
    def create_index(
        self,
        index_type: str = "hnsw",
        m: int = 16,
        ef_construction: int = 64,
        distance_metric: str = "vector_l2_ops"
    ):
        """Create index on vector column"""
        if self.is_sqlite:
            logger.info("Skipping HNSW index creation for SQLite")
            return
        try:
            if not self.collection_exists:
                raise Exception("Collection does not exist. Setup collection first.")

            with self.conn.cursor() as cur:
                # schema_name = 'suryavani_4eca84ab'
                quoted_schema = f'"{schema_name}"'
                full_table_name = f"{quoted_schema}.{self.table_name}"

                # Drop existing index
                cur.execute(f"DROP INDEX IF EXISTS {quoted_schema}.{self.table_name}_vector_idx;")

                # Check current dimension
                table_dim = self._get_table_vector_dimension()
                if table_dim and table_dim > 2000 and index_type.lower() == "hnsw":
                    logger.warning(
                        f"HNSW index not optimal for {table_dim}-D vectors. "
                        f"Consider using IVFFlat."
                    )

                if index_type.lower() == "hnsw":
                    create_index_query = f"""
                        CREATE INDEX {self.table_name}_vector_idx
                        ON {full_table_name}
                        USING hnsw (vector {distance_metric})
                        WITH (m = {m}, ef_construction = {ef_construction});
                    """
                    logger.info(f"Creating HNSW index on {full_table_name}")
                else:
                    raise ValueError(f"Unknown index type: {index_type}. Use 'hnsw'")

                cur.execute(create_index_query)
                self.conn.commit()

                logger.info(f"{index_type.upper()} index created successfully")

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error creating index: {str(e)}")
            raise
    
    def search(
        self,
        query_vector: List[float],
        user_id: str,
        collection_id: str,
        limit: int = 10,
        filter_expr: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Search chunks with user and collection filtering"""
        try:
            if isinstance(query_vector, np.ndarray):
                query_vector = query_vector.tolist()

            if self.is_sqlite:
                cur = self.conn.cursor()
                try:
                    # Retrieve matching chunks
                    query = f"""
                        SELECT id, content, source_file, source_type, page_number, 
                               chunk_index, start_char, end_char, metadata, 
                               embedding_model, embedding_provider, vector
                        FROM {self.table_name}
                        WHERE user_id = ? AND collection_id = ?
                    """
                    params = [str(user_id), str(collection_id)]
                    cur.execute(query, params)
                    rows = cur.fetchall()
                finally:
                    cur.close()

                # Compute distance and sort in Python
                results = []
                q_vec = np.array(query_vector)
                for row in rows:
                    row_dict = dict(row)
                    vec_str = row_dict["vector"]
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
                    row_dict["distance"] = distance
                    results.append(row_dict)
                
                results.sort(key=lambda x: x["distance"])
                results = results[:limit]
            else:
                with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # schema_name = 'suryavani_4eca84ab'
                    quoted_schema = f'"{schema_name}"'
                    full_table_name = f"{quoted_schema}.{self.table_name}"

                    where_parts = [
                        f"user_id = '{user_id}'",
                        f"collection_id = '{collection_id}'"
                    ]
                    
                    if filter_expr:
                        where_parts.append(self._convert_filter_to_sql(filter_expr))
                    
                    if filters:
                        for key, value in filters.items():
                            if isinstance(value, str):
                                where_parts.append(f"{key} = '{value}'")
                            else:
                                where_parts.append(f"{key} = {value}")
                    
                    where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

                    query = f"""
                        SELECT
                            id,
                            content,
                            source_file,
                            source_type,
                            page_number,
                            chunk_index,
                            start_char,
                            end_char,
                            metadata,
                            embedding_model,
                            embedding_provider,
                            vector <-> %s::vector AS distance
                        FROM {full_table_name}
                        {where_clause}
                        ORDER BY vector <-> %s::vector
                        LIMIT %s;
                    """

                    vector_str = f"[{','.join(map(str, query_vector))}]"
                    cur.execute(query, (vector_str, vector_str, limit))
                    results = cur.fetchall()

            # Format results
            formatted_results = []
            for result in results:
                metadata = result["metadata"]
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except:
                        metadata = {}

                formatted_result = {
                    "id": result["id"],
                    "score": float(result["distance"]),
                    "content": result["content"],
                    "citation": {
                        "source_file": result["source_file"],
                        "source_type": result["source_type"],
                        "page_number": result["page_number"],
                        "chunk_index": result["chunk_index"],
                        "start_char": result["start_char"],
                        "end_char": result["end_char"],
                    },
                    "metadata": metadata,
                    "embedding_model": result["embedding_model"],
                    "embedding_provider": result["embedding_provider"]
                }
                formatted_results.append(formatted_result)
            
            logger.info(f"Search completed: {len(formatted_results)} results found")
            return formatted_results

        except Exception as e:
            logger.error(f"Error during search: {str(e)}")
            raise
    
    def _convert_filter_to_sql(self, milvus_filter: str) -> str:
        """Convert filter expression to SQL WHERE clause."""
        sql_filter = milvus_filter.replace('==', '=')
        sql_filter = re.sub(r'"([^"]*)"', r"'\1'", sql_filter)
        return sql_filter
    
    def close(self):
        """Close database connection."""
        try:
            if self.conn:
                self.conn.close()
                logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing connection: {str(e)}")


if __name__ == "__main__":
    # Test VectorDB
    vector_db = VectorDB()
    print(f"VectorDB initialized")