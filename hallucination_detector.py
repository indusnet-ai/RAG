import sys
import os
import json
import asyncio

# Add current folder to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from evaluation.hallucination import calculate_hallucination

def check_hallucination(response_text: str, contexts: list) -> dict:
    """Standalone function to check hallucinations."""
    result = calculate_hallucination(response_text, contexts)
    # Output expected JSON structure: {"hallucination_score": 0.02}
    return {
        "hallucination_score": result.get("hallucination_score", 0.0)
    }

if __name__ == "__main__":
    # Test stub
    test_response = (
        "Corrective RAG (CRAG) evaluates retrieved documents and uses web search if needed. "
        "Hyper-RAG is a premium quantum architecture that runs summaries in parallel [1]."
    )
    test_contexts = [
        "Corrective RAG is a RAG framework that uses a self-evaluation model to assess retrieved documents."
    ]
    
    print("Testing Hallucination Detector...")
    score_report = check_hallucination(test_response, test_contexts)
    print(json.dumps(score_report, indent=2))
