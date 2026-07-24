# Context Builder & Map‑Reduce Orchestration

"""Utility functions for assembling a balanced retrieval context and for a simple
Map‑Reduce generation workflow.

This module provides:

1. **Diverse chunk selection** – Ensures that chunks originating from different
   structural sections (e.g. headings in `rag.pdf`) are evenly represented in the
   final context window.
2. **Map‑Reduce orchestration** – A two‑step generation strategy where the LLM
   first extracts architectural facts from individual chunks (the *map* step) and
   then synthesises a polished summary (the *reduce* step).

Both utilities are designed to be plug‑and‑play: the RAG generation pipeline can
import ``build_diverse_context`` (see ``rag_generation.py``).  The ``map_reduce_extractions``
function can be called from ``RAGGenerator`` or any custom endpoint that wishes to
employ the Map‑Reduce pattern.
"""

import logging
import json
import re
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1️⃣  Diverse Context Selection
# ---------------------------------------------------------------------------

def _group_by_section(chunks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group chunks by a *section* identifier.

    The underlying ``doc_processor`` stores metadata such as ``section`` or
    ``section_title``.  We fall back to ``"unknown"`` when no explicit value is
    present.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for chunk in chunks:
        meta = chunk.get("metadata", {}) or {}
        section = meta.get("section") or meta.get("section_title") or "unknown"
        groups.setdefault(section, []).append(chunk)
    return groups


def _select_diverse_chunks(
    chunks: List[Dict[str, Any]],
    max_chunks: int = 10,
    max_chars: int = 3000,
) -> List[Dict[str, Any]]:
    """Round‑robin selection across sections until size limits are hit.

    The algorithm iterates over the groups in a deterministic order, pulling one
    chunk from each group per cycle.  It stops when either ``max_chunks`` or
    ``max_chars`` constraints are satisfied.
    """
    if not chunks:
        return []

    groups = _group_by_section(chunks)
    iterators = {sec: iter(lst) for sec, lst in groups.items()}

    selected: List[Dict[str, Any]] = []
    total_chars = 0
    while len(selected) < max_chunks and total_chars < max_chars:
        made_progress = False
        for sec, it in list(iterators.items()):
            try:
                chunk = next(it)
                chunk_len = len(chunk.get("content", ""))
                if total_chars + chunk_len > max_chars:
                    continue
                selected.append(chunk)
                total_chars += chunk_len
                made_progress = True
                if len(selected) >= max_chunks:
                    break
            except StopIteration:
                del iterators[sec]
        if not made_progress:
            break
    return selected


def build_diverse_context(
    chunks: List[Dict[str, Any]],
    max_chunks: int = 10,
    max_context_chars: int = 4000,
) -> List[Dict[str, Any]]:
    """Return a list of chunk dictionaries balanced across sections.
    """
    selected = _select_diverse_chunks(
        chunks, max_chunks=max_chunks, max_chars=max_context_chars
    )
    logger.info(
        f"Selected {len(selected)} diverse chunks (max_chunks={max_chunks}, max_chars={max_context_chars})"
    )
    return selected

# ---------------------------------------------------------------------------
# 2️⃣  Map‑Reduce Generation Flow
# ---------------------------------------------------------------------------

def _extract_facts_from_batch(rag_generator, batch_content: str) -> List[Dict[str, Any]]:
    """Call the LLM with a focused extraction prompt for a batch of text.

    Returns a list of dicts with key facts, concepts, and key points.
    """
    extraction_prompt = (
        "You are an expert technical analyst. From the following excerpt, extract "
        "the main topics, key concepts, important facts, questions & answers, or procedures mentioned.\n"
        "Provide a JSON list where each item has the keys: \"topic\", \"key_points\", \"details\".\n\n"
        f"Text:\n{batch_content}\n"
    )
    # Direct LLM call without retrieval to extract facts
    messages = [{"role": "user", "content": extraction_prompt}]
    completion = rag_generator.model_manager.get_chat_completion(messages=messages, stream=False)
    if hasattr(completion, "choices"):
        response_text = completion.choices[0].message.content
    else:
        response_text = str(completion)
    try:
        match = re.search(r"\[.*\]", response_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        logger.warning(f"Failed to parse extraction JSON: {e}")
    return []


def map_reduce_extractions(
    rag_generator,
    query: str,
    chunks: List[Dict[str, Any]],
    batch_size: int = 3,
) -> Any:
    """Orchestrate a Map‑Reduce style generation for document summarization.

    *Map* – Process chunks in small batches, extracting key facts.
    *Reduce* – Synthesize those facts into a final structured summary of the document.
    """
    # Map step
    all_facts: List[Dict[str, Any]] = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        combined = "\n\n".join(c.get("content", "") for c in batch)
        batch_facts = _extract_facts_from_batch(rag_generator, combined)
        all_facts.extend(batch_facts)

    if not all_facts:
        logger.info("No facts extracted – falling back to normal generation.")
        return rag_generator.generate_response(
            query=query,
            top_k=len(chunks),
            user_id="system",
            collection_id="system",
            selected_document_ids=None,
            memory_context="",
            response_language="English",
            conversational_style="default",
            chat_length="long",
        )

    synthesis_prompt = (
        f"You are an expert document analyst. Using the extracted facts below from the user's document, "
        f"generate a comprehensive, high-quality, structured summary that directly answers the user query: '{query}'.\n\n"
        "GUIDELINES:\n"
        "1. Base your summary ENTIRELY on the extracted facts provided below.\n"
        "2. Do NOT mention any external RAG architectures or irrelevant concepts unless they are explicitly present in the extracted facts.\n"
        "3. Use clear markdown headers (## Overview, ## Key Topics / Findings, ## Detailed Breakdown, ## Conclusion) and bullet points.\n"
        "4. Include key Q&As, steps, code snippets, or rules if present in the facts.\n\n"
        f"Extracted facts from document:\n{json.dumps(all_facts, ensure_ascii=False, indent=2)}"
    )

    final_result = rag_generator.generate_response(
        query=synthesis_prompt,
        top_k=0,
        user_id="system",
        collection_id="system",
        selected_document_ids=None,
        memory_context="",
        response_language="English",
        conversational_style="default",
        chat_length="long",
    )

    # Format and populate sources used
    try:
        _, sources_info, _ = rag_generator._format_context_with_citations(chunks)
        final_result.sources_used = sources_info
        final_result.retrieval_count = len(chunks)
    except Exception as e:
        logger.warning(f"Failed to populate sources in Map-Reduce final result: {e}")

    return final_result

__all__ = ["build_diverse_context", "map_reduce_extractions"]
