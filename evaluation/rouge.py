from rouge_score import rouge_scorer
from typing import Dict

def calculate_rouge(hypothesis: str, reference: str) -> Dict[str, float]:
    """
    Calculate ROUGE-1, ROUGE-2, and ROUGE-L F1 scores.
    Returns:
        Dict with keys: rouge1_f1, rouge2_f1, rougeL_f1
    """
    if not hypothesis or not reference:
        return {
            "rouge1_f1": 0.0,
            "rouge2_f1": 0.0,
            "rougeL_f1": 0.0
        }

    scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=True)
    scores = scorer.score(reference, hypothesis)

    return {
        "rouge1_f1": round(scores['rouge1'].fmeasure, 4),
        "rouge2_f1": round(scores['rouge2'].fmeasure, 4),
        "rougeL_f1": round(scores['rougeL'].fmeasure, 4)
    }
