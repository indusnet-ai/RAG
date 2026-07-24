# [file name]: model_manager.py
# [file content begin]
import os
import yaml
import logging
import time
from typing import Optional, Dict, Any, List
from pathlib import Path
from openai import OpenAI
import requests
import json
from langsmith import traceable, Client
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModelManager:
    """Manages AI model providers with priority-based fallback"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.current_llm_provider = None
        self.current_embedding_provider = None
        self.openai_client = None
        self.ollama_base_url = None
        self.fastembed_model = None
        self.llm_models = []
        self.embedding_models = []
        self._initialize_models()
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {config_path}")
            return config
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise
    
    def _initialize_models(self):
        """Initialize all model providers with priority sorting"""
        try:
            # Sort LLM models by priority
            self.llm_models = [
                self.config['models']['primary_llm'],
                self.config['models']['fallback_llm']
            ]
            self.llm_models.sort(key=lambda x: x.get('priority', 999))
            
            # Sort embedding models by priority
            self.embedding_models = [
                self.config['embeddings']['primary_embedding'],
                self.config['embeddings']['fallback_embedding']
            ]
            self.embedding_models.sort(key=lambda x: x.get('priority', 999))
            
            # Initialize OpenAI client if configured
            openai_llm = next((m for m in self.llm_models if m['provider'] == 'openai'), None)
            openai_embedding = next((m for m in self.embedding_models if m['provider'] == 'openai'), None)
            
            if openai_llm or openai_embedding:
                api_key_env = (openai_llm or openai_embedding)['api_key_env']
                openai_key = os.getenv(api_key_env)
                if openai_key:
                    self.openai_client = OpenAI(api_key=openai_key)
                    logger.info("OpenAI client initialized")
                else:
                    logger.warning(f"OpenAI API key not found in environment variable: {api_key_env}")
            
            # Initialize Ollama if configured
            ollama_llm = next((m for m in self.llm_models if m['provider'] == 'ollama'), None)
            
            if ollama_llm:
                self.ollama_base_url = ollama_llm['base_url']
                if self._test_ollama_connection():
                    logger.info("Ollama connection verified")
                else:
                    logger.warning("Ollama not available at configured URL")
            
            # Initialize FastEmbed if configured (lazy loading)
            fastembed_model = next((m for m in self.embedding_models if m['provider'] == 'fastembed'), None)
            if fastembed_model:
                logger.info(f"FastEmbed configured: {fastembed_model['model_name']}")
                # Lazy initialization - will load when first used
            
            # Set current providers based on availability
            self._set_current_providers()
            
        except Exception as e:
            logger.error(f"Error initializing models: {e}")
            raise
    
    def _set_current_providers(self):
        """Set current providers based on availability and priority"""
        # Set LLM provider
        for model in self.llm_models:
            if self._is_provider_available(model):
                self.current_llm_provider = model['provider']
                logger.info(f"Using LLM provider: {model['provider']} with model: {model['model_name']}")
                break
        
        # Set embedding provider
        for model in self.embedding_models:
            if self._is_provider_available(model):
                self.current_embedding_provider = model['provider']
                logger.info(f"Using embedding provider: {model['provider']} with model: {model['model_name']}")
                break
    
    def _is_provider_available(self, model_config: Dict[str, Any]) -> bool:
        """Check if a provider is available"""
        provider = model_config['provider']
        
        if provider == 'openai':
            return self.openai_client is not None
        elif provider == 'ollama':
            return self.ollama_base_url is not None and self._test_ollama_connection()
        elif provider == 'fastembed':
            return True  # FastEmbed is always available (local)
        return False
    
    def _test_ollama_connection(self) -> bool:
        """Test if Ollama is running and accessible"""
        try:
            response = requests.get(f"{self.ollama_base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def _initialize_fastembed(self, model_name: str):
        """Lazy initialization of FastEmbed model"""
        if self.fastembed_model is None:
            try:
                from fastembed import TextEmbedding
                self.fastembed_model = TextEmbedding(model_name=model_name)
                logger.info(f"FastEmbed model '{model_name}' initialized")
            except Exception as e:
                logger.error(f"Failed to initialize FastEmbed: {e}")
                raise
    
    # def get_chat_completion(self, messages: list, stream: bool = False, **kwargs):
    @traceable(run_type="llm", name="rag_llm_call")
    def get_chat_completion(self, messages: list, stream: bool = False, **kwargs):

        """Get chat completion with automatic fallback"""
        retry_config = self.config.get('retry_config', {})
        max_retries = retry_config.get('max_retries', 3)
        
        for attempt in range(max_retries):
            try:
                current_model = self._get_current_llm_model()
                
                if current_model['provider'] == "openai":
                    return self._get_openai_completion(messages, stream, current_model, **kwargs)
                elif current_model['provider'] == "ollama":
                    return self._get_ollama_completion(messages, stream, current_model, **kwargs)
                
            except Exception as e:
                error_msg = str(e).lower()
                
                # Check if we should fallback
                should_fallback = (
                    retry_config.get('fallback_on_quota_error', True) and 
                    any(keyword in error_msg for keyword in ['insufficient_quota', 'rate_limit', 'quota', 'billing'])
                ) or (
                    retry_config.get('fallback_on_missing_key', True) and
                    'api key' in error_msg
                ) or (
                    retry_config.get('fallback_on_connection_error', True) and
                    any(keyword in error_msg for keyword in ['connection', 'timeout', 'failed', 'not found'])
                )
                
                if should_fallback and attempt < max_retries - 1:
                    logger.warning(f"LLM attempt {attempt + 1} failed: {e}")
                    logger.info("Trying next provider...")
                    self._fallback_to_next_llm_provider()
                    time.sleep(retry_config.get('retry_delay', 1))
                    continue
                
                # Re-raise if no more retries
                raise
        
        # This should not be reached if max_retries > 0
        raise Exception("Max retries exceeded for LLM")
    
    def _get_current_llm_model(self) -> Dict[str, Any]:
        """Get current LLM model configuration"""
        for model in self.llm_models:
            if model['provider'] == self.current_llm_provider:
                return model
        raise ValueError(f"No LLM model found for provider: {self.current_llm_provider}")
    
    def _get_current_embedding_model(self) -> Dict[str, Any]:
        """Get current embedding model configuration"""
        for model in self.embedding_models:
            if model['provider'] == self.current_embedding_provider:
                return model
        raise ValueError(f"No embedding model found for provider: {self.current_embedding_provider}")
    
    def _fallback_to_next_llm_provider(self):
        """Switch to next available LLM provider"""
        current_index = next((i for i, m in enumerate(self.llm_models) 
                            if m['provider'] == self.current_llm_provider), 0)
        
        for next_model in self.llm_models[current_index + 1:]:
            if self._is_provider_available(next_model):
                self.current_llm_provider = next_model['provider']
                logger.info(f"Fell back to LLM provider: {next_model['provider']}")
                return
        
        raise Exception("No fallback LLM providers available")
    
    def _fallback_to_next_embedding_provider(self):
        """Switch to next available embedding provider"""
        current_index = next((i for i, m in enumerate(self.embedding_models) 
                            if m['provider'] == self.current_embedding_provider), 0)
        
        for next_model in self.embedding_models[current_index + 1:]:
            if self._is_provider_available(next_model):
                self.current_embedding_provider = next_model['provider']
                logger.info(f"Fell back to embedding provider: {next_model['provider']}")
                return
        
        raise Exception("No fallback embedding providers available")
    
    def _get_openai_completion(self, messages: list, stream: bool, model_config: Dict[str, Any], **kwargs):
        """Get completion from OpenAI"""
        if not self.openai_client:
            raise ValueError("OpenAI client not initialized")
        
        params = {
            'model': kwargs.get('model', model_config['model_name']),
            'messages': messages,
            'temperature': kwargs.get('temperature', model_config.get('temperature', 0.3)),
            'max_tokens': kwargs.get('max_tokens', model_config.get('max_tokens', 16000)),
            'stream': stream
        }
        
        logger.info(f"Using OpenAI model: {params['model']}")
        return self.openai_client.chat.completions.create(**params)
    
    def _get_ollama_completion(self, messages: list, stream: bool, model_config: Dict[str, Any], **kwargs):
        """Get completion from Ollama"""
        payload = {
            'model': kwargs.get('model', model_config['model_name']),
            'messages': messages,
            'stream': stream,
            'options': {
                'temperature': kwargs.get('temperature', model_config.get('temperature', 0.3)),
                'num_predict': kwargs.get('max_tokens', model_config.get('max_tokens', 4096))
            }
        }
        
        logger.info(f"Using Ollama model: {payload['model']}")
        
        url = f"{self.ollama_base_url}/api/chat"
        
        if stream:
            return self._ollama_stream(payload, url)
        else:
            return self._ollama_non_stream(payload, url)
    
    def _ollama_stream(self, payload, url):
        """Handle Ollama streaming response"""
        with requests.post(url, json=payload, stream=True) as response:
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)
                    
                    # Create OpenAI-compatible response format
                    class StreamChunk:
                        def __init__(self, content):
                            self.content = content
                    
                    if 'message' in chunk and 'content' in chunk['message']:
                        yield StreamChunk(chunk['message']['content'])
    
    def _ollama_non_stream(self, payload, url):
        """Handle Ollama non-streaming response"""
        response = requests.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        
        # Create OpenAI-compatible response format
        class CompletionChoice:
            def __init__(self, content):
                self.message = type('Message', (), {'content': content})()
        
        class Completion:
            def __init__(self, content):
                self.choices = [CompletionChoice(content)]
        
        content = result.get('message', {}).get('content', '')
        return Completion(content)
    
    def get_embeddings(self, texts: list, model: Optional[str] = None):
        """Get embeddings with automatic fallback"""
        retry_config = self.config.get('retry_config', {})
        max_retries = retry_config.get('max_retries', 3)
        
        for attempt in range(max_retries):
            try:
                current_model = self._get_current_embedding_model()
                
                if current_model['provider'] == "openai":
                    return self._get_openai_embeddings(texts, current_model)
                elif current_model['provider'] == "ollama":
                    return self._get_ollama_embeddings(texts, current_model)
                elif current_model['provider'] == "fastembed":
                    return self._get_fastembed_embeddings(texts, current_model)
                
            except Exception as e:
                error_msg = str(e).lower()
                
                # Check if we should fallback
                should_fallback = (
                    retry_config.get('fallback_on_quota_error', True) and 
                    any(keyword in error_msg for keyword in ['insufficient_quota', 'rate_limit', 'quota', 'billing'])
                ) or (
                    retry_config.get('fallback_on_missing_key', True) and
                    'api key' in error_msg
                ) or (
                    retry_config.get('fallback_on_connection_error', True) and
                    any(keyword in error_msg for keyword in ['connection', 'timeout', 'failed', 'not found'])
                )
                
                if should_fallback and attempt < max_retries - 1:
                    logger.warning(f"Embedding attempt {attempt + 1} failed: {e}")
                    logger.info("Trying next embedding provider...")
                    self._fallback_to_next_embedding_provider()
                    time.sleep(retry_config.get('retry_delay', 1))
                    continue
                
                raise
        
        raise Exception("Max retries exceeded for embeddings")
    
    def _get_openai_embeddings(self, texts: list, model_config: Dict[str, Any]):
        """Get embeddings from OpenAI"""
        if not self.openai_client:
            raise ValueError("OpenAI client not initialized")
        
        response = self.openai_client.embeddings.create(
            model=model_config['model_name'],
            input=texts
        )
        
        return [data.embedding for data in response.data]
    
    def _get_ollama_embeddings(self, texts: list, model_config: Dict[str, Any]):
        """Get embeddings from Ollama"""
        embeddings = []
        # Try different Ollama embedding endpoints
        endpoints = ['/api/embeddings', '/api/embed']
        
        for endpoint in endpoints:
            try:
                url = f"{self.ollama_base_url}{endpoint}"
                
                for text in texts:
                    payload = {
                        'model': model_config['model_name'],
                        'prompt': text
                    }
                    
                    response = requests.post(url, json=payload, timeout=10)
                    response.raise_for_status()
                    result = response.json()
                    
                    # Handle different response formats
                    if 'embedding' in result:
                        embeddings.append(result['embedding'])
                    elif 'embeddings' in result and len(result['embeddings']) > 0:
                        embeddings.append(result['embeddings'][0])
                    else:
                        # Try to find embedding in response
                        for key, value in result.items():
                            if isinstance(value, list) and len(value) > 100:  # Likely an embedding
                                embeddings.append(value)
                                break
                
                if embeddings and len(embeddings) == len(texts):
                    logger.info(f"Successfully got embeddings from Ollama endpoint: {endpoint}")
                    return embeddings
                    
            except Exception as e:
                logger.warning(f"Ollama endpoint {endpoint} failed: {e}")
                continue
        
        raise Exception(f"Failed to get embeddings from Ollama. Tried endpoints: {endpoints}")
    
    def _get_fastembed_embeddings(self, texts: list, model_config: Dict[str, Any]):
        """Get embeddings from FastEmbed"""
        try:
            # Lazy initialization
            self._initialize_fastembed(model_config['model_name'])
            
            if self.fastembed_model is None:
                raise ValueError("FastEmbed model not initialized")
            
            # Generate embeddings
            embeddings = list(self.fastembed_model.embed(texts))
            
            # Convert to list of lists
            embeddings_list = [embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding) 
                             for embedding in embeddings]
            
            logger.info(f"Generated {len(embeddings_list)} embeddings using FastEmbed")
            return embeddings_list
            
        except Exception as e:
            logger.error(f"Error with FastEmbed: {e}")
            raise
    
    def get_current_llm_provider(self) -> str:
        """Get current active LLM provider"""
        return self.current_llm_provider
    
    def get_current_embedding_provider(self) -> str:
        """Get current active embedding provider"""
        return self.current_embedding_provider
    
    def get_current_embedding_dimension(self) -> int:
        """Get current embedding dimension"""
        current_model = self._get_current_embedding_model()
        dimension = current_model.get('dimension')
        
        # If dimension not specified, try to detect it
        if dimension is None:
            try:
                # Get a test embedding to detect dimension
                test_emb = self.get_embeddings(["test"])
                if test_emb and len(test_emb) > 0:
                    dimension = len(test_emb[0])
                    logger.info(f"Auto-detected embedding dimension: {dimension}")
                else:
                    dimension = 768  # Default fallback
            except:
                dimension = 768  # Default fallback
        
        return dimension
    
    def get_llm_config(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Get configuration for specified LLM provider"""
        provider = provider or self.current_llm_provider
        for model in self.llm_models:
            if model['provider'] == provider:
                return model
        return {}
    
    def get_embedding_config(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Get configuration for specified embedding provider"""
        provider = provider or self.current_embedding_provider
        for model in self.embedding_models:
            if model['provider'] == provider:
                return model
        return {}
    
    def switch_llm_provider(self, provider: str):
        """Manually switch LLM provider"""
        if any(m['provider'] == provider for m in self.llm_models):
            self.current_llm_provider = provider
            logger.info(f"Switched LLM to {provider}")
        else:
            raise ValueError(f"Invalid LLM provider: {provider}")
    
    def switch_embedding_provider(self, provider: str):
        """Manually switch embedding provider"""
        if any(m['provider'] == provider for m in self.embedding_models):
            self.current_embedding_provider = provider
            logger.info(f"Switched embedding to {provider}")
        else:
            raise ValueError(f"Invalid embedding provider: {provider}")


# Convenience function to get model manager instance
_model_manager_instance = None

def get_model_manager(config_path: str = "config.yaml") -> ModelManager:
    """Get singleton instance of ModelManager"""
    global _model_manager_instance
    if _model_manager_instance is None:
        _model_manager_instance = ModelManager(config_path)
    return _model_manager_instance
# [file content end]