"""
RAGAs Metrics API
View evaluation results and aggregate statistics
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel
from routers.dependencies import get_current_user
from db import get_db
from services.ragas_evaluator import RAGAsEvaluator
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ragas", tags=["RAGAs Metrics"])


class AggregateMetricsResponse(BaseModel):
    total_evaluations: int
    avg_faithfulness: Optional[float]
    avg_answer_relevancy: Optional[float]
    avg_context_precision: Optional[float]
    avg_context_recall: Optional[float]
    avg_eval_duration: Optional[float]


class QueryEvaluationResponse(BaseModel):
    faithfulness: Optional[float]
    answer_relevancy: Optional[float]
    context_precision: Optional[float]
    context_recall: Optional[float]
    contexts_count: int
    eval_duration_seconds: float
    evaluated_at: str


@router.get("/query/{query_id}", response_model=QueryEvaluationResponse)
async def get_query_evaluation(
    query_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Get RAGAs evaluation for a specific query"""
    try:
        evaluator = RAGAsEvaluator(db)
        result = evaluator.get_query_evaluation(query_id)
        
        if not result:
            raise HTTPException(404, "Evaluation not found for this query")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving evaluation: {str(e)}")
        raise HTTPException(500, f"Error: {str(e)}")


@router.get("/aggregate", response_model=AggregateMetricsResponse)
async def get_aggregate_metrics(
    collection_name: Optional[str] = None,
    days: int = 30,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """
    Get aggregate RAGAs metrics.
    
    - **collection_name**: Filter by collection (optional)
    - **days**: Time period in days (default: 30)
    
    Returns average scores across all evaluated queries.
    """
    try:
        user_id = str(current_user.id)
        
        # Get collection ID if name provided
        collection_id = None
        if collection_name:
            from sqlalchemy import text
            result = db.execute(text("""
                SELECT id FROM collections
                WHERE collection_name = :name AND user_id = :uid
            """), {"name": collection_name, "uid": user_id})
            
            row = result.fetchone()
            if row:
                collection_id = str(row.id)
        
        evaluator = RAGAsEvaluator(db)
        metrics = evaluator.get_aggregate_metrics(
            user_id=user_id,
            collection_id=collection_id,
            days=days
        )
        
        return metrics
        
    except Exception as e:
        logger.error(f"Error getting aggregate metrics: {str(e)}")
        raise HTTPException(500, f"Error: {str(e)}")