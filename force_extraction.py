import logging
import os
# Adjust the import paths according to your project structure
from services.rag_generation import RAGGenerator
from services.embedding_generator import EmbeddingGenerator
from context_builder import map_reduce_extractions

# Import your DB session creator – replace with actual module if different
from db import SessionLocal

# Added import for SQL text construction
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



def main() -> None:
    """Run a forced Map‑Reduce extraction over **all** chunks of the source PDF.

    The script:
    1. Instantiates the RAGGenerator with a fresh DB session.
    2. Generates an embedding for a generic extraction prompt.
    3. Retrieves *every* chunk belonging to the collection (using a very high limit).
    4. Feeds the complete chunk list into ``map_reduce_extractions`` which forces the LLM
       to read each chunk individually (Map step) and then synthesises a final summary
       (Reduce step).
    5. Prints the final response – this will contain the extracted facts for all nine
       architectures. If any architecture is missing, the response will include a warning
       from the prompt logic defined in ``rag_generation.py``.
    """
    # ---------------------------------------------------------------------
    # 1️⃣ Initialise services
    # ---------------------------------------------------------------------
    db = SessionLocal()
    embedding_generator = EmbeddingGenerator()
    rag = RAGGenerator(embedding_generator=embedding_generator, db=db)
    rag.enable_hybrid_search = False  # Disable hybrid to avoid DB transaction errors

    # ---------------------------------------------------------------------
    # 2️⃣ Create a generic query that triggers the extraction prompt
    # ---------------------------------------------------------------------
    extraction_query = (
        "Extract every RAG architecture described in the document, "
        "including name, pipeline, tips and use‑cases."
    )

    # The embedding generator used by RAGGenerator expects a list of strings –
    # we reuse its private helper for consistency. If the API differs, adjust
    # the call accordingly.
    # Generate embedding for the extraction query using the embedding generator
    query_vector = rag.embedding_generator.generate_query_embedding(extraction_query)

    # Close the previous DB session (it may be in a failed transaction state)
    try:
        db.close()
    except Exception:
        pass
    # Re‑open a fresh session for generation
    fresh_db = SessionLocal()
    rag = RAGGenerator(embedding_generator=embedding_generator, db=fresh_db)
    rag.enable_hybrid_search = False  # Ensure hybrid is disabled

    try:
        # Filter by document_id and collection_id
        simple_query = text("""
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
                c.metadata
            FROM chunks c
            WHERE (c.is_deleted = FALSE OR c.is_deleted IS NULL)
        """)
        rows = rag.db.execute(simple_query).fetchall()

        # Convert to list of dicts matching expected format
        all_chunks = []
        for row in rows:
            all_chunks.append({
                "id": row.id,
                "content": row.content,
                "citation": {
                    "source_file": row.source_file or "Unknown",
                    "source_type": row.source_type or "document",
                    "page_number": row.page_number,
                    "chunk_index": row.chunk_index,
                    "start_char": row.start_char,
                    "end_char": row.end_char,
                    "document_id": str(row.document_id) if row.document_id else None,
                },
                "metadata": row.metadata,
                "score": None,
            })
    except Exception as e:
        logger.error(f"Failed to retrieve chunks: {e}")
        raise


    logger.info(f"Retrieved {len(all_chunks)} chunks for forced extraction.")

    # ---------------------------------------------------------------------
    # 4️⃣ Run the Map‑Reduce flow. ``batch_size`` can be tuned – a value of 5
    #    balances LLM token limits with the desire to keep each map call small.
    # ---------------------------------------------------------------------
    final_result = map_reduce_extractions(
        rag_generator=rag,
        query=extraction_query,
        chunks=all_chunks,
        batch_size=5,
    )

    # Optional: Persist the output for later inspection
    output_path = os.path.join(os.getcwd(), "extracted_architectures.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_result.response)
    logger.info(f"Extraction saved to {output_path}")

    # ---------------------------------------------------------------------
    # 5️⃣ Output – the ``response`` attribute holds the synthesized markdown.
    # ---------------------------------------------------------------------
    print("\n=== FINAL MAP-REDUCE SUMMARY ===\n")
    try:
        print(final_result.response)
    except UnicodeEncodeError:
        try:
            print(final_result.response.encode('ascii', errors='replace').decode('ascii'))
        except Exception as e:
            print(f"<Could not print final result due to encoding error: {e}>")


if __name__ == "__main__":
    main()
