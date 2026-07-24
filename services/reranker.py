import os
import torch
import logging
from typing import List, Dict, Any
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from flashrank import Ranker, RerankRequest

logger = logging.getLogger(__name__)

class FlashRankReranker:
    def __init__(self):
        self.use_bge = False
        self.bge_tokenizer = None
        self.bge_model = None
        self.flashrank_ranker = None
        
        # Try to load BGE-Reranker-v2-m3
        try:
            logger.info("Loading BGE-Reranker-v2-m3 via transformers...")
            model_name = "BAAI/bge-reranker-v2-m3"
            self.bge_tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.bge_model = AutoModelForSequenceClassification.from_pretrained(model_name)
            
            # Use CUDA if available
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.bge_model.to(self.device)
            self.bge_model.eval()
            
            self.use_bge = True
            logger.info(f"✅ BGE-Reranker-v2-m3 loaded successfully on {self.device}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load BGE-Reranker-v2-m3 ({e}). Falling back to FlashRank ms-marco-MiniLM...")
            try:
                self.flashrank_ranker = Ranker(
                    model_name="ms-marco-MiniLM-L-12-v2",
                    cache_dir="./models"
                )
                logger.info("✅ FlashRank ready (fallback)")
            except Exception as fe:
                logger.error(f"❌ Failed to load FlashRank fallback: {fe}")
                # We raise fe here so it can fallback to disabling reranking in rag_generation
                raise fe

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_n: int = 5
    ) -> List[Dict[str, Any]]:
        if not documents:
            return []
            
        if self.use_bge and self.bge_model and self.bge_tokenizer:
            try:
                # 1. Format inputs for cross-encoder
                pairs = [[query, doc.get("content", "")] for doc in documents]
                
                # 2. Tokenize and run model
                with torch.no_grad():
                    inputs = self.bge_tokenizer(
                        pairs, 
                        padding=True, 
                        truncation=True, 
                        return_tensors='pt', 
                        max_length=512
                    ).to(self.device)
                    
                    scores = self.bge_model(**inputs).logits.view(-1).float().tolist()
                
                # If single doc, scores might be a float instead of list
                if isinstance(scores, float):
                    scores = [scores]
                    
                # 3. Associate scores and sort
                reranked = []
                for idx, (doc, score) in enumerate(zip(documents, scores)):
                    doc_copy = doc.copy()
                    doc_copy["rerank_score"] = score
                    doc_copy["original_rank"] = idx + 1
                    reranked.append(doc_copy)
                    
                # Sort descending (higher score = more relevant)
                reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
                
                logger.info(f"BGE-Reranker-v2: Reranked {len(documents)} → {min(top_n, len(reranked))} (Top score: {reranked[0]['rerank_score']:.4f})")
                return reranked[:top_n]
                
            except Exception as e:
                logger.error(f"Error during BGE reranking: {e}. Falling back to FlashRank if available...")
                if not self.flashrank_ranker:
                    # If no fallback available, return top_n from original list
                    return documents[:top_n]
                # Fall through to flashrank logic below
                
        # FlashRank fallback logic
        if self.flashrank_ranker:
            try:
                passages = [
                    {"id": i, "text": doc.get('content', ''), "meta": doc}
                    for i, doc in enumerate(documents)
                ]
                rerank_request = RerankRequest(query=query, passages=passages)
                results = self.flashrank_ranker.rerank(rerank_request)
                
                reranked = []
                for result in results[:top_n]:
                    doc = result['meta'].copy()
                    doc['rerank_score'] = result['score']
                    doc['original_rank'] = result['id'] + 1
                    reranked.append(doc)
                
                logger.info(f"FlashRank fallback: Reranked {len(documents)} → {len(reranked)}")
                return reranked
            except Exception as e:
                logger.error(f"FlashRank rerank fallback failed: {e}")
                return documents[:top_n]
            
        return documents[:top_n]