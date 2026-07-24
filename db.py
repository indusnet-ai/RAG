# db.py
import os
from dotenv import load_dotenv
from fastapi import logger
from sqlalchemy import create_engine, text as sa_text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from services.metrics import track_db_connection_failure
import re
import sqlite3
from uuid import UUID

# Register UUID adapter for SQLite
sqlite3.register_adapter(UUID, lambda u: str(u))

import sqlalchemy
import sqlalchemy.sql
import sqlalchemy.sql.expression

def text(sql_str):
    if isinstance(sql_str, str) and DATABASE_URL.startswith("sqlite"):
        # Replace pgvector types
        sql_str = re.sub(r'(?i)\bvector\(\d+\)', 'TEXT', sql_str)
        # Replace CAST(xxxx AS vector) with xxxx
        sql_str = re.sub(r'(?i)\bCAST\((.*?)\s+AS\s+vector\)', r'\1', sql_str)
        # Replace BIGSERIAL
        sql_str = sql_str.replace('BIGSERIAL PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT')
        sql_str = sql_str.replace('bigserial primary key', 'INTEGER PRIMARY KEY AUTOINCREMENT')
        # Replace gen_random_uuid()
        sql_str = sql_str.replace('DEFAULT gen_random_uuid()', 'DEFAULT (lower(hex(randomblob(16))))')
        sql_str = sql_str.replace('gen_random_uuid()', 'lower(hex(randomblob(16)))')
        # Replace NOW() or NOW
        sql_str = re.sub(r'(?i)\bDEFAULT\s+NOW\(\)', 'DEFAULT CURRENT_TIMESTAMP', sql_str)
        sql_str = re.sub(r'(?i)\bDEFAULT\s+NOW\b', 'DEFAULT CURRENT_TIMESTAMP', sql_str)
        sql_str = re.sub(r'(?i)\bNOW\(\)', 'CURRENT_TIMESTAMP', sql_str)
        # Replace ILIKE
        sql_str = re.sub(r'(?i)\bILIKE\b', 'LIKE', sql_str)
    return sa_text(sql_str)

# Apply monkeypatch to all sqlalchemy entrypoints
sqlalchemy.text = text
sqlalchemy.sql.text = text
sqlalchemy.sql.expression.text = text


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing in .env")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """Database session dependency with error tracking"""
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        track_db_connection_failure()
        logger.error(f"Database error: {str(e)}")
        raise
    finally:
        db.close()


# -------------------------------------------------------
# CLEAN — PURE SQL — FULL DATABASE INITIALIZATION
# -------------------------------------------------------
def init_db():
    with engine.connect() as conn:
        if not DATABASE_URL.startswith("sqlite"):
            conn.execute(sa_text("CREATE EXTENSION IF NOT EXISTS vector;"))

        # ------------------- USERS -----------------------
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'User' CHECK (role IN ('Admin', 'User', 'admin', 'user')),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_deleted BOOLEAN DEFAULT FALSE
        );
        """))

        # ------------------- COLLECTIONS -----------------------
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS collections (
            id UUID PRIMARY KEY,
            user_id UUID REFERENCES users(id),
            collection_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            is_deleted BOOLEAN DEFAULT FALSE,
            chat_title VARCHAR(255),
            summary TEXT,
            summary_generated_at TIMESTAMP,
            summary_source_count INTEGER DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """))

        # ------------------- DOCUMENTS -----------------------
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS documents (
            id UUID PRIMARY KEY,
            collection_id UUID REFERENCES collections(id),
            user_id UUID REFERENCES users(id),
            file_name TEXT NOT NULL,
            source_url TEXT,
            file_type TEXT NOT NULL,
            chunk_count INT DEFAULT 0,
            is_deleted BOOLEAN DEFAULT FALSE,
            file_path TEXT,
            uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """))

        # ------------------- CHUNKS -----------------------
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS chunks (
            id UUID PRIMARY KEY,
            document_id UUID REFERENCES documents(id),
            collection_id UUID REFERENCES collections(id),
            user_id UUID REFERENCES users(id),
            content TEXT,
            vector vector(3072),
            source_file TEXT,
            source_type TEXT,
            page_number INT,
            chunk_index INT,
            start_char INT,
            end_char INT,
            metadata JSONB,
            embedding_model TEXT,
            is_deleted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """))

        # ------------------- QUERIES -----------------------
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS queries (
            id UUID PRIMARY KEY,
            user_id UUID REFERENCES users(id),
            collection_id UUID REFERENCES collections(id),
            query_text TEXT,
            response_text TEXT,
            sources_used JSONB,
            reference_map JSONB,
            is_deleted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """))

        # ------------------- RAGAS EVALUATIONS -----------------------
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ragas_evaluations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            query_id UUID REFERENCES queries(id) ON DELETE CASCADE,
            faithfulness FLOAT,
            answer_relevancy FLOAT,
            context_precision FLOAT,
            context_recall FLOAT,
            contexts_count INT,
            eval_duration_seconds FLOAT,
            evaluated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT unique_query_evaluation UNIQUE (query_id)
        );
        """))


        # ------------------- MEMORY SESSIONS -----------------------
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS memory_sessions (
            id UUID PRIMARY KEY,
            user_id UUID REFERENCES users(id),
            session_id UUID NOT NULL,
            summary_text TEXT,
            context_state JSONB,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """))

        # ------------------- AUDIO FILES -----------------------
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS audio_files (
            id UUID PRIMARY KEY,
            user_id UUID REFERENCES users(id),
            document_id UUID REFERENCES documents(id),
            audio_url TEXT NOT NULL,
            transcription_text TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """))

        # ------------------- ADMINS -----------------------
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS admins (
            id UUID PRIMARY KEY,
            name TEXT NOT NULL,
            email_id TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('Admin', 'Super Admin')),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """))

        # ------------------- SYSTEM LOGS -----------------------
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id BIGSERIAL PRIMARY KEY,
            user_id UUID,
            event_type TEXT,
            details JSONB,
            timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """))

        # ------------------- LANGGRAPH KEY-VALUE STORE -----------------------
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS lg_kv_store (
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            value JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (namespace, key)
        );
        """))

        # ------------------- LANGGRAPH EMBEDDINGS -----------------------
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS lg_embeddings (
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            embedding vector(1536),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(namespace, key)
        );
        """))
        
        # conn.execute(text("""
        #     ALTER TABLE documents 
        #     ADD COLUMN file_path VARCHAR(500);
        #     """))

        # ------------------- GENERIC STORE TABLE -----------------------
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS store (
            prefix TEXT NOT NULL,
            key TEXT NOT NULL,
            value JSONB NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP,
            ttl_minutes INT,
            PRIMARY KEY (prefix, key)
        );
        """))

        conn.commit()

    print("[OK] Database initialized - all tables created cleanly (including RAGAs evaluations).\n")