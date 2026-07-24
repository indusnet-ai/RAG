import unittest
import sys
import os
import tempfile
import json
from pathlib import Path

# Add root folder to path so imports work correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from reference_generator import ReferenceGenerator, REFERENCE_DIR

class TestSummaryGeneration(unittest.TestCase):
    def setUp(self):
        self.generator = ReferenceGenerator()
        
        # Create a temporary txt file for testing
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_file_path = os.path.join(self.test_dir.name, "test_doc.txt")
        
        self.doc_content = (
            "The Advanced RAG chatbot is an AI application. It is designed to run in dark mode. "
            "It supports ingestion from PDFs, Word documents, YouTube videos, and Web scraping. "
            "It uses hybrid search and FlashRank reranking to optimize context relevancy before "
            "sending queries to OpenAI GPT-4 or local Ollama servers."
        )
        
        with open(self.test_file_path, "w", encoding="utf-8") as f:
            f.write(self.doc_content)
            
        self.doc_id = "test_summary_doc_001"

    def tearDown(self):
        self.test_dir.cleanup()
        # Clean up cached file if created
        cache_file = os.path.join(REFERENCE_DIR, f"{self.doc_id}.json")
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
            except:
                pass

    def test_generate_and_cache_summary(self):
        """Test that a summary can be generated and cached correctly."""
        summary = self.generator.generate_reference_summary(self.test_file_path, self.doc_id)
        self.assertIsNotNone(summary)
        self.assertTrue(len(summary) > 0)
        
        # Check cache file exists
        cache_file = os.path.join(REFERENCE_DIR, f"{self.doc_id}.json")
        self.assertTrue(os.path.exists(cache_file))
        
        # Verify cache file structure
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["document_id"], self.doc_id)
            self.assertEqual(data["document_name"], "test_doc.txt")
            self.assertEqual(data["reference_summary"], summary)

if __name__ == '__main__':
    unittest.main()
