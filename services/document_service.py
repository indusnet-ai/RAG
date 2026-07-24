from services.doc_processor import DocumentProcessor
from uuid import uuid4
from typing import List
import os

class DocumentService:
    def __init__(self, max_ocr_workers: int = 5):
        """
        Initialize DocumentService with parallel OCR support
        
        Args:
            max_ocr_workers: Number of parallel workers for OCR processing (default: 5)
                           - Higher = faster but more API calls/memory
                           - Recommended: 4-8 workers
        """
        self.processor = DocumentProcessor(max_workers=max_ocr_workers)

    def process_uploaded_file(self, temp_path: str, original_name: str):
        """
        Process uploaded file and return chunks
        
        Args:
            temp_path: Path to temporary file
            original_name: Original filename
            
        Returns:
            List of DocumentChunk instances
        """
        chunks = self.processor.process_document(temp_path)
        
        # Ensure chunks have correct file name and indices
        for idx, chunk in enumerate(chunks):
            chunk.source_file = original_name
            chunk.chunk_index = idx
        
        return chunks
    
    def process_pasted_text(self, text_content: str, text_title: str = "Pasted Text"):
        """
        Process pasted text directly.
        
        Args:
            text_content: Text to process
            text_title: Title for the text
            
        Returns:
            List of DocumentChunk instances
        """
        chunks = self.processor._create_chunks_from_text(
            text=text_content,
            source_file=text_title,
            source_type='text',
            page_number=None,
            additional_metadata={
                'input_method': 'paste',
                'character_count': len(text_content)
            }
        )
        
        for idx, chunk in enumerate(chunks):
            chunk.chunk_index = idx
            chunk.source_file = text_title
        
        return chunks