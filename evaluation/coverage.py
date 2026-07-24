import os
import json
import logging
from typing import List, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

DEFAULT_EXPECTED_SECTIONS = [
    "Standard RAG",
    "DeepRAG",
    "MA-RAG",
    "Corrective RAG",
    "Speculative RAG",
    "Fusion RAG",
    "RAG-Gym",
    "Modular RAG",
    "SAM-RAG"
]

def calculate_coverage(response_text: str, expected_sections: List[str] = None) -> Dict[str, Any]:
    """
    Evaluates whether expected sections/architectures are present in the response_text.
    Utilizes a LLM-based fact checker for semantic matching (e.g. Multi-Agent RAG mapping to MA-RAG).
    Saves coverage reports and missing sections to json files at the root and results directories.
    """
    if not expected_sections:
        expected_sections = DEFAULT_EXPECTED_SECTIONS
        
    logger.info(f"📋 Running section coverage evaluation for {len(expected_sections)} sections...")
    
    # 1. Simple heuristic keyword check first
    coverage_map = {}
    missing = []
    
    # Let's perform a direct word boundary match
    import re
    for section in expected_sections:
        # Check if the section name appears in the text
        # Clean section name for query matching (e.g. MA-RAG, SAM-RAG)
        escaped = re.escape(section)
        # Handle optional hyphens/spaces: standard rag -> standard-rag / standard rag
        escaped_alt = escaped.replace(r'\ ', r'[\s\-]*')
        pattern = re.compile(r'\b' + escaped_alt + r'\b', re.IGNORECASE)
        
        if pattern.search(response_text):
            coverage_map[section] = True
        else:
            coverage_map[section] = False
            
    # 2. Refine false negatives using LLM (GPT-4o-mini)
    false_negatives = [sec for sec, covered in coverage_map.items() if not covered]
    if false_negatives:
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            client = OpenAI(api_key=api_key)
            
            prompt = f"""You are a professional technical auditor.
Check if the following sections/topics are covered, explained, or described in the provided text.
Sometimes they might be discussed under slightly different names (e.g., "Multi-Agent RAG" instead of "MA-RAG" or "Segment-Attention-Model" instead of "SAM-RAG").
Only mark a section as covered if there is actual substantive description of it, not just a passing mention in a list.

Expected sections to check:
{json.dumps(false_negatives, indent=2)}

Text to inspect:
---
{response_text}
---

Return ONLY a valid JSON object mapping each section name to a boolean value indicating whether it is covered:
{{
  "section_name": true/false
}}
"""
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            
            llm_results = json.loads(completion.choices[0].message.content)
            for sec, covered in llm_results.items():
                if sec in coverage_map:
                    coverage_map[sec] = bool(covered)
                    
        except Exception as e:
            logger.warning(f"Failed to refine false negatives via LLM: {e}")
            
    # Calculate covered count and score
    covered_sections = sum(1 for covered in coverage_map.values() if covered)
    expected_count = len(expected_sections)
    coverage_score = (covered_sections / expected_count) * 100.0 if expected_count > 0 else 0.0
    
    missing = [sec for sec, covered in coverage_map.items() if not covered]
    
    report = {
        "expected_sections": expected_count,
        "covered_sections": covered_sections,
        "coverage_score": round(coverage_score, 1),
        "details": coverage_map
    }
    
    # Save files to results/ and root
    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
    os.makedirs(results_dir, exist_ok=True)
    
    # Paths
    report_paths = [
        os.path.join(results_dir, "coverage_report.json"),
        "coverage_report.json"
    ]
    missing_paths = [
        os.path.join(results_dir, "missing_sections.json"),
        "missing_sections.json"
    ]
    
    for path in report_paths:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            logger.info(f"💾 Saved coverage report to {path}")
        except Exception as e:
            logger.error(f"Failed to save {path}: {e}")
            
    for path in missing_paths:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(missing, f, indent=2)
            logger.info(f"💾 Saved missing sections list to {path}")
        except Exception as e:
            logger.error(f"Failed to save {path}: {e}")
            
    return report
