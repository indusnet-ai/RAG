import os
import sys
import json
import asyncio
import logging
from uuid import uuid4
from pathlib import Path
from sqlalchemy import text

# Add root folder to path so imports work correctly
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

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
    
    logger.info("🏁 Starting Production-Grade RAG Evaluation Benchmark (Phase 5)...")

    # Step 1: Ensure we have the target document in the database
    doc_row = db.execute(text("""
        SELECT id, file_name, file_path, collection_id, user_id FROM documents 
        WHERE file_name = 'rag.pdf' AND (is_deleted = FALSE OR is_deleted IS NULL) LIMIT 1;
    """)).fetchone()

    if not doc_row:
        logger.error("❌ Document 'rag.pdf' not found in database. Reprocess it first.")
        db.close()
        return

    doc_id = str(doc_row.id)
    doc_name = doc_row.file_name
    doc_file_path = doc_row.file_path
    collection_id = str(doc_row.collection_id)
    user_id = str(doc_row.user_id)

    logger.info(f"👤 Using user: {user_id}")
    logger.info(f"📁 Using collection: {collection_id}")
    logger.info(f"📄 Found active document: {doc_name} ({doc_id})")

    # Step 2: Generate Gold Reference Summary (Phase 4)
    try:
        reference_summary = ref_generator.generate_reference_summary(doc_file_path, doc_id)
        logger.info("✅ Reference gold summary loaded.")
    except Exception as e:
        logger.error(f"❌ Failed to obtain reference summary: {e}")
        db.close()
        return

    # Step 3: Query chatbot for summary (Phase 5)
    logger.info("🤖 Querying chatbot for summary response...")
    query = "Summarize the key points from the uploaded document"
    
    rag_result = rag_generator.generate_response(
        query=query,
        user_id=user_id,
        collection_id=collection_id,
        selected_document_ids=[doc_id]
    )
    
    chatbot_response = rag_result.response
    logger.info(f"✓ Chatbot response received (length: {len(chatbot_response)} chars).")

    # Step 4: Extract retrieved contexts for evaluation
    query_vector = embedder.generate_query_embedding(query)
    search_results = rag_generator._search_chunks(
        query_text=query,
        query_vector=query_vector.tolist(),
        user_id=user_id,
        collection_id=collection_id,
        limit=200,
        selected_document_ids=[doc_id]
    )
    search_results = rag_generator._filter_to_best_document(search_results)
    contexts = [r["content"] for r in search_results]
    logger.info(f"✓ Extracted {len(contexts)} chunks as retrieval contexts.")

    # Step 5: Run full 13-metric evaluation suite (Phase 2 & Phase 3 & Phase 11)
    scores = await evaluator.evaluate_response(
        query=query,
        response=chatbot_response,
        contexts=contexts,
        reference=reference_summary
    )

    # Step 6: Save results and thresholds check (Phase 5 & Phase 13)
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
