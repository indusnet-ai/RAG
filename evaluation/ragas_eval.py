import os
import logging
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI

from ragas.llms import llm_factory
from ragas.embeddings.base import embedding_factory
from ragas.metrics.collections import (
    Faithfulness,
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
)

logger = logging.getLogger(__name__)

class RagasEvaluator:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY is not configured in .env. RagasEvaluator initialization skipped.")
            self.initialized = False
            return

        try:
            self.client = AsyncOpenAI(api_key=api_key)
            # Use gpt-4o-mini as a high-quality, cost-efficient evaluator model
            self.llm = llm_factory("gpt-4o-mini", client=self.client)
            self.embeddings = embedding_factory(
                "openai",
                model="text-embedding-3-small",
                client=self.client
            )
            
            # Initialize metrics
            self.faithfulness_metric = Faithfulness(llm=self.llm)
            self.answer_relevancy_metric = AnswerRelevancy(llm=self.llm, embeddings=self.embeddings)
            self.context_precision_metric = ContextPrecision(llm=self.llm)
            self.context_recall_metric = ContextRecall(llm=self.llm)
            self.initialized = True
            logger.info("✅ RAGAs evaluator initialized with 4 metrics (Faithfulness, Relevancy, Precision, Recall)")
        except Exception as e:
            logger.error(f"Failed to initialize RAGAs evaluator: {e}")
            self.initialized = False

    async def evaluate(
        self,
        query: str,
        response: str,
        contexts: List[str],
        reference: str
    ) -> Dict[str, float]:
        """
        Evaluate a single query-response pair against context and reference.
        Returns:
            Dict containing RAGAs scores.
        """
        if not self.initialized:
            logger.warning("RagasEvaluator not initialized. Returning default scores.")
            return {
                "faithfulness": 0.0,
                "answer_relevancy": 0.0,
                "context_precision": 0.0,
                "context_recall": 0.0
            }

        if not contexts:
            logger.warning("No contexts provided for RAGAs evaluation.")
            return {
                "faithfulness": 0.0,
                "answer_relevancy": 0.0,
                "context_precision": 0.0,
                "context_recall": 0.0
            }

        scores = {}
        
        # 1. Faithfulness
        try:
            faith = await self.faithfulness_metric.ascore(
                user_input=query,
                retrieved_contexts=contexts,
                response=response
            )
            scores["faithfulness"] = round(faith.value, 4)
        except Exception as e:
            logger.warning(f"Faithfulness evaluation failed: {e}")
            scores["faithfulness"] = 0.0

        # 2. Answer Relevancy
        try:
            relevancy = await self.answer_relevancy_metric.ascore(
                user_input=query,
                response=response
            )
            scores["answer_relevancy"] = round(relevancy.value, 4)
        except Exception as e:
            logger.warning(f"Answer Relevancy evaluation failed: {e}")
            scores["answer_relevancy"] = 0.0

        # 3. Context Precision
        try:
            precision = await self.context_precision_metric.ascore(
                user_input=query,
                retrieved_contexts=contexts,
                reference=reference
            )
            scores["context_precision"] = round(precision.value, 4)
        except Exception as e:
            logger.warning(f"Context Precision evaluation failed: {e}")
            scores["context_precision"] = 0.0

        # 4. Context Recall
        try:
            recall = await self.context_recall_metric.ascore(
                user_input=query,
                retrieved_contexts=contexts,
                reference=reference
            )
            scores["context_recall"] = round(recall.value, 4)
        except Exception as e:
            logger.warning(f"Context Recall evaluation failed: {e}")
            scores["context_recall"] = 0.0

        return scores
