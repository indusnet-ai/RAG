"""
RAGAs Evaluation Service - Production Ready
- 3 reliable metrics (skip Faithfulness)
- Rounded decimal storage (3 decimals)
- Synthetic ground truth
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlalchemy import text
import os

from services.metrics import track_ragas_metrics, track_ragas_duration

from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.embeddings.base import embedding_factory

from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
)

logger = logging.getLogger(__name__)


class RAGAsEvaluator:
    """
    Production RAGAs evaluator.
    
    Metrics:
    - Answer Relevancy: Most important (varies by query quality)
    - Context Precision: Retrieval ranking quality
    - Context Recall: Retrieval completeness
    
    Note: Precision/Recall often 1.0 with synthetic ground truth.
    This is expected behavior.
    """

    def __init__(self, db):
        self.db = db

        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )

        self.llm = llm_factory("gpt-4o-mini", client=self.client)
        
        self.embeddings = embedding_factory(
            "openai",
            model="text-embedding-3-small",
            client=self.client
        )

        self.answer_relevancy = AnswerRelevancy(
            llm=self.llm,
            embeddings=self.embeddings
        )
        self.context_precision = ContextPrecision(llm=self.llm)
        self.context_recall = ContextRecall(llm=self.llm)

        logger.info("✅ RAGAs evaluator initialized (3 metrics)")


    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        """Truncate text to max_chars"""
        if not text or len(text) <= max_chars:
            return text
        
        truncated = text[:max_chars]
        
        # Try sentence boundary
        for punct in ['. ', '! ', '? ', '\n']:
            last = truncated.rfind(punct)
            if last > max_chars * 0.7:
                return truncated[:last + 1]
        
        return truncated + "..."


    async def _generate_ground_truth(self, query: str, contexts: List[str]) -> str:
        """Generate synthetic ground truth"""
        try:
            combined = "\n\n".join(contexts[:5])
            combined = self._truncate_text(combined, 4000)
            
            prompt = f"""Answer this question based ONLY on the context. Be concise (2-3 sentences).

Context:
{combined}

Question: {query}

Answer:"""

            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=150
            )
            
            gt = response.choices[0].message.content.strip()
            logger.info(f"✅ Ground truth generated ({len(gt)} chars)")
            return gt
            
        except Exception as e:
            logger.error(f"❌ Ground truth failed: {e}")
            return ""


    async def evaluate_query(
        self,
        query_id: str,
        query: str,
        response: str,
        sources_used: List[Dict[str, Any]],
        ground_truth: Optional[str] = None
    ) -> Dict[str, float]:
        """Evaluate query with 3 metrics"""
        start_time = datetime.utcnow()

        try:
            # Extract contexts
            contexts: List[str] = []

            for source in sources_used:
                chunk_ids = source.get("chunk_ids", [])
                if not chunk_ids:
                    continue

                result = self.db.execute(
                    text("""
                        SELECT content FROM chunks
                        WHERE id::text = ANY(:ids)
                        ORDER BY array_position(:ids, id::text)
                    """),
                    {"ids": chunk_ids}
                )

                contexts.extend(row.content for row in result)

            if not contexts:
                logger.warning(f"⚠️ No contexts for {query_id}")
                return {}

            contexts = contexts[:5]

            logger.info(f"📊 Evaluating {query_id}: {len(contexts)} contexts, {len(response)} chars")

            # Generate ground truth if needed
            if not ground_truth or not ground_truth.strip():
                logger.info("🤖 Generating ground truth...")
                ground_truth = await self._generate_ground_truth(query, contexts)

            scores: Dict[str, Optional[float]] = {}

            # 1. Answer Relevancy
            try:
                relevancy = await self.answer_relevancy.ascore(
                    user_input=query,
                    response=self._truncate_text(response, 2000)
                )
                scores["answer_relevancy"] = relevancy.value
                logger.info(f"  ✅ Answer Relevancy: {relevancy.value:.3f}")
                
            except Exception as e:
                logger.warning(f"  ⚠️ Answer Relevancy failed: {str(e)[:80]}")
                scores["answer_relevancy"] = None

            # 2. Context Precision
            if ground_truth and ground_truth.strip():
                try:
                    precision = await self.context_precision.ascore(
                        user_input=query,
                        retrieved_contexts=contexts,
                        reference=ground_truth
                    )
                    scores["context_precision"] = precision.value
                    logger.info(f"  ✅ Context Precision: {precision.value:.3f}")
                    
                except Exception as e:
                    logger.warning(f"  ⚠️ Context Precision failed: {str(e)[:80]}")
                    scores["context_precision"] = None
            else:
                scores["context_precision"] = None

            # 3. Context Recall
            if ground_truth and ground_truth.strip():
                try:
                    recall = await self.context_recall.ascore(
                        user_input=query,
                        retrieved_contexts=contexts,
                        reference=ground_truth
                    )
                    scores["context_recall"] = recall.value
                    logger.info(f"  ✅ Context Recall: {recall.value:.3f}")
                    
                except Exception as e:
                    logger.warning(f"  ⚠️ Context Recall failed: {str(e)[:80]}")
                    scores["context_recall"] = None
            else:
                scores["context_recall"] = None

            # Faithfulness always None
            scores["faithfulness"] = None

            # Store
            eval_duration = (datetime.utcnow() - start_time).total_seconds()

            self._store_evaluation(
                query_id=query_id,
                scores=scores,
                contexts_count=len(contexts),
                eval_duration=eval_duration
            )

            track_ragas_metrics(scores)
            track_ragas_duration(eval_duration)

            def fmt(s):
                return f"{s:.3f}" if s is not None else "N/A"
            
            logger.info(
                f"✅ Complete: "
                f"R={fmt(scores.get('answer_relevancy'))}, "
                f"P={fmt(scores.get('context_precision'))}, "
                f"RC={fmt(scores.get('context_recall'))} "
                f"({eval_duration:.2f}s)"
            )

            return scores

        except Exception as e:
            logger.error(f"❌ Evaluation failed: {e}", exc_info=True)
            return {}


    def _store_evaluation(
        self,
        query_id: str,
        scores: Dict[str, Optional[float]],
        contexts_count: int,
        eval_duration: float
    ):
        """Store results with rounded decimals"""
        try:
            # ✅ Helper to round scores to 3 decimals
            def round_score(score):
                return round(score, 3) if score is not None else None
            
            self.db.execute(
                text("""
                    INSERT INTO ragas_evaluations (
                        query_id,
                        faithfulness,
                        answer_relevancy,
                        context_precision,
                        context_recall,
                        contexts_count,
                        eval_duration_seconds,
                        evaluated_at
                    ) VALUES (
                        :qid, :faith, :rel, :prec, :rec, :ctx, :dur, CURRENT_TIMESTAMP
                    )
                """),
                {
                    "qid": query_id,
                    "faith": round_score(scores.get("faithfulness")),      # Rounded to 3 decimals
                    "rel": round_score(scores.get("answer_relevancy")),    # Rounded to 3 decimals
                    "prec": round_score(scores.get("context_precision")),  # Rounded to 3 decimals
                    "rec": round_score(scores.get("context_recall")),      # Rounded to 3 decimals
                    "ctx": contexts_count,
                    "dur": round(eval_duration, 2),  # Rounded to 2 decimals
                }
            )
            self.db.commit()
            logger.info("✅ Stored evaluation")
        except Exception as e:
            logger.error(f"❌ Store failed: {e}")
            try:
                self.db.rollback()
            except:
                pass


    def get_query_evaluation(self, query_id: str) -> Optional[Dict[str, Any]]:
        """Get evaluation"""
        try:
            result = self.db.execute(text("""
                SELECT faithfulness, answer_relevancy, context_precision,
                       context_recall, contexts_count, eval_duration_seconds, evaluated_at
                FROM ragas_evaluations WHERE query_id = :qid
            """), {"qid": query_id})
            
            row = result.fetchone()
            if row:
                return {
                    "faithfulness": row.faithfulness,
                    "answer_relevancy": row.answer_relevancy,
                    "context_precision": row.context_precision,
                    "context_recall": row.context_recall,
                    "contexts_count": row.contexts_count,
                    "eval_duration_seconds": row.eval_duration_seconds,
                    "evaluated_at": row.evaluated_at.isoformat() if row.evaluated_at else None
                }
            return None
        except Exception as e:
            logger.error(f"❌ Get failed: {e}")
            return None
    
    
    def get_aggregate_metrics(
        self,
        user_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, float]:
        """Get aggregate metrics"""
        try:
            filters = ["evaluated_at >= CURRENT_TIMESTAMP - INTERVAL '%s days'" % days]
            params = {}
            
            if user_id:
                filters.append("q.user_id = :uid")
                params["uid"] = user_id
            if collection_id:
                filters.append("q.collection_id = :cid")
                params["cid"] = collection_id
            
            where = " AND ".join(filters)
            
            result = self.db.execute(text(f"""
                SELECT 
                    COUNT(*) as total,
                    AVG(faithfulness) as f,
                    AVG(answer_relevancy) as r,
                    AVG(context_precision) as p,
                    AVG(context_recall) as rc,
                    AVG(eval_duration_seconds) as dur
                FROM ragas_evaluations re
                JOIN queries q ON re.query_id = q.id
                WHERE {where}
            """), params)
            
            row = result.fetchone()
            if row:
                return {
                    "total_evaluations": row.total,
                    "avg_faithfulness": round(row.f, 3) if row.f else None,
                    "avg_answer_relevancy": round(row.r, 3) if row.r else None,
                    "avg_context_precision": round(row.p, 3) if row.p else None,
                    "avg_context_recall": round(row.rc, 3) if row.rc else None,
                    "avg_eval_duration": round(row.dur, 2) if row.dur else None,
                }
            return {}
        except Exception as e:
            logger.error(f"❌ Aggregate failed: {e}")
            return {}