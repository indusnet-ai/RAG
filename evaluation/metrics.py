import os
import json
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Directory to store JSON results
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)
RESULTS_FILE = os.path.join(RESULTS_DIR, "evaluation_results.json")
EVAL_RESULTS_ROOT = "evaluation_results.json"  # Phase 5 output target

# Define threshold boundaries (Phase 13 success criteria)
THRESHOLDS = {
    "bleu1": 0.40,
    "bleu4": 0.20,
    "rougeL_f1": 0.45,
    "faithfulness": 0.95,
    "context_precision": 0.90,
    "context_recall": 0.85,
    "coverage_score": 90.0,
    "hallucination_score": 0.05
}

def init_eval_db(db):
    """Create evaluation table if it does not exist, and upgrade columns if missing."""
    try:
        # SQLite compatible UUID and VARCHAR logic
        db.execute(text("""
        CREATE TABLE IF NOT EXISTS automated_evaluations (
            id VARCHAR(36) PRIMARY KEY,
            document_id VARCHAR(36),
            document_name VARCHAR(255),
            query_text TEXT,
            response_text TEXT,
            reference_text TEXT,
            bleu1 FLOAT,
            bleu2 FLOAT,
            bleu3 FLOAT,
            bleu4 FLOAT,
            rouge1_f1 FLOAT,
            rouge2_f1 FLOAT,
            rougeL_f1 FLOAT,
            bert_precision FLOAT,
            bert_recall FLOAT,
            bert_f1 FLOAT,
            faithfulness FLOAT,
            answer_relevancy FLOAT,
            context_precision FLOAT,
            context_recall FLOAT,
            coverage_score FLOAT,
            hallucination_score FLOAT,
            status VARCHAR(50),
            diagnostics TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """))
        db.commit()
        
        # Check if coverage_score column exists, if not add it
        try:
            db.execute(text("SELECT coverage_score FROM automated_evaluations LIMIT 1;"))
        except Exception:
            try:
                db.rollback()
            except:
                pass
            db.execute(text("ALTER TABLE automated_evaluations ADD COLUMN coverage_score FLOAT;"))
            db.commit()
            logger.info("Added coverage_score column to automated_evaluations table")
            
        # Check if hallucination_score column exists, if not add it
        try:
            db.execute(text("SELECT hallucination_score FROM automated_evaluations LIMIT 1;"))
        except Exception:
            try:
                db.rollback()
            except:
                pass
            db.execute(text("ALTER TABLE automated_evaluations ADD COLUMN hallucination_score FLOAT;"))
            db.commit()
            logger.info("Added hallucination_score column to automated_evaluations table")
            
    except Exception as e:
        logger.error(f"Failed to initialize automated_evaluations table: {e}")
        try:
            db.rollback()
        except:
            pass

def check_success_criteria(scores: Dict[str, float]) -> Dict[str, Any]:
    """
    Compares calculated metrics against success criteria thresholds (Phase 13).
    Flags failures and prepares diagnostics.
    """
    failed_metrics = []
    
    # Check each defined threshold
    for metric, threshold in THRESHOLDS.items():
        val = scores.get(metric)
        if val is None:
            val = 0.0
            
        if metric == "hallucination_score":
            if val > threshold:
                failed_metrics.append(f"{metric} (value: {val:.3f} > threshold: {threshold:.2f})")
        else:
            if val < threshold:
                failed_metrics.append(f"{metric} (value: {val:.3f} < threshold: {threshold:.2f})")
            
    passed = len(failed_metrics) == 0
    status = "PASSED" if passed else "FAILED"
    
    diagnostics = ""
    if not passed:
        diagnostics = (
            f"Evaluation FAILED due to sub-threshold metrics: {', '.join(failed_metrics)}. "
            f"Diagnostics: Generated response has low similarity to reference answer or has coverage/hallucination gaps. "
            f"Suggested retrieval improvements: Ensure context builder selects diverse section chunks and check prompt constraints."
        )
        
    return {
        "status": status,
        "passed": passed,
        "diagnostics": diagnostics,
        "failed_metrics": failed_metrics
    }

def save_evaluation_result(
    db,
    document_id: str,
    document_name: str,
    query_text: str,
    response_text: str,
    reference_text: str,
    scores: Dict[str, float]
) -> Dict[str, Any]:
    """
    Check thresholds, save result to local JSON files, and insert into SQL database.
    """
    # Initialize DB schema first
    init_eval_db(db)
    
    # Check thresholds
    crit_result = check_success_criteria(scores)
    
    eval_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    
    result_payload = {
        "id": eval_id,
        "document_id": document_id,
        "document_name": document_name,
        "query_text": query_text,
        "response_text": response_text,
        "reference_text": reference_text,
        "scores": scores,
        "status": crit_result["status"],
        "diagnostics": crit_result["diagnostics"],
        "created_at": created_at
    }
    
    # 1. Save to JSON files (Phase 5: save to evaluation_results.json at root and results/)
    for filepath in [RESULTS_FILE, EVAL_RESULTS_ROOT]:
        try:
            data = []
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if not isinstance(data, list):
                            data = []
                except Exception:
                    data = []
                    
            # Append new evaluation results
            data.append(result_payload)
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                
            logger.info(f"💾 Saved evaluation result to JSON: {filepath}")
        except Exception as e:
            logger.error(f"Failed to write results to JSON ({filepath}): {e}")
        
    # 2. Save to Database
    try:
        db.execute(text("""
            INSERT INTO automated_evaluations (
                id, document_id, document_name, query_text, response_text, reference_text,
                bleu1, bleu2, bleu3, bleu4,
                rouge1_f1, rouge2_f1, rougeL_f1,
                bert_precision, bert_recall, bert_f1,
                faithfulness, answer_relevancy, context_precision, context_recall,
                coverage_score, hallucination_score,
                status, diagnostics, created_at
            ) VALUES (
                :id, :doc_id, :doc_name, :q_text, :resp_text, :ref_text,
                :bleu1, :bleu2, :bleu3, :bleu4,
                :rouge1_f1, :rouge2_f1, :rougeL_f1,
                :bert_p, :bert_r, :bert_f1,
                :faith, :rel, :prec, :rec,
                :cov, :hal,
                :status, :diag, CURRENT_TIMESTAMP
            )
        """), {
            "id": eval_id,
            "doc_id": document_id,
            "doc_name": document_name,
            "q_text": query_text,
            "resp_text": response_text,
            "ref_text": reference_text,
            "bleu1": scores.get("bleu1"),
            "bleu2": scores.get("bleu2"),
            "bleu3": scores.get("bleu3"),
            "bleu4": scores.get("bleu4"),
            "rouge1_f1": scores.get("rouge1_f1"),
            "rouge2_f1": scores.get("rouge2_f1"),
            "rougeL_f1": scores.get("rougeL_f1"),
            "bert_p": scores.get("bert_precision"),
            "bert_r": scores.get("bert_recall"),
            "bert_f1": scores.get("bert_f1"),
            "faith": scores.get("faithfulness"),
            "rel": scores.get("answer_relevancy"),
            "prec": scores.get("context_precision"),
            "rec": scores.get("context_recall"),
            "cov": scores.get("coverage_score"),
            "hal": scores.get("hallucination_score"),
            "status": crit_result["status"],
            "diag": crit_result["diagnostics"]
        })
        db.commit()
        logger.info(f"✅ Logged evaluation {eval_id} to SQL database.")
    except Exception as e:
        logger.error(f"Failed to log evaluation to DB: {e}")
        try:
            db.rollback()
        except:
            pass
            
    return result_payload
