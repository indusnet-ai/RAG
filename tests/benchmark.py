import os
import sys
import json
import asyncio
import logging
from uuid import uuid4
from pathlib import Path
from sqlalchemy import text

# Add root folder to path so imports work correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db import SessionLocal
from services.doc_processor import DocumentProcessor
from services.embedding_generator import EmbeddingGenerator
from services.rag_generation import RAGGenerator
from reference_generator import ReferenceGenerator
from evaluation.evaluator import RAGEvaluator
from evaluation.metrics import save_evaluation_result

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_benchmark():
    db = SessionLocal()
    ref_generator = ReferenceGenerator()
    evaluator = RAGEvaluator()
    embedder = EmbeddingGenerator()
    rag_generator = RAGGenerator(embedding_generator=embedder, db=db)
    
    logger.info("🏁 Starting RAG Evaluation Benchmark...")

    # Step 1: Ensure we have at least one user, collection, and document in the database
    # Check for users
    user_row = db.execute(text("SELECT id, email FROM users LIMIT 1;")).fetchone()
    if not user_row:
        logger.error("❌ No users found in database. Run register_admin_user.py first.")
        db.close()
        return

    user_id = str(user_row.id)
    user_email = user_row.email
    logger.info(f"👤 Using user: {user_email} ({user_id})")

    # Check for collections
    col_row = db.execute(text("SELECT id, collection_name FROM collections WHERE user_id = :uid LIMIT 1;"), {"uid": user_id}).fetchone()
    if not col_row:
        # Create a default collection
        collection_id = str(uuid4())
        collection_name = "eval_benchmark_collection"
        db.execute(text("""
            INSERT INTO collections (id, user_id, collection_name, source_type, created_at)
            VALUES (:id, :uid, :name, 'pdf', CURRENT_TIMESTAMP)
        """), {"id": collection_id, "uid": user_id, "name": collection_name})
        db.commit()
        logger.info(f"📁 Created evaluation collection: {collection_name} ({collection_id})")
    else:
        collection_id = str(col_row.id)
        collection_name = col_row.collection_name
        logger.info(f"📁 Using collection: {collection_name} ({collection_id})")

    # Check for documents
    doc_row = db.execute(text("""
        SELECT id, file_name, file_path FROM documents 
        WHERE collection_id = :cid AND user_id = :uid AND (is_deleted = FALSE OR is_deleted IS NULL) LIMIT 1;
    """), {"cid": collection_id, "uid": user_id}).fetchone()

    if not doc_row:
        logger.info("🔍 No documents found in database. Scanning disk for PDFs to auto-import...")
        # Scan uploaded_files directory
        pdf_path = None
        pdf_name = None
        upload_dir = Path("uploaded_files")
        if upload_dir.exists():
            for p in upload_dir.glob("**/*.pdf"):
                pdf_path = str(p)
                pdf_name = p.name
                break
                
        if not pdf_path:
            logger.error("❌ No PDF files found in uploaded_files/ subdirectories. Please upload a PDF file first.")
            db.close()
            return
            
        logger.info(f"📥 Auto-importing PDF: {pdf_name} from {pdf_path}...")
        
        # Ingest, chunk, embed, and store in DB
        processor = DocumentProcessor()
        chunks = processor.process_document(pdf_path)
        
        for idx, chunk in enumerate(chunks):
            chunk.source_file = pdf_name
            chunk.chunk_index = idx
            
        embedded_chunks = embedder.generate_embeddings(chunks)
        document_id = str(uuid4())
        
        # Insert document record
        db.execute(text("""
            INSERT INTO documents (id, collection_id, user_id, file_name, file_type, file_path, chunk_count)
            VALUES (:id, :cid, :uid, :fname, 'pdf', :fpath, :count)
        """), {
            "id": document_id,
            "cid": collection_id,
            "uid": user_id,
            "fname": pdf_name,
            "fpath": pdf_path,
            "count": len(embedded_chunks)
        })
        
        # Insert chunks
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
                "doc": document_id,
                "cid": collection_id,
                "uid": user_id,
                "idx": c.chunk_index,
                "start": c.start_char,
                "end": c.end_char,
                "content": c.content,
                "vector": vector_str,
                "stype": c.source_type,
                "source_file": pdf_name,
                "page_num": c.page_number if hasattr(c, 'page_number') else None,
                "emb_model": "text-embedding-3-large",
                "metadata": metadata_json
            })
        db.commit()
        logger.info(f"✅ Auto-imported document {pdf_name} ({document_id}) with {len(embedded_chunks)} chunks.")
        
        doc_id = document_id
        doc_name = pdf_name
        doc_file_path = pdf_path
    else:
        doc_id = str(doc_row.id)
        doc_name = doc_row.file_name
        doc_file_path = doc_row.file_path
        logger.info(f"📄 Found active document: {doc_name} ({doc_id})")

    # Step 2: Generate Gold Reference Summary (Phase 3)
    try:
        reference_summary = ref_generator.generate_reference_summary(doc_file_path, doc_id)
        logger.info("✅ Reference gold summary loaded.")
    except Exception as e:
        logger.error(f"❌ Failed to obtain reference summary: {e}")
        db.close()
        return

    # Step 3: Ask chatbot to summarize (Phase 4)
    logger.info("🤖 Querying chatbot for summary response...")
    query = "Summarize the key points from the uploaded document"
    
    # Run synchronously
    rag_result = rag_generator.generate_response(
        query=query,
        user_id=user_id,
        collection_id=collection_id,
        selected_document_ids=[doc_id]
    )
    
    chatbot_response = rag_result.response
    logger.info(f"✓ Chatbot response received (length: {len(chatbot_response)} chars).")

    # Step 4: Extract retrieved contexts for RAGAs
    # Replicate retrieval to get exact texts
    query_vector = embedder.generate_query_embedding(query)
    search_results = rag_generator._search_chunks(
        query_text=query,
        query_vector=query_vector.tolist(),
        user_id=user_id,
        collection_id=collection_id,
        limit=15,
        selected_document_ids=[doc_id]
    )
    search_results = rag_generator._filter_to_best_document(search_results)
    contexts = [r["content"] for r in search_results]
    logger.info(f"✓ Extracted {len(contexts)} chunks as retrieval contexts.")

    # Step 5: Run full 11-metric evaluation suite (Phase 2)
    scores = await evaluator.evaluate_response(
        query=query,
        response=chatbot_response,
        contexts=contexts,
        reference=reference_summary
    )

    # Step 6: Save results and thresholds check (Phase 4 & Phase 8)
    eval_report = save_evaluation_result(
        db=db,
        document_id=doc_id,
        document_name=doc_name,
        query_text=query,
        response_text=chatbot_response,
        reference_text=reference_summary,
        scores=scores
    )

    logger.info(f"🏁 Benchmark finished with status: {eval_report['status']}")
    if eval_report['status'] == "FAILED":
        logger.warning(f"❌ Diagnostics: {eval_report['diagnostics']}")
    else:
        logger.info("🎉 All metrics passed success criteria thresholds!")
        
    db.close()

if __name__ == "__main__":
    asyncio.run(run_benchmark())
