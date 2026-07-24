# reprocess_and_reembed.py
import os
import json
import logging
from sqlalchemy import text
from db import SessionLocal
from services.doc_processor import DocumentProcessor
from services.embedding_generator import EmbeddingGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    db = SessionLocal()
    embedder = EmbeddingGenerator()
    # Initialize with default 5 workers for OCR
    processor = DocumentProcessor(max_workers=5)

    try:
        # Fetch all documents
        doc_rows = db.execute(text("SELECT id, collection_id, user_id, file_name, file_path FROM documents")).fetchall()
        logger.info(f"Found {len(doc_rows)} documents in the database.")

        for doc in doc_rows:
            doc_id = doc.id
            collection_id = doc.collection_id
            user_uuid = doc.user_id
            file_name = doc.file_name
            file_path = doc.file_path

            logger.info(f"Processing document: {file_name} (ID: {doc_id}) from path: {file_path}")

            if not file_path or not os.path.exists(file_path):
                logger.warning(f"File path {file_path} does not exist. Skipping.")
                continue

            # Delete old chunks for this document
            logger.info(f"Deleting old chunks for document {doc_id}...")
            db.execute(text("DELETE FROM chunks WHERE document_id = :doc_id"), {"doc_id": doc_id})

            # Process document again using updated DocumentProcessor (fixed boilerplate condition)
            logger.info(f"Extracting chunks from {file_path}...")
            chunks = processor.process_document(file_path)

            # Ensure chunks have correct file name and indices
            for idx, chunk in enumerate(chunks):
                chunk.source_file = file_name
                chunk.chunk_index = idx

            logger.info(f"Extracted {len(chunks)} chunks. Generating embeddings...")
            embedded_chunks = embedder.generate_embeddings(chunks)
            logger.info(f"Generated {len(embedded_chunks)} embeddings. Storing in DB...")

            # Insert chunks
            from uuid import uuid4
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
                    "doc": doc_id,
                    "cid": collection_id,
                    "uid": user_uuid,
                    "idx": c.chunk_index,
                    "start": c.start_char,
                    "end": c.end_char,
                    "content": c.content,
                    "vector": vector_str,
                    "stype": c.source_type,
                    "source_file": file_name,
                    "page_num": c.page_number if hasattr(c, 'page_number') else None,
                    "emb_model": "text-embedding-3-large",
                    "metadata": metadata_json
                })

            # Update document chunk count
            db.execute(text("""
                UPDATE documents
                SET chunk_count = :count
                WHERE id = :doc_id
            """), {"count": len(embedded_chunks), "doc_id": doc_id})

            logger.info(f"Successfully re-processed and saved document {doc_id}.")

        db.commit()
        logger.info("Transaction committed successfully.")

    except Exception as e:
        db.rollback()
        logger.error(f"Error during reprocess: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
