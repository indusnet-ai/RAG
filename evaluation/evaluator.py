import logging
from typing import List, Dict, Any
import asyncio

from evaluation.bleu import calculate_bleu
from evaluation.rouge import calculate_rouge
from evaluation.bertscore import calculate_bertscore
from evaluation.ragas_eval import RagasEvaluator
from evaluation.coverage import calculate_coverage
from evaluation.hallucination import calculate_hallucination

logger = logging.getLogger(__name__)

class RAGEvaluator:
    def __init__(self):
        # Initialize RagasEvaluator wrapper (handles OpenAI/Ragas setup)
        self.ragas_evaluator = RagasEvaluator()

    async def evaluate_response(
        self,
        query: str,
        response: str,
        contexts: List[str],
        reference: str
    ) -> Dict[str, float]:
        """
        Runs all 13 evaluation metrics against the hypothesis response, contexts, and reference summary.
        Combines results into a single flat dict.
        """
        logger.info("🧪 Executing full RAG Evaluation suite...")
        
        # 1. Lexical and Semantic computation (run in threadpool as they are CPU-bound)
        loop = asyncio.get_event_loop()
        
        bleu_scores = await loop.run_in_executor(None, calculate_bleu, response, reference)
        logger.info(f"  ✓ BLEU-1 to 4 calculated: {bleu_scores}")
        
        rouge_scores = await loop.run_in_executor(None, calculate_rouge, response, reference)
        logger.info(f"  ✓ ROUGE F1 calculated: {rouge_scores}")
        
        bert_scores = await loop.run_in_executor(None, calculate_bertscore, response, reference)
        logger.info(f"  ✓ BERTScore calculated: {bert_scores}")
        
        # 2. Section Coverage (Phase 3)
        coverage_report = await loop.run_in_executor(None, calculate_coverage, response)
        coverage_score = coverage_report.get("coverage_score", 0.0)
        logger.info(f"  ✓ Section Coverage calculated: {coverage_score}%")
        
        # 3. Hallucination Detection (Phase 11)
        hallucination_report = await loop.run_in_executor(None, calculate_hallucination, response, contexts)
        hallucination_score = hallucination_report.get("hallucination_score", 0.0)
        logger.info(f"  ✓ Hallucination Score calculated: {hallucination_score}")
        
        # 4. RAGAs evaluation (async OpenAI calls)
        ragas_scores = {
            "faithfulness": 0.0,
            "answer_relevancy": 0.0,
            "context_precision": 0.0,
            "context_recall": 0.0
        }
        
        if self.ragas_evaluator.initialized:
            try:
                ragas_scores = await self.ragas_evaluator.evaluate(
                    query=query,
                    response=response,
                    contexts=contexts,
                    reference=reference
                )
                logger.info(f"  ✓ Ragas scores calculated: {ragas_scores}")
            except Exception as e:
                logger.error(f"Error calculating Ragas metrics: {e}")
        else:
            logger.warning("Ragas evaluator not initialized. Skipping Ragas metrics.")

        # Combine all metrics into a flat dict
        aggregated_scores = {
            # BLEU
            "bleu1": bleu_scores.get("bleu1", 0.0),
            "bleu2": bleu_scores.get("bleu2", 0.0),
            "bleu3": bleu_scores.get("bleu3", 0.0),
            "bleu4": bleu_scores.get("bleu4", 0.0),
            # ROUGE
            "rouge1_f1": rouge_scores.get("rouge1_f1", 0.0),
            "rouge2_f1": rouge_scores.get("rouge2_f1", 0.0),
            "rougeL_f1": rouge_scores.get("rougeL_f1", 0.0),
            # BERTScore
            "bert_precision": bert_scores.get("precision", 0.0),
            "bert_recall": bert_scores.get("recall", 0.0),
            "bert_f1": bert_scores.get("f1", 0.0),
            # Ragas
            "faithfulness": ragas_scores.get("faithfulness", 0.0),
            "answer_relevancy": ragas_scores.get("answer_relevancy", 0.0),
            "context_precision": ragas_scores.get("context_precision", 0.0),
            "context_recall": ragas_scores.get("context_recall", 0.0),
            # Custom Metrics
            "coverage_score": coverage_score,
            "hallucination_score": hallucination_score
        }
        
        logger.info("📊 Finished evaluation suite aggregation.")
        return aggregated_scores
