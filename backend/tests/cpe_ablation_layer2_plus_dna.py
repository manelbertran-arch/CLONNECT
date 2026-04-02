"""
CPE Ablation — Layer 2 + System #8 (Relationship DNA Engine).

Adds per-lead relationship DNA (type, vocabulary, trust, topics, golden examples)
on top of Layer 2 baseline (Doc D v3 + full Fase 1 detection pipeline).

Layer 2 systems active:
  #4 Input Guards, #1 Sensitive, #5 Pool Matching, #2 Frustration, #3 Context Signals
  + Doc D v3 system prompt

System #8 adds:
  - RelationshipDNA: type (FAMILIA/AMISTAD/CLIENTE/...), trust_score, depth_level
  - Vocabulary guidance: words to use, words to avoid
  - Emoji patterns per relationship
  - Recurring topics, private references
  - Golden examples (few-shot from this specific lead)
  - Bot instructions

Protocol:
  - 50 cases × 3 runs = 150 observations
  - L1 (9 text metrics) + L2 (5 lexical) + L3 (BERTScore + rep + hallucination)
  - Wilcoxon + Cliff's delta vs Layer 2 baseline
  - 5 diverse cases printed for human eval

Usage:
    railway run python3 tests/cpe_ablation_layer2_plus_dna.py --creator iris_bertran
    railway run python3 tests/cpe_ablation_layer2_plus_dna.py --creator iris_bertran --evaluate-only

Output:
    tests/cpe_data/{creator}/sweep/layer2_plus_system08.json
"""

import argparse
import asyncio
import json
import logging
import math
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DEEPINFRA_TIMEOUT", "30")
os.environ.setdefault("DEEPINFRA_CB_THRESHOLD", "999")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_l2_dna")
logger.setLevel(logging.INFO)

DEFAULT_MODEL    = "Qwen/Qwen3-14B"
RATE_LIMIT_DELAY = 1.2

SENSITIVE_CONFIDENCE  = 0.70
SENSITIVE_ESCALATION  = 0.85
POOL_CONFIDENCE       = 0.80
POOL_MAX_MSG_LEN      = 80
INPUT_MAX_LEN         = 3000


# =============================================================================
# REUSE from layer2 script
# =============================================================================

from tests.cpe_ablation_layer2_full_detection import (
    load_system_prompt,
    load_pool_variator,
    load_calibration,
    run_input_guards,
    build_augmented_prompt,
    compute_l1,
    compute_l2,
    compute_l3_quick,
    wilcoxon_signed_rank,
    cliffs_delta,
    cliffs_magnitude,
    extract_per_case_from_results,
    _extract_per_case_from_files,
    _text_metrics,
    _count_sentences,
    _chrf,
    _bleu4,
    _rouge_l,
    _meteor,
    _repetition_rate,
    _is_text_ground_truth,
    _get_conversation_context,
)


# =============================================================================
# DNA LOADING — System #8
# =============================================================================

def load_dna_for_lead(creator_id: str, sender_id: str) -> Optional[str]:
    """Load RelationshipDNA + lead profile merged into unified block.

    Uses the #7→#8 merged path: format_unified_lead_context() combines
    DNA (relationship type, vocabulary, trust, topics) with lead profile
    (name, language, interests, products, CRM data) into one prompt block.

    Returns unified context string, or None if no DNA exists.
    """
    try:
        from services.relationship_dna_repository import get_relationship_dna
        from services.dm_agent_context_integration import (
            _format_dna_for_prompt,
            format_unified_lead_context,
        )
        dna = get_relationship_dna(creator_id, sender_id)
        if not dna:
            return None
        dna_block = _format_dna_for_prompt(dna)

        # Load lead profile from DB (merged System #7 data)
        lead_profile = _load_lead_profile(creator_id, sender_id)
        if lead_profile:
            return format_unified_lead_context(dna_block, lead_profile)
        return dna_block
    except Exception as e:
        logger.debug("DNA load failed for %s/%s: %s", creator_id, sender_id, e)
    return None


def _load_lead_profile(creator_id: str, sender_id: str) -> Optional[Dict]:
    """Load lead profile data from DB for unified context merging.

    Maps actual leads table columns (full_name, status, score, purchase_intent,
    tags, deal_value, relationship_type, notes) to the format expected by
    format_unified_lead_context().
    """
    try:
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            row = session.execute(
                text("""
                    SELECT l.username, l.full_name, l.status, l.score,
                           l.purchase_intent, l.tags, l.deal_value,
                           l.relationship_type, l.notes
                    FROM leads l
                    JOIN creators c ON l.creator_id = c.id
                    WHERE c.name = :cname
                      AND (l.platform_user_id = :sid OR l.username = :sid)
                    LIMIT 1
                """),
                {"cname": creator_id, "sid": sender_id},
            ).fetchone()
            if not row:
                return None
            tags = row[5] or []
            return {
                "name": row[1] or row[0] or "",
                "language": "es",
                "stage": row[2] or "",          # status as stage
                "interests": [],
                "products": [],
                "objections": [],
                "purchase_score": round(row[4], 2) if row[4] and row[4] > 0 else 0,
                "is_customer": row[2] in ("cliente", "customer"),
                "crm_status": row[7] or "",     # relationship_type
                "is_vip": "vip" in [t.lower() for t in tags],
                "is_price_sensitive": "price_sensitive" in [t.lower() for t in tags],
                "deal_value": row[6] or 0,
                "crm_notes": row[8] or "",      # notes
                "summary": "",
            }
        finally:
            session.close()
    except Exception as e:
        logger.debug("Lead profile load failed for %s/%s: %s", creator_id, sender_id, e)
        return None


def load_dna_context_prompt(creator_id: str, sender_id: str) -> str:
    """Load full context prompt (CreatorDMStyle + WritingPatterns + DNA + PostContext)."""
    try:
        from services.dm_agent_context_integration import build_context_prompt
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(
                    asyncio.run, build_context_prompt(creator_id, sender_id)
                ).result()
        return asyncio.run(build_context_prompt(creator_id, sender_id))
    except Exception as e:
        logger.debug("Context prompt failed for %s/%s: %s", creator_id, sender_id, e)
        return ""


def _get_platform_user_id(lead_id: str) -> Optional[str]:
    """Resolve lead UUID to platform_user_id."""
    try:
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            row = session.execute(
                text("SELECT platform_user_id FROM leads WHERE id = :lid LIMIT 1"),
                {"lid": lead_id},
            ).fetchone()
            return row[0] if row and row[0] else None
        finally:
            session.close()
    except Exception:
        return None


def _resolve_sender_id(tc: Dict, creator_id: str) -> str:
    """Get the best sender_id for DNA lookup.

    DNA stores follower_id as platform_user_id (e.g. 'wa_34682882838' or '1426741728859479').
    Test cases store lead_username which may be a platform_user_id (WA) or a display username (IG).
    For IG usernames, we need to resolve to the numeric platform_user_id via the leads table.
    """
    # 1. If lead_id UUID is available, resolve directly
    lead_id = tc.get("lead_id", "")
    if lead_id:
        pid = _get_platform_user_id(lead_id)
        if pid:
            return pid

    username = tc.get("lead_username", "")
    if not username:
        return tc.get("id", "unknown")

    # 2. WA leads: lead_username IS the platform_user_id
    if username.startswith("wa_"):
        return username

    # 3. IG leads: resolve username → platform_user_id via DB
    try:
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            row = session.execute(
                text("""
                    SELECT l.platform_user_id FROM leads l
                    JOIN creators c ON l.creator_id = c.id
                    WHERE c.name = :cname
                      AND (l.username = :uname OR l.platform_user_id = :uname)
                    LIMIT 1
                """),
                {"cname": creator_id, "uname": username},
            ).fetchone()
            if row and row[0]:
                return row[0]
        finally:
            session.close()
    except Exception as e:
        logger.debug("DB resolve failed for %s: %s", username, e)

    # 4. Fallback: return username as-is
    return username


# =============================================================================
# L3 — BERTScore
# =============================================================================

def compute_l3_bertscore(results: List[Dict]) -> dict:
    """L3: BERTScore coherence + semantic similarity."""
    bots = [r["bot_response"] for r in results]
    gts = [r["ground_truth"] for r in results]

    try:
        from bert_score import score as bert_score
        safe_bots = [b if b else "." for b in bots]
        safe_gts = [g if g else "." for g in gts]
        _, _, F1 = bert_score(
            cands=safe_bots, refs=safe_gts,
            model_type="xlm-roberta-large", lang="es",
            batch_size=16, verbose=False, rescale_with_baseline=True,
        )
        f1_scores = [F1[i].item() for i in range(len(bots))]
        for i in range(len(bots)):
            if not bots[i] or not gts[i]:
                f1_scores[i] = 0.0
        return {
            "coherence_bert_f1": round(statistics.mean(f1_scores), 4),
            "_bert_f1_scores": f1_scores,
        }
    except ImportError:
        logger.warning("bert-score not installed")
        return {"coherence_bert_f1": 0.0, "_bert_f1_scores": [0.0] * len(bots)}


def compute_semsim(results: List[Dict]) -> float:
    """Semantic similarity via sentence-transformers."""
    try:
        from sentence_transformers import SentenceTransformer, util
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        bots = [r["bot_response"] or "." for r in results]
        gts = [r["ground_truth"] or "." for r in results]
        emb_b = model.encode(bots, convert_to_tensor=True)
        emb_g = model.encode(gts, convert_to_tensor=True)
        sims = [util.cos_sim(emb_b[i], emb_g[i]).item() for i in range(len(bots))]
        return round(statistics.mean(sims), 4)
    except ImportError:
        return 0.0


# =============================================================================
# GENERATION — Layer 2 + DNA
# =============================================================================

async def generate_layer2_dna_run(
    test_cases: List[Dict],
    base_prompt: str,
    variator,
    calibration: dict,
    creator_id: str,
    model: str,
    run_idx: int,
    delay: float = RATE_LIMIT_DELAY,
) -> Tuple[List[Dict], Dict[str, int]]:
    """One run: Layer 2 + DNA context injected into system prompt."""
    from core.sensitive_detector import detect_sensitive_content, get_crisis_resources
    from core.frustration_detector import get_frustration_detector
    from core.context_detector import detect_all as detect_context
    from services.length_controller import classify_lead_context
    from core.providers.deepinfra_provider import call_deepinfra

    frustration_detector = get_frustration_detector()
    counts = defaultdict(int)

    logger.info("[Run %d] layer2+dna | model=%s | cases=%d", run_idx, model, len(test_cases))

    results = []
    for i, tc in enumerate(test_cases, 1):
        original_message = tc["test_input"]
        t0 = time.monotonic()

        bot_response = ""
        source       = "llm"
        intercept_by = None
        frust_level  = 0
        ctx_signals  = None
        guard_flags  = {}
        pool_cat     = None
        pool_conf    = 0.0
        tokens_in    = 0
        tokens_out   = 0
        augmented    = False
        dna_injected = False

        # ── GUARD #4: Input Guards ─────────────────────────────────────────
        message, guard_flags = run_input_guards(original_message)

        if guard_flags["is_empty"]:
            counts["empty_skipped"] += 1
            source = "empty_skip"
            intercept_by = "input_guard_empty"
            bot_response = ""
        else:
            if guard_flags["is_truncated"]:
                counts["truncated"] += 1
            if guard_flags["injection_flagged"]:
                counts["injection_flagged"] += 1
            if guard_flags["is_media"]:
                counts["media_flagged"] += 1

            # ── SYSTEM #1: Sensitive Detection ─────────────────────────────
            try:
                sensitive = detect_sensitive_content(message)
                if sensitive and sensitive.confidence >= SENSITIVE_CONFIDENCE:
                    counts["sensitive_flagged"] += 1
                    if sensitive.confidence >= SENSITIVE_ESCALATION:
                        bot_response = get_crisis_resources(language="es")
                        source = "crisis"
                        intercept_by = f"sensitive_{sensitive.type.value}"
                        counts["sensitive_escalated"] += 1
            except Exception as e:
                logger.debug("Sensitive detection error: %s", e)

            # ── SYSTEM #5: Pool Matching ───────────────────────────────────
            if not bot_response and len(message.strip()) <= POOL_MAX_MSG_LEN:
                try:
                    pool_context = classify_lead_context(message)
                    match = variator.try_pool_response(
                        lead_message=message,
                        min_confidence=0.70,
                        calibration=calibration,
                        turn_index=i,
                        conv_id=f"l2dna_run{run_idx}_{i}",
                        context=pool_context,
                        creator_id=creator_id,
                    )
                    if match.matched and match.confidence >= POOL_CONFIDENCE:
                        bot_response = match.response.strip()
                        source = "pool"
                        intercept_by = f"pool_{match.category}"
                        pool_cat = match.category
                        pool_conf = round(match.confidence, 3)
                        counts["pool_matched"] += 1
                except Exception as e:
                    logger.debug("Pool matching error: %s", e)

            # ── SYSTEM #2: Frustration Detection ───────────────────────────
            try:
                frust_signals, frust_score = frustration_detector.analyze_message(
                    message, f"l2dna_run{run_idx}_{i}"
                )
                frust_level = frust_signals.level
                if frust_level >= 2:
                    counts["frustration_moderate_plus"] += 1
                elif frust_level == 1:
                    counts["frustration_soft"] += 1
            except Exception as e:
                logger.debug("Frustration detection error: %s", e)

            # ── SYSTEM #3: Context Signals ─────────────────────────────────
            try:
                ctx_signals = detect_context(message)
                if getattr(ctx_signals, "is_b2b", False):
                    counts["b2b_detected"] += 1
                if getattr(ctx_signals, "is_correction", False):
                    counts["correction_detected"] += 1
                obj = getattr(ctx_signals, "objection_type", "")
                if obj:
                    counts[f"objection_{obj}"] += 1
                name = getattr(ctx_signals, "user_name", "")
                if name:
                    counts["name_extracted"] += 1
            except Exception as e:
                logger.debug("Context detection error: %s", e)

            # ── LLM GENERATION (if not intercepted) ────────────────────────
            if not bot_response:
                counts["llm_calls"] += 1

                # Build augmented prompt from detection signals
                prompt = build_augmented_prompt(base_prompt, frust_level, ctx_signals)
                augmented = (prompt != base_prompt)
                if augmented:
                    counts["prompt_augmented"] += 1

                # ── SYSTEM #8: DNA Context ─────────────────────────────────
                # Resolve sender_id and load DNA for this lead
                sender_id = _resolve_sender_id(tc, creator_id)
                dna_ctx = await asyncio.to_thread(
                    load_dna_for_lead, creator_id, sender_id
                )
                if dna_ctx:
                    prompt = prompt + "\n\n" + dna_ctx
                    dna_injected = True
                    counts["dna_injected"] += 1

                # Build conversation history for multi-turn
                messages = [{"role": "system", "content": prompt}]
                turns = tc.get("turns", [])
                for turn in turns:
                    role = turn.get("role", "")
                    content = turn.get("content", "")
                    if not content:
                        continue
                    if role in ("iris", "assistant"):
                        messages.append({"role": "assistant", "content": content})
                    elif role in ("lead", "user"):
                        messages.append({"role": "user", "content": content})
                # Remove last user msg if it duplicates test_input
                if messages and messages[-1].get("content") == original_message:
                    messages = messages[:-1]
                messages.append({"role": "user", "content": message})

                resp = None
                try:
                    resp = await call_deepinfra(
                        messages, max_tokens=150, temperature=0.7, model=model,
                    )
                except Exception as e:
                    logger.warning("[Run %d] LLM error case %d: %s", run_idx, i, e)

                bot_response = resp["content"].strip() if resp else ""
                tokens_in = resp.get("tokens_in", 0) if resp else 0
                tokens_out = resp.get("tokens_out", 0) if resp else 0

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        results.append({
            "id":               tc["id"],
            "test_input":       original_message,
            "ground_truth":     tc.get("ground_truth", ""),
            "bot_response":     bot_response,
            "category":         tc.get("category", ""),
            "language":         tc.get("language", ""),
            "elapsed_ms":       elapsed_ms,
            "tokens_in":        tokens_in,
            "tokens_out":       tokens_out,
            "run":              run_idx,
            "source":           source,
            "intercept_by":     intercept_by,
            "frustration_level": frust_level,
            "is_b2b":           getattr(ctx_signals, "is_b2b", False) if ctx_signals else False,
            "is_correction":    getattr(ctx_signals, "is_correction", False) if ctx_signals else False,
            "objection_type":   getattr(ctx_signals, "objection_type", "") if ctx_signals else "",
            "user_name":        getattr(ctx_signals, "user_name", "") if ctx_signals else "",
            "prompt_augmented": augmented,
            "dna_injected":     dna_injected,
            "pool_category":    pool_cat,
            "pool_conf":        pool_conf,
            "guard_flags":      guard_flags,
        })

        if i % 10 == 0 or not bot_response:
            tag = "DNA" if dna_injected else source.upper()[:5]
            print(f"  [{tag:5}] [{i:02d}/{len(test_cases)}] {tc['id']}: {bot_response[:55]!r}")

        if source == "llm":
            await asyncio.sleep(delay)

    n_ok = sum(1 for r in results if r["bot_response"])
    n_dna = counts["dna_injected"]
    ok_ms = [r["elapsed_ms"] for r in results if r["bot_response"] and r["elapsed_ms"] > 0]
    avg_ms = statistics.mean(ok_ms) if ok_ms else 0
    print(
        f"  Run {run_idx}: {n_ok}/{len(results)} OK | "
        f"llm={counts['llm_calls']} pool={counts['pool_matched']} "
        f"dna={n_dna} | avg {avg_ms:.0f}ms"
    )
    return results, dict(counts)


# =============================================================================
# STATISTICAL COMPARISON
# =============================================================================

def compare_vs_baseline(
    test_pc: Dict[str, List[float]],
    base_pc: Dict[str, List[float]],
    label: str,
) -> Dict[str, Dict]:
    """Paired Wilcoxon + Cliff's delta for each metric."""
    comparison = {}
    metrics = ["has_emoji", "has_excl", "q_rate", "char_len",
               "sentence_count", "chrf", "bleu4", "rouge_l", "meteor", "len_ratio"]
    for m in metrics:
        if m not in test_pc or m not in base_pc:
            continue
        x, y = test_pc[m], base_pc[m]
        n = min(len(x), len(y))
        if n < 3:
            continue
        x, y = x[:n], y[:n]
        w, p = wilcoxon_signed_rank(x, y)
        d = cliffs_delta(x, y)
        comparison[m] = {
            "w": w, "p": p,
            "cliff_d": d,
            "magnitude": cliffs_magnitude(d),
            "mean_test": round(statistics.mean(x), 4),
            "mean_base": round(statistics.mean(y), 4),
            "delta": round(statistics.mean(x) - statistics.mean(y), 4),
        }
    return comparison


# =============================================================================
# MAIN
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="CPE Ablation — Layer 2 + DNA Engine")
    parser.add_argument("--creator", default="iris_bertran")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--delay", type=float, default=RATE_LIMIT_DELAY)
    parser.add_argument("--evaluate-only", action="store_true")
    args = parser.parse_args()

    creator_id = args.creator
    n_runs = max(1, args.runs)
    model = args.model

    data_dir = Path(f"tests/cpe_data/{creator_id}")
    sweep_dir = data_dir / "sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 74)
    print("LAYER 2 + SYSTEM #8 (DNA ENGINE) ABLATION")
    print("=" * 74)

    base_prompt = load_system_prompt(creator_id)
    print(f"System prompt: {len(base_prompt)} chars")

    test_set_v2 = data_dir / "test_set_v2_stratified.json"
    test_set_v1 = data_dir / "test_set.json"
    test_set_path = test_set_v2 if test_set_v2.exists() else test_set_v1
    with open(test_set_path, encoding="utf-8") as f:
        test_set = json.load(f)
    conversations = test_set.get("conversations", [])
    version = test_set.get("metadata", {}).get("version", "v1")
    n_mt = sum(1 for c in conversations if c.get("is_multi_turn"))
    print(f"Test cases: {len(conversations)} (version={version}, multi-turn={n_mt})")

    bm_path = data_dir / "baseline_metrics.json"
    baseline_metrics = json.loads(bm_path.read_text()) if bm_path.exists() else {}
    print(f"Baseline metrics: {'loaded' if baseline_metrics else 'NOT FOUND'}")

    variator = load_pool_variator(creator_id)
    calibration = load_calibration(creator_id)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = sweep_dir / "layer2_plus_system08.json"

    # ── GENERATION ────────────────────────────────────────────────────────────
    run_files: List[Path] = []
    all_results: List[List[Dict]] = []
    all_counts: List[dict] = []

    if args.evaluate_only:
        # Load existing run files
        for run_idx in range(1, n_runs + 1):
            pattern = f"layer2_plus_dna_run{run_idx}_*.json"
            files = sorted(sweep_dir.glob(pattern))
            if files:
                run_files.append(files[-1])  # latest
        if not run_files:
            print("ERROR: --evaluate-only but no layer2_plus_dna_run*.json found.")
            sys.exit(1)
        for rf in run_files:
            d = json.loads(rf.read_text())
            all_results.append(d["results"])
            all_counts.append(d.get("intercept_counts", {}))
        print(f"Evaluate-only: {len(run_files)} files")
    else:
        api_key = os.getenv("DEEPINFRA_API_KEY")
        if not api_key:
            print("ERROR: DEEPINFRA_API_KEY not set.")
            sys.exit(1)

        for run_idx in range(1, n_runs + 1):
            print(f"\n--- RUN {run_idx}/{n_runs} ---")
            try:
                import core.providers.deepinfra_provider as _di
                _di._deepinfra_consecutive_failures = 0
                _di._deepinfra_circuit_open_until = 0.0
            except Exception:
                pass

            run_results, counts = await generate_layer2_dna_run(
                conversations, base_prompt, variator, calibration,
                creator_id, model, run_idx, args.delay,
            )
            all_results.append(run_results)
            all_counts.append(counts)

            rf = sweep_dir / f"layer2_plus_dna_run{run_idx}_{ts}.json"
            payload = {
                "ablation":        "layer2_plus_dna",
                "creator":         creator_id,
                "model":           model,
                "system_prompt":   base_prompt,
                "systems_active":  [
                    "input_guards", "sensitive_detection", "pool_matching",
                    "frustration_detection", "context_signals", "compressed_doc_d",
                    "relationship_dna",
                ],
                "run":             run_idx,
                "n_cases":         len(run_results),
                "timestamp":       datetime.now(timezone.utc).isoformat(),
                "intercept_counts": counts,
                "results":         run_results,
            }
            rf.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            run_files.append(rf)
            print(f"  Saved: {rf.name}")

    # ── EVALUATION ────────────────────────────────────────────────────────────
    print("\n" + "=" * 74)
    print("EVALUATION")
    print("=" * 74)

    # Compute L1 per run
    l1_per_run = []
    for run_results in all_results:
        responses = [r["bot_response"] for r in run_results]
        l1 = compute_l1(responses, baseline_metrics)
        l1_per_run.append(l1)

    # Compute L2 per run
    l2_per_run = []
    for run_results in all_results:
        l2 = compute_l2(run_results)
        l2_per_run.append(l2)

    # Compute L3 per run (quick: rep + hallucination)
    l3q_per_run = []
    for run_results in all_results:
        l3q = compute_l3_quick(run_results)
        l3q_per_run.append(l3q)

    # Compute L3 BERTScore (use all runs concatenated then average)
    print("Computing BERTScore...")
    l3_bert_per_run = []
    for run_results in all_results:
        l3b = compute_l3_bertscore(run_results)
        l3_bert_per_run.append(l3b)

    # Compute semsim
    print("Computing semantic similarity...")
    semsim_per_run = [compute_semsim(rr) for rr in all_results]

    # Aggregate L1
    l1_agg = {}
    if l1_per_run and l1_per_run[0]:
        for metric_name in l1_per_run[0].get("metrics", {}):
            vals = [lr["metrics"][metric_name]["bot"] for lr in l1_per_run if "metrics" in lr]
            if vals:
                l1_agg[metric_name] = {
                    "mean": round(statistics.mean(vals), 4),
                    "std": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0,
                    "runs": vals,
                }

    l1_score_runs = [lr.get("passed", 0) for lr in l1_per_run if lr]
    l1_score_mean = round(statistics.mean(l1_score_runs), 1) if l1_score_runs else 0

    # Aggregate L2
    l2_agg = {}
    for metric_name in ["chrf", "bleu4", "rouge_l", "meteor", "len_ratio"]:
        vals = [lr[metric_name] for lr in l2_per_run if metric_name in lr]
        if vals:
            l2_agg[metric_name] = {
                "mean": round(statistics.mean(vals), 4),
                "std": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0,
                "runs": vals,
            }

    # Aggregate L3
    bert_vals = [lr["coherence_bert_f1"] for lr in l3_bert_per_run]
    rep_vals = [lr["rep_rate_pct"] for lr in l3q_per_run]
    hallu_vals = [lr["hallu_rate_pct"] for lr in l3q_per_run]

    l3_agg = {
        "coherence_bert_f1": {
            "mean": round(statistics.mean(bert_vals), 4),
            "std": round(statistics.stdev(bert_vals), 4) if len(bert_vals) > 1 else 0,
            "runs": bert_vals,
        },
        "repetition_rate_pct": {
            "mean": round(statistics.mean(rep_vals), 2),
            "std": round(statistics.stdev(rep_vals), 2) if len(rep_vals) > 1 else 0,
            "runs": rep_vals,
        },
        "hallucination_rate_pct": {
            "mean": round(statistics.mean(hallu_vals), 2),
            "std": round(statistics.stdev(hallu_vals), 2) if len(hallu_vals) > 1 else 0,
            "runs": hallu_vals,
        },
        "semsim": {
            "mean": round(statistics.mean(semsim_per_run), 4),
            "std": round(statistics.stdev(semsim_per_run), 4) if len(semsim_per_run) > 1 else 0,
            "runs": semsim_per_run,
        },
    }

    # ── INTERCEPT COUNTS ──────────────────────────────────────────────────────
    ic_avg = {}
    if all_counts:
        all_keys = set()
        for c in all_counts:
            all_keys.update(c.keys())
        for k in sorted(all_keys):
            vals = [c.get(k, 0) for c in all_counts]
            ic_avg[k] = round(statistics.mean(vals), 1)

    # ── STATISTICAL COMPARISON VS LAYER 2 ─────────────────────────────────────
    print("\nStatistical comparison vs Layer 2 baseline...")

    # Extract per-case scores from our runs
    test_pc = extract_per_case_from_results(all_results)

    # Load Layer 2 baseline per-case scores
    l2_baseline_files = sorted(sweep_dir.glob("layer2_full_detection_run*_210437.json"))
    if not l2_baseline_files:
        l2_baseline_files = sorted(sweep_dir.glob("layer2_full_detection_run*.json"))
    # Pick the latest complete set of 3 runs
    by_ts = defaultdict(list)
    for f in sorted(sweep_dir.glob("layer2_full_detection_run*.json")):
        parts = f.stem.split("_")
        ts_part = "_".join(parts[-2:])
        by_ts[ts_part].append(f)
    complete_sets = sorted(
        [(ts_key, fs) for ts_key, fs in by_ts.items() if len(fs) == 3],
        key=lambda t: t[0], reverse=True,
    )
    base_pc = {}
    if complete_sets:
        ts_key, base_files = complete_sets[0]
        logger.info("Layer 2 baseline: %s (%d files)", ts_key, len(base_files))
        base_pc = _extract_per_case_from_files(base_files)

    stat_comparison = {}
    if base_pc:
        stat_comparison = compare_vs_baseline(test_pc, base_pc, "layer2")

    # ── SAMPLE CASES (text-only GT) ──────────────────────────────────────────
    # Pick 5 diverse cases (different categories), excluding media ground_truth
    sample_cases = []
    seen_cats = set()
    r1_all = all_results[0] if all_results else []
    # Prefer cases where DNA was injected
    for r in r1_all:
        cat = r.get("category", "")
        if (r.get("dna_injected") and cat not in seen_cats and r.get("bot_response")
                and _is_text_ground_truth(r.get("ground_truth", ""))):
            sample_cases.append({
                "id": r["id"],
                "category": cat,
                "test_input": r["test_input"],
                "ground_truth": r["ground_truth"],
                "bot_response": r["bot_response"],
                "dna_injected": r["dna_injected"],
                "source": r["source"],
                "conversation_context": _get_conversation_context(r["id"], conversations),
            })
            seen_cats.add(cat)
        if len(sample_cases) >= 5:
            break
    # Fill remaining with non-DNA cases
    if len(sample_cases) < 5:
        for r in r1_all:
            cat = r.get("category", "")
            if (cat not in seen_cats and r.get("bot_response")
                    and _is_text_ground_truth(r.get("ground_truth", ""))):
                sample_cases.append({
                    "id": r["id"],
                    "category": cat,
                    "test_input": r["test_input"],
                    "ground_truth": r["ground_truth"],
                    "bot_response": r["bot_response"],
                    "dna_injected": r.get("dna_injected", False),
                    "source": r["source"],
                    "conversation_context": _get_conversation_context(r["id"], conversations),
                })
                seen_cats.add(cat)
            if len(sample_cases) >= 5:
                break

    # ── BUILD REPORT ──────────────────────────────────────────────────────────
    report = {
        "ablation": "layer2_plus_system08_dna",
        "version": "v1",
        "creator": creator_id,
        "model": model,
        "system_prompt": base_prompt,
        "system_prompt_chars": len(base_prompt),
        "systems_active": [
            "input_guards", "sensitive_detection", "pool_matching",
            "frustration_detection", "context_signals", "compressed_doc_d",
            "relationship_dna",
        ],
        "n_runs": n_runs,
        "n_cases": len(conversations),
        "computed": datetime.now(timezone.utc).isoformat(),
        "intercept_counts_per_run": all_counts,
        "intercept_counts_avg": ic_avg,
        "l1": {
            "score_per_run": [lr.get("score", "?/9") for lr in l1_per_run],
            "agg_metrics": l1_agg,
            "per_run": [lr.get("metrics", {}) for lr in l1_per_run],
        },
        "l2": {
            "agg": l2_agg,
            "per_run": [{k: v for k, v in lr.items() if not k.startswith("_")} for lr in l2_per_run],
        },
        "l3": {"agg": l3_agg},
        "statistical_comparison_vs_layer2": stat_comparison,
        "sample_cases": sample_cases,
    }

    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nSaved: {output_path}")

    # ── PRINT SUMMARY ─────────────────────────────────────────────────────────
    print("\n" + "=" * 74)
    print(f"  LAYER 2 + SYSTEM #8 (DNA) — @{creator_id} — {n_runs} runs × {len(conversations)} cases")
    print("=" * 74)

    print(f"\n  L1 Score: {l1_score_mean}/9 avg ({l1_score_runs})")
    print(f"\n  L1 Metrics (mean ± std):")
    for m, v in l1_agg.items():
        print(f"    {m:<20} {v['mean']:>8.2f} ± {v['std']:.2f}")

    print(f"\n  L2 Metrics:")
    for m, v in l2_agg.items():
        print(f"    {m:<20} {v['mean']:>8.4f} ± {v['std']:.4f}")

    print(f"\n  L3 Metrics:")
    for m, v in l3_agg.items():
        print(f"    {m:<24} {v['mean']:>8.4f} ± {v['std']:.4f}")

    print(f"\n  Intercept counts (avg):")
    for k, v in ic_avg.items():
        print(f"    {k:<30} {v:.1f}")

    if stat_comparison:
        print(f"\n  {'Metric':<20} {'Δ':>8} {'p':>8} {'Cliff d':>8} {'Magnitude':<12}")
        print(f"  {'-'*18:<20} {'-'*8:>8} {'-'*8:>8} {'-'*8:>8} {'-'*12:<12}")
        for m, v in stat_comparison.items():
            sig = "*" if v["p"] < 0.05 else " "
            print(
                f"  {m:<20} {v['delta']:>+8.4f} {v['p']:>8.4f}{sig} "
                f"{v['cliff_d']:>+8.4f} {v['magnitude']:<12}"
            )

    print(f"\n  5 Sample Cases for Human Eval:")
    print(f"  {'-'*70}")
    for sc in sample_cases:
        dna_tag = " [DNA]" if sc.get("dna_injected") else ""
        print(f"  [{sc['category']}]{dna_tag} {sc['id']}")
        ctx = sc.get("conversation_context", [])
        if ctx:
            print(f"    Context (last {len(ctx)} turns):")
            for t in ctx:
                role_tag = "👤" if t["role"] == "user" else "🤖"
                print(f"      {role_tag} {t['content'][:120]}")
        print(f"    Lead:  {sc['test_input'][:70]}")
        print(f"    GT:    {sc['ground_truth'][:70]}")
        print(f"    Bot:   {sc['bot_response'][:70]}")
        print()

    print("=" * 74)


if __name__ == "__main__":
    asyncio.run(main())
