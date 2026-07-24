import unittest
import sys
import os

# Add root folder to path so imports work correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db import SessionLocal
from services.embedding_generator import EmbeddingGenerator
from services.hybrid_search import search_chunks_hybrid

class TestRetrieval(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.embedder = EmbeddingGenerator()

    def tearDown(self):
        self.db.close()

    def test_database_connection(self):
        """Test that the database is reachable and returns results."""
        try:
            result = self.db.execute(text("SELECT 1;"))
            val = result.scalar()
            self.assertEqual(val, 1)
        except Exception as e:
            # Import text if not already loaded
            from sqlalchemy import text
            result = self.db.execute(text("SELECT 1;"))
            val = result.scalar()
            self.assertEqual(val, 1)

    def test_embedding_generation(self):
        """Test that the embedding generator successfully vectorizes query text."""
        query = "What is Retrieval-Augmented Generation?"
        vector = self.embedder.generate_query_embedding(query)
        self.assertIsNotNone(vector)
        # Ensure dimensions match expected size (3072 for text-embedding-3-large, or 1024 for BAAI fallback)
        self.assertTrue(len(vector) in [1024, 3072])

if __name__ == '__main__':
    unittest.main()
