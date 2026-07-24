from bert_score import score
from typing import Dict
import logging

logger = logging.getLogger(__name__)

def calculate_bertscore(hypothesis: str, reference: str) -> Dict[str, float]:
    """
    Calculate BERTScore Precision, Recall, and F1.
    Uses 'distilbert-base-uncased' as a lightweight model for speed.
    Returns:
        Dict with keys: precision, recall, f1
    """
    if not hypothesis or not reference:
        return {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0
        }

    try:
        # P, R, F1 are tensors corresponding to each sentence pair
        P, R, F1 = score(
            [hypothesis], 
            [reference], 
            lang="en", 
            model_type="distilbert-base-uncased", 
            verbose=False
        )
        
        return {
            "precision": round(P.mean().item(), 4),
            "recall": round(R.mean().item(), 4),
            "f1": round(F1.mean().item(), 4)
        }
    except Exception as e:
        logger.error(f"Error calculating BERTScore: {e}")
        return {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0
        }
