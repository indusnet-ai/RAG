# [file name]: embedding_generator.py
import logging
from typing import List, Dict, Any, Optional
import numpy as np
from dataclasses import dataclass

from services.metrics import track_external_service_failure
from services.model_manager import get_model_manager
from services.doc_processor import DocumentChunk

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EmbeddedChunk:
    """Document chunk with its embedding vector"""
    chunk: DocumentChunk
    embedding: np.ndarray
    embedding_model: str
    embedding_provider: str  # Track which provider was used

    def to_vector_db_format(self) -> Dict[str, Any]:
        return {
            'id': self.chunk.chunk_id,
            'vector': self.embedding.tolist(),
            'content': self.chunk.content,
            'source_file': self.chunk.source_file,
            'source_type': self.chunk.source_type,
            'page_number': self.chunk.page_number,
            'chunk_index': self.chunk.chunk_index,
            'start_char': self.chunk.start_char,
            'end_char': self.chunk.end_char,
            'metadata': self.chunk.metadata,
            'embedding_model': self.embedding_model,
            'embedding_provider': self.embedding_provider
        }


class EmbeddingGenerator:
    """
    Embedding generator with automatic fallback between multiple providers
    """
    def __init__(self, config_path: str = "config.yaml"):
        self.model_manager = get_model_manager(config_path)
        self.current_embedding_model = None
        self.current_provider = None
        self.embedding_dim = None
        
        # Try to initialize, but don't fail if test embedding fails
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize embedding model with graceful fallback"""
        try:
            # Get the current embedding provider and config
            self.current_provider = self.model_manager.get_current_embedding_provider()
            config = self.model_manager.get_embedding_config(self.current_provider)
            
            self.current_embedding_model = config.get('model_name', '')
            self.embedding_dim = config.get('dimension')
            
            # Try to get actual dimension from a test embedding
            try:
                test_embeddings = self.model_manager.get_embeddings(["test"])
                if test_embeddings and len(test_embeddings) > 0:
                    actual_dim = len(test_embeddings[0])
                    
                    # Update dimension if different from config or not set
                    if self.embedding_dim is None or self.embedding_dim != actual_dim:
                        self.embedding_dim = actual_dim
                        logger.info(f"Auto-detected embedding dimension: {self.embedding_dim}")
                    
                    logger.info(f"Embedding model initialized successfully")
                    logger.info(f"Provider: {self.current_provider}, Model: {self.current_embedding_model}")
                    logger.info(f"Embedding dimension: {self.embedding_dim}")
                else:
                    raise ValueError("Failed to get test embedding")
                    
            except Exception as test_error:
                logger.warning(f"Test embedding failed during init: {test_error}")
                # If dimension not set, use a reasonable default based on provider
                if self.embedding_dim is None:
                    if self.current_provider == 'openai':
                        self.embedding_dim = 3072
                    elif self.current_provider == 'fastembed':
                        self.embedding_dim = 1024  # Default for BAAI models
                    else:
                        self.embedding_dim = 768  # General default
                    
                    logger.info(f"Using default dimension {self.embedding_dim} for {self.current_provider}")
                
        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {str(e)}")
            # Don't raise - let it fail gracefully and use defaults
            self.current_provider = 'unknown'
            self.current_embedding_model = 'unknown'
            self.embedding_dim = 768
    
    def generate_embeddings(self, chunks: List[DocumentChunk]) -> List[EmbeddedChunk]:
        """Generate embeddings for document chunks with fallback"""
        # Filter out empty or whitespace-only chunks
        chunks = [chunk for chunk in chunks if chunk.content and chunk.content.strip()]
        if not chunks:
            return []

        logger.info(f"Generating embeddings for {len(chunks)} chunks")
        try:
            texts = [chunk.content for chunk in chunks]
            
            # Use ModelManager for automatic fallback
            embeddings = self.model_manager.get_embeddings(texts)
            
            embedded_chunks = []
            for chunk, embedding in zip(chunks, embeddings):
                embedded_chunk = EmbeddedChunk(
                    chunk=chunk,
                    embedding=np.array(embedding, dtype=np.float32),
                    embedding_model=self.current_embedding_model,
                    embedding_provider=self.current_provider
                )
                embedded_chunks.append(embedded_chunk)

            logger.info(f"Successfully generated {len(embedded_chunks)} embeddings")
            logger.info(f"Provider used: {self.current_provider}, Model: {self.current_embedding_model}")
            return embedded_chunks

        except Exception as e:
            track_external_service_failure("openai")  # ✅ ADD THIS LINE
            logger.error(f"Error generating embeddings: {str(e)}")
            raise
    
    def generate_query_embedding(self, query_text: str) -> np.ndarray:
        """Generate embedding for a single query string with fallback"""
        try:
            embeddings = self.model_manager.get_embeddings([query_text])
            embedding = np.array(embeddings[0], dtype=np.float32)
            
            # Update current provider info
            self.current_provider = self.model_manager.get_current_embedding_provider()
            config = self.model_manager.get_embedding_config(self.current_provider)
            self.current_embedding_model = config.get('model_name', '')
            
            logger.info(f"Query embedding generated using {self.current_provider} ({self.current_embedding_model})")
            return embedding
        except Exception as e:
            track_external_service_failure("openai")  # ✅ ADD THIS LINE
            logger.error(f"Error generating query embedding: {str(e)}")
            raise
    
    def get_embedding_dimension(self) -> int:
        """Get current embedding dimension"""
        return self.embedding_dim or 768
    
    def get_current_provider(self) -> str:
        """Get the current embedding provider"""
        return self.current_provider or 'unknown'
    
    def get_current_model(self) -> str:
        """Get the current embedding model name"""
        return self.current_embedding_model or 'unknown'


if __name__ == "__main__":
    # Test the embedding generator
    embedding_generator = EmbeddingGenerator()
    
    try:
        # Test with sample query
        query = "What is machine learning?"
        query_embedding = embedding_generator.generate_query_embedding(query)
        print(f"✅ Query embedding shape: {query_embedding.shape}")
        print(f"✅ Provider used: {embedding_generator.get_current_provider()}")
        print(f"✅ Model used: {embedding_generator.get_current_model()}")
        print(f"✅ Dimension: {embedding_generator.get_embedding_dimension()}")
        
    except Exception as e:
        print(f"Error: {e}")
        print(f"Current provider: {embedding_generator.get_current_provider()}")
        print(f"Current dimension: {embedding_generator.get_embedding_dimension()}")