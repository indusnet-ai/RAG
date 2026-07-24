import nltk
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
import re
from typing import Dict, List

# Try downloading punkt tokenizer data, fallback gracefully if offline/fails
try:
    nltk.download('punkt', quiet=True)
except Exception:
    pass

def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase words. Fallback to regex tokenizer if NLTK fails."""
    if not text:
        return []
    try:
        return [token.lower() for token in nltk.word_tokenize(text)]
    except Exception:
        # Fallback tokenizer
        return re.findall(r'\w+', text.lower())

def calculate_bleu(hypothesis: str, reference: str) -> Dict[str, float]:
    """
    Calculate BLEU-1, BLEU-2, BLEU-3, and BLEU-4 scores.
    Returns:
        Dict with keys: bleu1, bleu2, bleu3, bleu4
    """
    hyp_tokens = tokenize(hypothesis)
    ref_tokens = tokenize(reference)

    if not hyp_tokens or not ref_tokens:
        return {
            "bleu1": 0.0,
            "bleu2": 0.0,
            "bleu3": 0.0,
            "bleu4": 0.0
        }

    # sentence_bleu expects a list of references, where each reference is a list of tokens
    references = [ref_tokens]
    
    # Use method1 smoothing to avoid zero score for short sentences
    chencherry = SmoothingFunction()
    smoothing = chencherry.method1

    try:
        bleu1 = sentence_bleu(references, hyp_tokens, weights=(1.0, 0.0, 0.0, 0.0), smoothing_function=smoothing)
        bleu2 = sentence_bleu(references, hyp_tokens, weights=(0.5, 0.5, 0.0, 0.0), smoothing_function=smoothing)
        bleu3 = sentence_bleu(references, hyp_tokens, weights=(0.33, 0.33, 0.33, 0.0), smoothing_function=smoothing)
        bleu4 = sentence_bleu(references, hyp_tokens, weights=(0.25, 0.25, 0.25, 0.25), smoothing_function=smoothing)
    except Exception:
        bleu1 = bleu2 = bleu3 = bleu4 = 0.0

    return {
        "bleu1": round(bleu1, 4),
        "bleu2": round(bleu2, 4),
        "bleu3": round(bleu3, 4),
        "bleu4": round(bleu4, 4)
    }
