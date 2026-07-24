import os
import json
import logging
from typing import Dict, Any, Optional
from openai import OpenAI
from pathlib import Path
from services.doc_processor import DocumentProcessor

logger = logging.getLogger(__name__)

# Reference answer storage directory
REFERENCE_DIR = "reference_answers"
os.makedirs(REFERENCE_DIR, exist_ok=True)

class ReferenceGenerator:
    def __init__(self):
        self.processor = DocumentProcessor()
        # Initialize OpenAI client using standard environment variable
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def generate_reference_summary(self, file_path: str, document_id: str) -> str:
        """
        Extracts full text of the document, generates a gold summary using the LLM,
        and caches the result to reference_answers/{document_id}.json.
        """
        cache_file = os.path.join(REFERENCE_DIR, f"{document_id}.json")
        
        # Check if already cached
        if os.path.exists(cache_file):
            logger.info(f"✓ Found cached reference summary for {document_id}")
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("reference_summary", "")
            except Exception as e:
                logger.warning(f"Failed to read cached summary: {e}. Regenerating...")

        logger.info(f"📝 Extracting text from {file_path} for gold summary...")
        
        # Extract text via existing DocumentProcessor pipeline (handles OCR, PPTX, DOCX, etc.)
        chunks = self.processor.process_document(file_path)
        if not chunks:
            raise ValueError(f"No text extracted from document {file_path}")
            
        full_text = "\n\n".join([c.content for c in chunks])
        
        # Limit text length to prevent context limit errors during reference generation
        # Let's truncate at 60,000 characters (approx. 15,000 tokens)
        max_chars = 60000
        if len(full_text) > max_chars:
            logger.info(f"Truncating document text from {len(full_text)} to {max_chars} characters for prompt size safety.")
            full_text = full_text[:max_chars] + "\n\n...[Truncated for length]..."

        logger.info("🤖 Querying LLM to generate gold reference summary...")
        
        system_instruction = (
            "You are an expert document analyst.\n"
            "Requirements:\n"
            "1. Cover every major section of the document.\n"
            "2. Cover every RAG architecture mentioned in the document (specifically look for: Standard RAG, DeepRAG, MA-RAG, Corrective RAG, Speculative RAG, Fusion RAG, RAG-Gym, Modular RAG, SAM-RAG).\n"
            "3. Do not omit topics.\n"
            "4. Preserve factual accuracy.\n"
            "5. Create comparative comparison tables when relevant."
        )
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # gpt-4o-mini is fast and highly accurate for summarization tasks
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": f"Here is the document content:\n\n{full_text}\n\nPlease generate the gold reference summary."}
                ],
                temperature=0.2
            )
            
            gold_summary = response.choices[0].message.content.strip()
            
            # Cache the result
            ref_payload = {
                "document_id": document_id,
                "document_name": Path(file_path).name,
                "reference_summary": gold_summary
            }
            
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(ref_payload, f, indent=2)
                
            logger.info(f"✅ Generated and cached reference summary to: {cache_file}")
            return gold_summary
            
        except Exception as e:
            logger.error(f"Failed to generate reference summary via LLM: {e}")
            raise e
