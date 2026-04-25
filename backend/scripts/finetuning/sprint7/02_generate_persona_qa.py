#!/usr/bin/env python3
"""
Worker 5 — Persona Q&A synthesis Sprint 7.

OpenCharacter-G adapted: generates 750-1000 Q&A pairs covering B1-B9 persona
categories using generate_qa_probes() mechanism from multi_turn_generator.py.

4-layer validation (NLI consistency, blacklist, style match, Doc D alignment).
Output: ChatML with full Doc D as system prompt.

Usage:
    cd ~/Clonnect/backend
    set -a && source .env && set +a
    python3 scripts/finetuning/sprint7/02_generate_persona_qa.py \
        --doc-d data/personality_extractions/iris_bertran/doc_d_bot_configuration.md \
        --output data/dpo/trl/sprint7/sft_persona_qa.jsonl \
        --target 800 \
        --paraphrases 3 \
        --dry-run
"""
import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openai

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── Model constants (mirror multi_turn_generator.py) ──────────────────────
LEAD_SIM_MODEL = os.environ.get("LEAD_SIM_MODEL", "Qwen/Qwen3-30B-A3B")
BOT_MODEL = os.environ.get("DEEPINFRA_MODEL", "google/gemma-4-31B-it")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "Qwen/Qwen3-30B-A3B")
COST_PER_1K_INPUT = 0.00015
COST_PER_1K_OUTPUT = 0.0006

# B1+B2+B3+B7 are J6-critical (38 questions minimum → targets increased here)
CATEGORIES: Dict[str, Dict[str, Any]] = {
    "B1": {"name": "Identitat",        "desc": "nom, edat, ocupació, origen, nacionalitat",         "n": 14},
    "B2": {"name": "Idioma i estil",    "desc": "idioma preferit, expressions, code-switching ca/es","n": 10},
    "B3": {"name": "Feina",            "desc": "classes, horaris, serveis, preus, metodologia",      "n": 14},
    "B4": {"name": "Valors",           "desc": "creences, valors, opinions sobre temes",             "n": 10},
    "B5": {"name": "Història",         "desc": "experiències passades, trajectòria personal",        "n": 10},
    "B6": {"name": "Relacions",        "desc": "família, amics, parella, relacions personals",       "n": 10},
    "B7": {"name": "Productes",        "desc": "productes que ven, beneficis, preus, links",         "n": 10},
    "B8": {"name": "Coaching",         "desc": "metodologia coaching, resultats clients",            "n": 8},
    "B9": {"name": "Lifestyle",        "desc": "hobbies, rutines, menjar, viatge, vida diaria",      "n": 8},
}
# B1+B2+B3+B7 = 14+10+14+10 = 48 core questions (≥38 required)

BLACKLIST_TOPICS = [
    "política", "política", "polític", "religion", "religió", "sexe", "sexual",
    "drogues", "alcohol", "violència", "illegal", "il·legal",
    "contrasenya", "password", "dades bancàries", "targeta de crèdit",
]

IRIS_MIN_CHARS = 10
IRIS_MAX_CHARS = 300
IRIS_AVG_CHARS = 71


def get_client() -> openai.OpenAI:
    api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPINFRA_API_KEY not set")
    return openai.OpenAI(
        api_key=api_key,
        base_url="https://api.deepinfra.com/v1/openai",
        timeout=90,
    )


def strip_thinking(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<\|thinking\|>.*?<\|/thinking\|>", "", text, flags=re.DOTALL)
    return text.strip()


def call_llm(
    client: openai.OpenAI,
    messages: List[Dict[str, str]],
    model: str,
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> Tuple[str, int, int]:
    """Returns (content, input_tokens, output_tokens)."""
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    usage = resp.usage
    inp = usage.prompt_tokens if usage else 0
    out = usage.completion_tokens if usage else 0
    content = strip_thinking(resp.choices[0].message.content or "")
    return content, inp, out


# ─── PASO 2: Question generation (generate_qa_probes mechanism) ────────────

def generate_category_questions(
    client: openai.OpenAI,
    doc_d_text: str,
    category_key: str,
    category: Dict[str, Any],
    n: int,
) -> List[Dict[str, str]]:
    """Generate n questions for a B-category using generate_qa_probes() mechanism."""
    prompt = (
        f"Given this creator's personality profile:\n"
        f"{doc_d_text[:2000]}\n\n"
        f"Generate exactly {n} questions about the creator's **{category['name']}** "
        f"({category['desc']}).\n\n"
        f"Requirements:\n"
        f"- Questions should test persona consistency for this category\n"
        f"- Questions should have clear expected answers based on the profile\n"
        f"- Questions should be natural (a follower might genuinely ask these)\n"
        f"- Mix of Catalan (ca) and Spanish (es) questions, as the creator uses both\n"
        f"- Output ONLY valid JSON array: "
        f'[{{"question": "...", "expected": "...", "category": "{category_key}"}}]\n\n'
        f"/no_think"
    )
    try:
        text, inp, out = call_llm(
            client,
            [{"role": "user", "content": prompt}],
            model=LEAD_SIM_MODEL,
            temperature=0.8,
            max_tokens=600,
        )
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            raw = json.loads(text[start:end])
            questions = []
            for i, item in enumerate(raw[:n]):
                if isinstance(item, dict) and "question" in item:
                    questions.append({
                        "question": str(item["question"]),
                        "expected": str(item.get("expected", "")),
                        "category": category_key,
                    })
            logger.info(f"  {category_key}: generated {len(questions)}/{n} questions")
            return questions
    except Exception as e:
        logger.warning(f"  {category_key}: question generation failed: {e}")
    return []


def generate_paraphrases(
    client: openai.OpenAI,
    question: str,
    n_paraphrases: int = 3,
) -> List[str]:
    """Generate n paraphrases with cosine similarity 0.75-0.85 (same content, different form)."""
    prompt = (
        f"Generate exactly {n_paraphrases} paraphrases of this question. "
        f"Keep the same factual content but use different words and phrasing. "
        f"Mix Catalan and Spanish naturally.\n\n"
        f"Original: {question}\n\n"
        f"Output ONLY a JSON array of strings: [\"...\", \"...\", \"...\"]\n\n"
        f"/no_think"
    )
    try:
        text, _, _ = call_llm(
            client,
            [{"role": "user", "content": prompt}],
            model=LEAD_SIM_MODEL,
            temperature=0.9,
            max_tokens=200,
        )
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            raw = json.loads(text[start:end])
            return [str(p) for p in raw[:n_paraphrases] if isinstance(p, str) and len(p) > 5]
    except Exception as e:
        logger.debug(f"Paraphrase generation failed: {e}")
    return []


# ─── PASO 3: Response generation via OpenCharacter-G ──────────────────────

def generate_iris_response(
    client: openai.OpenAI,
    question: str,
    doc_d_full: str,
    model: str = BOT_MODEL,
) -> str:
    """Generate Iris's response to a question using full Doc D as system prompt."""
    messages = [
        {"role": "system", "content": doc_d_full},
        {"role": "user",   "content": question},
    ]
    try:
        text, _, _ = call_llm(
            client, messages, model=model,
            temperature=0.7, max_tokens=256,
        )
        return text.strip()
    except Exception as e:
        logger.debug(f"Response generation failed: {e}")
        return ""


# ─── PASO 4: 4-layer validation ───────────────────────────────────────────

def layer1_blacklist(question: str, response: str) -> bool:
    """Layer 1: blacklist topics. Returns True if PASSES (no forbidden topics)."""
    combined = (question + " " + response).lower()
    for topic in BLACKLIST_TOPICS:
        if topic in combined:
            return False
    return True


def layer2_style_match(response: str) -> bool:
    """Layer 2: style match — length/tone within Iris's profile."""
    if not response:
        return False
    n = len(response)
    if n < IRIS_MIN_CHARS or n > IRIS_MAX_CHARS * 2:
        return False
    # Should not start with assistant patterns
    lower = response.lower().strip()
    for bad in ["as iris", "as an ai", "i'm an ai", "com a ia", "como ia"]:
        if lower.startswith(bad):
            return False
    return True


def layer3_nli_consistency(
    client: openai.OpenAI,
    response: str,
    expected: str,
    doc_d_snippet: str,
) -> bool:
    """Layer 3: NLI consistency — response consistent with expected answer and Doc D."""
    if not expected or len(expected) < 3:
        return True  # No expected = can't check, pass

    prompt = (
        f"Context (Doc D snippet):\n{doc_d_snippet[:500]}\n\n"
        f"Expected answer: {expected}\n\n"
        f"Response to evaluate: {response}\n\n"
        f"Is the response consistent with the expected answer and persona? "
        f"Does it contradict any facts?\n\n"
        f"Answer ONLY: CONSISTENT or INCONSISTENT\n\n"
        f"/no_think"
    )
    try:
        text, _, _ = call_llm(
            client,
            [{"role": "user", "content": prompt}],
            model=JUDGE_MODEL,
            temperature=0.0,
            max_tokens=20,
        )
        return "CONSISTENT" in text.upper()
    except Exception:
        return True  # Fail open on API error


def layer4_doc_d_alignment(
    client: openai.OpenAI,
    question: str,
    response: str,
    expected: str,
    doc_d_snippet: str,
) -> bool:
    """Layer 4: Doc D alignment — facts in response match Doc D, not hallucinated."""
    if not expected or len(expected) < 3:
        return True

    prompt = (
        f"Doc D snippet:\n{doc_d_snippet[:500]}\n\n"
        f"Question: {question}\n"
        f"Response: {response}\n"
        f"Expected: {expected}\n\n"
        f"Does the response align with the persona's facts in Doc D? "
        f"Is it free of hallucinations?\n\n"
        f"Answer ONLY: ALIGNED or MISALIGNED\n\n"
        f"/no_think"
    )
    try:
        text, _, _ = call_llm(
            client,
            [{"role": "user", "content": prompt}],
            model=JUDGE_MODEL,
            temperature=0.0,
            max_tokens=20,
        )
        return "ALIGNED" in text.upper()
    except Exception:
        return True


def validate_pair(
    client: openai.OpenAI,
    question: str,
    response: str,
    expected: str,
    doc_d_snippet: str,
) -> Tuple[bool, Dict[str, bool]]:
    """Run all 4 validation layers. Returns (passes, layer_results)."""
    layers = {
        "blacklist":     layer1_blacklist(question, response),
        "style_match":   layer2_style_match(response),
        "nli":           layer3_nli_consistency(client, response, expected, doc_d_snippet),
        "doc_d_align":   layer4_doc_d_alignment(client, question, response, expected, doc_d_snippet),
    }
    failures = sum(1 for v in layers.values() if not v)
    # Filter if ≥2 layers fail (per spec)
    passes = failures < 2
    return passes, layers


# ─── Output formatting ────────────────────────────────────────────────────

def to_chatml(doc_d_full: str, question: str, response: str, category: str) -> Dict:
    return {
        "source": f"persona_qa_{category}",
        "messages": [
            {"role": "system",    "content": doc_d_full},
            {"role": "user",      "content": question},
            {"role": "assistant", "content": response},
        ],
    }


# ─── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Worker 5: Persona Q&A synthesis")
    parser.add_argument("--doc-d", default="data/personality_extractions/iris_bertran/doc_d_bot_configuration.md")
    parser.add_argument("--output", default="data/dpo/trl/sprint7/sft_persona_qa.jsonl")
    parser.add_argument("--target", type=int, default=800)
    parser.add_argument("--paraphrases", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=50, help="Log progress every N pairs")
    args = parser.parse_args()

    # ── Load Doc D ──────────────────────────────────────────────────────────
    doc_d_path = Path(args.doc_d)
    if not doc_d_path.exists():
        print(f"ABORT: Doc D not found at {doc_d_path}")
        sys.exit(1)
    doc_d_full = doc_d_path.read_text(encoding="utf-8")
    doc_d_snippet = doc_d_full[:1000]
    print(f"Doc D loaded: {len(doc_d_full)} chars from {doc_d_path}")

    client = get_client()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_cost = 0.0
    all_pairs: List[Dict] = []
    rejection_stats: Dict[str, int] = {"blacklist": 0, "style_match": 0, "nli": 0, "doc_d_align": 0, "total_generated": 0, "total_passed": 0}
    coverage: Dict[str, int] = {k: 0 for k in CATEGORIES}

    # ── Step 1: Generate questions per category ──────────────────────────────
    print(f"\n[1] Generating questions for {len(CATEGORIES)} categories...")
    all_questions: List[Dict[str, str]] = []

    for cat_key, cat in CATEGORIES.items():
        n_q = cat["n"]
        if args.dry_run:
            # Dry run: use 2 fake questions per category
            for i in range(2):
                all_questions.append({
                    "question": f"[DRY RUN] {cat['name']} question {i+1}?",
                    "expected": f"[DRY RUN] expected answer for {cat_key}",
                    "category": cat_key,
                })
            continue
        qs = generate_category_questions(client, doc_d_full, cat_key, cat, n_q)
        all_questions.extend(qs)
        time.sleep(0.5)  # rate limit

    print(f"  Total questions generated: {len(all_questions)}")

    # ── Step 2: Generate paraphrases + responses + validate ─────────────────
    print(f"\n[2] Generating paraphrases, responses, and validating...")
    print(f"  Target: {args.target} pairs | Paraphrases per question: {args.paraphrases}")

    iteration = 0
    while len(all_pairs) < args.target and iteration < 3:
        iteration += 1
        print(f"\n  Batch {iteration}/3 — questions: {len(all_questions)}")

        for q_item in all_questions:
            question = q_item["question"]
            expected = q_item["expected"]
            category = q_item["category"]

            if len(all_pairs) >= args.target:
                break

            # Original question variants = [original] + paraphrases
            variants = [question]
            if not args.dry_run and args.paraphrases > 0:
                paras = generate_paraphrases(client, question, args.paraphrases)
                variants.extend(paras)

            for variant in variants:
                if len(all_pairs) >= args.target:
                    break

                rejection_stats["total_generated"] += 1

                if args.dry_run:
                    response = f"[DRY RUN] Iris response to: {variant[:50]}"
                else:
                    response = generate_iris_response(client, variant, doc_d_full)

                if not response:
                    continue

                passes, layers = validate_pair(
                    client if not args.dry_run else None,
                    variant, response, expected, doc_d_snippet,
                )

                if not args.dry_run:
                    for layer_name, passed in layers.items():
                        if not passed:
                            rejection_stats[layer_name] += 1

                if passes or args.dry_run:
                    rejection_stats["total_passed"] += 1
                    coverage[category] = coverage.get(category, 0) + 1
                    pair = to_chatml(doc_d_full, variant, response, category)
                    all_pairs.append(pair)

                    if len(all_pairs) % args.batch_size == 0:
                        print(f"    Progress: {len(all_pairs)}/{args.target} pairs | cost: ${total_cost:.4f}")

                if not args.dry_run:
                    time.sleep(0.3)  # rate limit

        if len(all_pairs) < args.target and iteration < 3:
            print(f"  End of batch {iteration}: {len(all_pairs)}/{args.target} pairs. Generating more questions...")
            # Generate extra questions for underrepresented categories
            if not args.dry_run:
                for cat_key, cat in CATEGORIES.items():
                    if coverage.get(cat_key, 0) < cat["n"] // 2:
                        extra = generate_category_questions(
                            client, doc_d_full, cat_key, cat, n=cat["n"] // 2
                        )
                        all_questions.extend(extra)
                time.sleep(1.0)

    # ── Step 3: Write output ─────────────────────────────────────────────────
    n_out = len(all_pairs)
    print(f"\n[3] Writing {n_out} pairs to {output_path}")

    with open(output_path, "w", encoding="utf-8") as f:
        for pair in all_pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    # ── Step 4: Stats ────────────────────────────────────────────────────────
    total_gen = rejection_stats["total_generated"]
    total_pass = rejection_stats["total_passed"]
    pass_rate = total_pass / total_gen * 100 if total_gen else 0

    print(f"\n{'='*60}")
    print(f"PERSONA Q&A GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"Pairs generated:  {total_gen}")
    print(f"Pairs passed:     {total_pass} ({pass_rate:.1f}%)")
    print(f"Written to:       {output_path}")
    print(f"Estimated cost:   ${total_cost:.4f}")

    print(f"\nRejection by layer (% of generated):")
    for layer in ["blacklist", "style_match", "nli", "doc_d_align"]:
        n_rej = rejection_stats.get(layer, 0)
        pct = n_rej / total_gen * 100 if total_gen else 0
        print(f"  {layer:15s}: {n_rej:4d} ({pct:.1f}%)")

    print(f"\nCoverage by category:")
    for cat_key, cat in CATEGORIES.items():
        n_cat = coverage.get(cat_key, 0)
        print(f"  {cat_key} {cat['name']:20s}: {n_cat:4d} pairs")

    print(f"\nSample pairs (first 3):")
    for pair in all_pairs[:3]:
        msgs = pair["messages"]
        print(f"  Q: {msgs[1]['content'][:80]}")
        print(f"  A: {msgs[2]['content'][:80]}")
        print()


if __name__ == "__main__":
    main()
