import os
import json
import logging
import re
from typing import List, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def calculate_hallucination(response_text: str, contexts: List[str]) -> Dict[str, Any]:
    """
    Evaluates response_text against retrieved context chunks to detect hallucinated details,
    unsupported claims, and missing citations.
    Returns:
    {
       "hallucination_score": float (0.0 to 1.0),
       "claims": list of analyzed claims,
       "missing_citations_count": int,
       "unsupported_claims_count": int
    }
    """
    logger.info("🕵️ Running hallucination detection...")
    
    # 1. Check for missing citations (statements that look like facts but lack citation brackets [1])
    # Let's count paragraphs or sentences that make claims but lack citations
    sentences = re.split(r'(?<=[.!?])\s+', response_text)
    total_sentences = len(sentences)
    missing_citations = 0
    
    # Simple check: if a sentence has numbers, names, or architectural definitions but no [number]
    for s in sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        
        # Check if sentence makes factual statements (e.g. contains words like "RAG", "is", "uses", "provides")
        # and does not end or contain a citation pattern like [1] or [12]
        if any(w in s_clean for w in ["RAG", "architecture", "standard", "corrective", "speculative", "fusion", "modular"]):
            if not re.search(r'\[\d+\]', s_clean):
                missing_citations += 1
                
    # 2. LLM Fact-Checking for Unsupported Claims & Content Absent from Source
    context_combined = "\n\n".join([f"[Chunk {idx+1}]: {ctx}" for idx, ctx in enumerate(contexts)])
    
    hallucination_score = 0.0
    claims_details = []
    unsupported_count = 0
    
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        client = OpenAI(api_key=api_key)
        
        prompt = f"""You are an expert fact-checker. Compare the Chatbot Response against the Provided Context Chunks.
        
Identify all major factual statements and assertions made in the Chatbot Response.
For each statement:
1. Check if it is fully supported by the Provided Context Chunks.
2. Check if the information is absent from the source context (hallucinated).

Provided Context Chunks:
---
{context_combined}
---

Chatbot Response:
---
{response_text}
---

Return your analysis as a valid JSON object matching the following schema:
{{
  "claims": [
    {{
      "statement": "text of statement/claim",
      "supported": true/false,
      "absent_from_source": true/false,
      "explanation": "why it is or isn't supported"
    }}
  ]
}}
"""
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        
        llm_data = json.loads(completion.choices[0].message.content)
        claims_details = llm_data.get("claims", [])
        
        # Calculate unsupported count
        for c in claims_details:
            if not c.get("supported", True) or c.get("absent_from_source", False):
                unsupported_count += 1
                
        total_claims = len(claims_details)
        if total_claims > 0:
            hallucination_score = unsupported_count / total_claims
        else:
            hallucination_score = 0.0
            
    except Exception as e:
        logger.error(f"Failed to execute LLM fact-checking: {e}")
        # Fallback heuristic score based on missing citations
        if total_sentences > 0:
            hallucination_score = min(0.5, missing_citations / total_sentences)
            
    # Compile final report
    report = {
        "hallucination_score": round(hallucination_score, 3),
        "claims": claims_details,
        "missing_citations_count": missing_citations,
        "unsupported_claims_count": unsupported_count
    }
    
    # Save a hallucination report to results/
    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
    os.makedirs(results_dir, exist_ok=True)
    report_path = os.path.join(results_dir, "hallucination_report.json")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        logger.info(f"💾 Saved hallucination report to {report_path}")
    except Exception as e:
        logger.error(f"Failed to save {report_path}: {e}")
        
    return report
