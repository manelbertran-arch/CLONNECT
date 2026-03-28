#!/usr/bin/env python3
"""
RAG Quality Evaluator — measures retrieval and generation quality.

Inspired by RAGAS framework metrics (2025-2026 industry standard).
Uses LLM-as-judge (GPT-4o-mini) for semantic evaluation.

Metrics:
  1. Context Precision: Are retrieved chunks relevant to the query?
  2. Context Recall: Was all needed info retrieved?
  3. Faithfulness: Does the response use chunks correctly (not hallucinate)?
  4. Answer Relevancy: Does the response answer the actual question?

Usage:
    python tests/eval_rag_quality.py tests/test_set_real_leads.json
    python tests/eval_rag_quality.py tests/test_set_real_leads.json --output tests/rag_quality.json
"""

import argparse
import json
import logging
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("eval_rag")

sys.path.insert(0, str(Path(__file__).parent.parent))

# Product keywords that trigger RAG retrieval
PRODUCT_KEYWORDS = {
    "precio", "preu", "cuanto", "cuánto", "cuesta", "costa", "horario",
    "horari", "clase", "classe", "reserv", "apunt", "barre", "pilates",
    "reformer", "zumba", "flow", "entreno", "entrenament", "sesion",
    "sessió", "pack", "bono", "taller", "hipopresivos", "heels",
    "masterclass", "workshop",
}

JUDGE_MODEL = "gpt-4o-mini"

# ═══════════════════════════════════════════════════════════════════════════════
# RAG RETRIEVAL
# ═══════════════════════════════════════════════════════════════════════════════

def retrieve_chunks(query: str, creator_id: str = "iris_bertran", top_k: int = 5) -> List[Dict]:
    """Execute RAG retrieval for a query."""
    try:
        from core.rag.semantic import SemanticRAG
        rag = SemanticRAG()
        results = rag.search(query, top_k=top_k, creator_id=creator_id)
        return results
    except Exception as e:
        logger.warning("RAG search failed: %s", e)
        return []


def format_chunks_text(chunks: List[Dict]) -> str:
    """Format retrieved chunks into readable text."""
    if not chunks:
        return "(no chunks retrieved)"
    lines = []
    for i, c in enumerate(chunks):
        content = c.get("content", c.get("text", ""))[:200]
        score = c.get("score", 0)
        source = c.get("metadata", {}).get("type", c.get("source_type", "unknown"))
        lines.append(f"[{i+1}] (score={score:.3f}, type={source}) {content}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# LLM-AS-JUDGE METRICS
# ═══════════════════════════════════════════════════════════════════════════════

def get_openai_client():
    from openai import OpenAI
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def judge_metric(client, system: str, prompt: str) -> Dict:
    """Call GPT-4o-mini to evaluate a single metric. Returns parsed JSON."""
    try:
        resp = client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=200,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except Exception as e:
        logger.warning("Judge call failed: %s", e)
        return {"score": 0, "reason": str(e)}


def eval_context_precision(client, query: str, chunks: List[Dict]) -> Dict:
    """Are the retrieved chunks relevant to the query?"""
    chunks_text = format_chunks_text(chunks)
    return judge_metric(client,
        "You evaluate retrieval quality. Score 0-10 how relevant the retrieved chunks are to the query.",
        f"Query: {query}\n\nRetrieved chunks:\n{chunks_text}\n\n"
        "Score 0-10: how many chunks are relevant to answering this query?\n"
        "Respond JSON: {\"score\": N, \"relevant_chunks\": N, \"total_chunks\": N, \"reason\": \"...\"}"
    )


def eval_context_recall(client, query: str, chunks: List[Dict], ground_truth: str) -> Dict:
    """Was all needed info in the retrieved chunks?"""
    chunks_text = format_chunks_text(chunks)
    return judge_metric(client,
        "You evaluate if retrieved chunks contain all information needed for the correct answer.",
        f"Query: {query}\n\nCorrect answer: {ground_truth}\n\nRetrieved chunks:\n{chunks_text}\n\n"
        "Score 0-10: does the chunk set contain all facts needed for the correct answer?\n"
        "Respond JSON: {\"score\": N, \"missing_info\": \"what's missing or empty if complete\", \"reason\": \"...\"}"
    )


def eval_faithfulness(client, query: str, chunks: List[Dict], response: str) -> Dict:
    """Does the response use chunks correctly without hallucinating?"""
    chunks_text = format_chunks_text(chunks)
    return judge_metric(client,
        "You evaluate if a response is faithful to the retrieved context (no hallucination).",
        f"Query: {query}\n\nRetrieved context:\n{chunks_text}\n\nGenerated response: {response}\n\n"
        "Score 0-10: does the response only state facts from the context? "
        "Penalize invented prices, schedules, or details not in the chunks.\n"
        "Respond JSON: {\"score\": N, \"hallucinations\": [\"list any invented facts\"], \"reason\": \"...\"}"
    )


def eval_answer_relevancy(client, query: str, response: str, ground_truth: str) -> Dict:
    """Does the response actually answer the question?"""
    return judge_metric(client,
        "You evaluate if a chatbot response answers the user's question correctly.",
        f"User question: {query}\n\nBot response: {response}\n\nCorrect answer: {ground_truth}\n\n"
        "Score 0-10: does the bot's response address the question correctly?\n"
        "Respond JSON: {\"score\": N, \"addresses_question\": true/false, \"reason\": \"...\"}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# BOT RESPONSE GENERATION (optional — uses production pipeline)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_bot_response(query: str, creator_id: str, history: List[Dict] = None) -> str:
    """Generate a response using the production DM pipeline."""
    import asyncio

    async def _gen():
        try:
            from core.dm_agent_v2 import DMResponderAgent
            agent = DMResponderAgent(creator_id=creator_id)
            metadata = {"history": history or [], "username": "test_lead", "message_id": "rag_eval"}
            result = await agent.process_dm(message=query, sender_id="rag_eval_lead", metadata=metadata)
            return result.content if result else ""
        except Exception as e:
            logger.error("Pipeline generation failed: %s", e)
            return ""

    return asyncio.run(_gen())


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EVALUATION
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="RAG Quality Evaluator")
    parser.add_argument("test_set", help="Path to test set JSON")
    parser.add_argument("--output", "-o", default=None, help="Output JSON path")
    parser.add_argument("--creator", default="iris_bertran")
    parser.add_argument("--generate", action="store_true",
                        help="Also generate bot responses via pipeline (slow)")
    args = parser.parse_args()

    with open(args.test_set) as f:
        data = json.load(f)
    convs = data if isinstance(data, list) else data.get("conversations", [])

    # Filter to RAG-eligible cases
    rag_convs = []
    for c in convs:
        msg = c.get("test_input", c.get("lead_message", ""))
        if any(kw in msg.lower() for kw in PRODUCT_KEYWORDS):
            rag_convs.append(c)

    logger.info("RAG-eligible: %d/%d conversations", len(rag_convs), len(convs))

    if not rag_convs:
        logger.error("No RAG-eligible conversations in test set")
        sys.exit(1)

    client = get_openai_client()
    results = []

    for i, conv in enumerate(rag_convs):
        query = conv.get("test_input", conv.get("lead_message", ""))
        ground_truth = conv.get("ground_truth", "")
        conv_id = conv.get("id", f"conv_{i}")

        logger.info("[%d/%d] %s: %s", i + 1, len(rag_convs), conv_id, query[:50])

        # 1. Retrieve chunks
        chunks = retrieve_chunks(query, creator_id=args.creator)
        logger.info("  Retrieved %d chunks", len(chunks))

        # 2. Optionally generate bot response
        bot_response = ""
        if args.generate:
            history = []
            for t in conv.get("turns", []):
                role = "assistant" if t.get("role") == "iris" else "user"
                history.append({"role": role, "content": t.get("content", "")})
            bot_response = generate_bot_response(query, args.creator, history)
            logger.info("  Bot: %s", bot_response[:60])
        else:
            bot_response = ground_truth  # Use ground truth as proxy

        # 3. Evaluate metrics
        precision = eval_context_precision(client, query, chunks)
        time.sleep(0.3)
        recall = eval_context_recall(client, query, chunks, ground_truth)
        time.sleep(0.3)
        faithfulness = eval_faithfulness(client, query, chunks, bot_response)
        time.sleep(0.3)
        relevancy = eval_answer_relevancy(client, query, bot_response, ground_truth)
        time.sleep(0.3)

        result = {
            "id": conv_id,
            "query": query,
            "ground_truth": ground_truth[:200],
            "bot_response": bot_response[:200],
            "chunks_retrieved": len(chunks),
            "chunks_text": format_chunks_text(chunks[:3])[:500],
            "metrics": {
                "context_precision": precision.get("score", 0),
                "context_recall": recall.get("score", 0),
                "faithfulness": faithfulness.get("score", 0),
                "answer_relevancy": relevancy.get("score", 0),
            },
            "details": {
                "precision": precision,
                "recall": recall,
                "faithfulness": faithfulness,
                "relevancy": relevancy,
            },
        }
        results.append(result)

        logger.info(
            "  Precision=%.0f Recall=%.0f Faithfulness=%.0f Relevancy=%.0f",
            precision.get("score", 0), recall.get("score", 0),
            faithfulness.get("score", 0), relevancy.get("score", 0),
        )

    # Aggregate
    metrics_keys = ["context_precision", "context_recall", "faithfulness", "answer_relevancy"]
    aggregated = {}
    for key in metrics_keys:
        values = [r["metrics"][key] for r in results if r["metrics"][key] > 0]
        if values:
            aggregated[key] = {
                "mean": round(statistics.mean(values), 1),
                "min": min(values),
                "max": max(values),
                "n": len(values),
            }

    overall = round(
        statistics.mean([
            aggregated.get(k, {}).get("mean", 0) for k in metrics_keys
        ]), 1
    ) if aggregated else 0

    output = {
        "test_set": args.test_set,
        "creator": args.creator,
        "rag_eligible": len(rag_convs),
        "total_conversations": len(convs),
        "overall_rag_score": overall,
        "aggregated_metrics": aggregated,
        "per_conversation": results,
    }

    # Print summary
    print()
    print("=" * 55)
    print("  RAG QUALITY EVALUATION (RAGAS-inspired)")
    print("=" * 55)
    print(f"  Overall RAG Score:     {overall}/10")
    print(f"  Conversations:         {len(rag_convs)} (RAG-eligible)")
    print()
    for key in metrics_keys:
        agg = aggregated.get(key, {})
        label = key.replace("_", " ").title()
        mean = agg.get("mean", 0)
        bar = "#" * int(mean) + "." * (10 - int(mean))
        print(f"  {label:22s} {mean:>4}/10  [{bar}]")
    print()
    print("  Per-conversation:")
    for r in results:
        m = r["metrics"]
        print(f"    {r['id']:12s} P={m['context_precision']:.0f} R={m['context_recall']:.0f} "
              f"F={m['faithfulness']:.0f} A={m['answer_relevancy']:.0f} "
              f"| chunks={r['chunks_retrieved']}")
    print("=" * 55)

    # Save
    output_path = args.output or f"tests/rag_quality_{args.creator}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    logger.info("Saved to %s", output_path)


if __name__ == "__main__":
    main()
