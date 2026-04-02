"""
CPE Ablation — Layer 2 + System #9 (Memory Engine).

Adds ONLY #9 (long-term memory: LLM fact extraction, summaries, COMEDY compression,
Ebbinghaus decay, pgvector semantic recall) on top of the full Layer 2 pipeline.

Systems active (cumulative):
  Layer 2 base:
    #4 Input Guards      — empty gate, injection flag, media flag, length truncation
    #1 Sensitive         — crisis/threat/spam → crisis response, SKIP LLM
    #5 Pool Matching     — short social msg → pool response, SKIP LLM
    #2 Frustration       — annotate level 0-3 in metadata
    #3 Context Signals   — annotate language, B2B, correction, objection, name

  NEW — System #9 Memory Engine:
    - recall()           — semantic search of lead_memories for relevant facts
    - Injected into system prompt as "MEMORIA DEL LEAD" section
    - Uses pgvector cosine similarity on extracted facts
    - COMEDY compression, Ebbinghaus decay (if enabled)

LLM generation (if not intercepted):
  - Base: DeepInfra Qwen3-14B + Doc D v3 system prompt
  - + Memory Engine recall context (if available)
  - + Frustration/B2B/correction/objection notes

Methodology:
  - PersonaGym (EMNLP 2025) + AbGen (ACL 2025)
  - 3 runs × 50 cases = 150 observations
  - L1 (9) + L2 (6) + L3 (BERTScore + rep + hallucination)
  - Wilcoxon + Cliff's delta vs Layer 2 baseline

Usage:
    railway run python3 tests/cpe_ablation_layer2_plus_system09.py --creator iris_bertran
    railway run python3 tests/cpe_ablation_layer2_plus_system09.py --creator iris_bertran --evaluate-only

Output:
    tests/cpe_data/{creator}/sweep/layer2_plus_system09_run{N}_{ts}.json
    tests/cpe_data/{creator}/sweep/layer2_plus_system09.json
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

# Force Memory Engine ON for this ablation
os.environ["ENABLE_MEMORY_ENGINE"] = "true"
os.environ.setdefault("DEEPINFRA_TIMEOUT", "30")
os.environ.setdefault("DEEPINFRA_CB_THRESHOLD", "999")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_layer2_plus_sys09")
logger.setLevel(logging.INFO)

DEFAULT_MODEL    = "Qwen/Qwen3-14B"
RATE_LIMIT_DELAY = 1.2

# Thresholds — mirror production values
SENSITIVE_CONFIDENCE  = 0.70
SENSITIVE_ESCALATION  = 0.85
POOL_CONFIDENCE       = 0.80
POOL_MAX_MSG_LEN      = 80
INPUT_MAX_LEN         = 3000


# =============================================================================
# IMPORTS FROM LAYER 2 (reuse all metrics, guards, etc.)
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
    _text_metrics,
    _count_sentences,
    _chrf,
    _bleu4,
    _rouge_l,
    _meteor,
    _repetition_rate,
    _norm_sf,
    _is_text_ground_truth,
    _get_conversation_context,
)


# =============================================================================
# SYSTEM #9: Memory Engine recall
# =============================================================================

async def _resolve_lead_uuid_for_ablation(creator_id: str, lead_username: str) -> Optional[str]:
    """Resolve a test-case username/phone to a real lead UUID in the DB.
    Returns None if the lead doesn't exist."""
    def _sync():
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            # Try exact match on platform_user_id with common prefixes
            candidates = [lead_username]
            if not lead_username.startswith(("ig_", "wa_", "tg_")):
                candidates.extend([f"ig_{lead_username}", f"wa_{lead_username}"])
            for pid in candidates:
                row = session.execute(
                    text(
                        "SELECT l.id FROM leads l "
                        "JOIN creators c ON l.creator_id = c.id "
                        "WHERE c.name = :cname AND l.platform_user_id = :pid LIMIT 1"
                    ),
                    {"cname": creator_id, "pid": pid},
                ).fetchone()
                if row:
                    return str(row[0])
            # Try username match
            row = session.execute(
                text(
                    "SELECT l.id FROM leads l "
                    "JOIN creators c ON l.creator_id = c.id "
                    "WHERE c.name = :cname AND l.username = :uname LIMIT 1"
                ),
                {"cname": creator_id, "uname": lead_username},
            ).fetchone()
            if row:
                return str(row[0])
            return None
        finally:
            session.close()
    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.debug("[SYS09] Lead resolution failed for %s: %s", lead_username[:20], e)
        return None


# Cache resolved lead UUIDs to avoid repeated DB lookups
_lead_uuid_cache: Dict[str, Optional[str]] = {}


async def recall_memory_for_lead(
    creator_id: str, lead_username: str, message: str,
    conversation_history: List[Dict] = None,
) -> Tuple[str, dict]:
    """
    Call Memory Engine recall() for a lead. Returns (memory_context_str, metadata).

    Pre-resolves lead_username to a valid DB UUID before calling Memory Engine.
    Skips gracefully if the lead doesn't exist in the DB.
    """
    from services.memory_engine import get_memory_engine

    meta = {"memory_recalled": False, "memory_chars": 0, "facts_added": 0}

    # Step 0: Resolve lead_username → UUID (cached)
    if lead_username not in _lead_uuid_cache:
        _lead_uuid_cache[lead_username] = await _resolve_lead_uuid_for_ablation(
            creator_id, lead_username
        )
    lead_uuid = _lead_uuid_cache[lead_username]
    if not lead_uuid:
        return "", meta  # Lead doesn't exist in DB — no memories possible

    engine = get_memory_engine()

    # Skip add() — DB is read-only via railway run, and lead_memories
    # already has 7300+ facts from production. Just recall existing data.

    # Recall relevant memories
    try:
        memory_context = await engine.recall(creator_id, lead_uuid, message)
        if memory_context:
            meta["memory_recalled"] = True
            meta["memory_chars"] = len(memory_context)
        return memory_context or "", meta
    except Exception as e:
        logger.debug("[SYS09] recall() failed for %s: %s", lead_username[:20], e)
        return "", meta


def inject_memory_into_prompt(base_prompt: str, memory_context: str) -> str:
    """Append memory context to the system prompt, before any detection notes."""
    if not memory_context:
        return base_prompt
    return base_prompt + "\n\n" + memory_context


# =============================================================================
# GENERATION — Layer 2 + System #9
# =============================================================================

async def generate_run(
    test_cases: List[Dict],
    base_prompt: str,
    variator,
    calibration: dict,
    creator_id: str,
    model: str,
    run_idx: int,
    delay: float = RATE_LIMIT_DELAY,
) -> Tuple[List[Dict], Dict[str, int]]:
    """
    One run through Layer 2 + System #9 Memory Engine.
    Identical to layer2 generation but adds memory recall before LLM call.
    """
    from core.sensitive_detector import detect_sensitive_content, get_crisis_resources
    from core.frustration_detector import get_frustration_detector
    from core.context_detector import detect_all as detect_context
    from services.length_controller import classify_lead_context
    from core.providers.deepinfra_provider import call_deepinfra

    frustration_detector = get_frustration_detector()
    counts = defaultdict(int)

    logger.info("[Run %d] layer2+sys09 | model=%s | cases=%d", run_idx, model, len(test_cases))

    results = []
    for i, tc in enumerate(test_cases, 1):
        original_message = tc["test_input"]
        t0 = time.monotonic()

        bot_response = ""
        source       = "llm"
        intercept_by = None
        frust_level  = 0
        ctx_signals  = None
        guard_flags: dict = {}
        pool_cat     = None
        pool_conf    = 0.0
        tokens_in    = 0
        tokens_out   = 0
        augmented    = False
        memory_ctx   = ""
        memory_meta: dict = {}

        # ── GUARD #4: Input Guards ─────────────────────────────────────────
        message, guard_flags = run_input_guards(original_message)

        if guard_flags["is_empty"]:
            counts["empty_skipped"] += 1
            source      = "empty_skip"
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
                        source        = "crisis"
                        intercept_by  = f"sensitive_{sensitive.type.value}"
                        counts["sensitive_escalated"] += 1
            except Exception as e:
                logger.debug("Sensitive detection error: %s", e)

            # ── SYSTEM #5: Pool Matching ──────────────────────────────────
            if not bot_response and len(message.strip()) <= POOL_MAX_MSG_LEN:
                try:
                    pool_context = classify_lead_context(message)
                    match = variator.try_pool_response(
                        lead_message  = message,
                        min_confidence= 0.70,
                        calibration   = calibration,
                        turn_index    = i,
                        conv_id       = f"l2s09_run{run_idx}_{i}",
                        context       = pool_context,
                        creator_id    = creator_id,
                    )
                    if match.matched and match.confidence >= POOL_CONFIDENCE:
                        bot_response = match.response.strip()
                        source        = "pool"
                        intercept_by  = f"pool_{match.category}"
                        pool_cat      = match.category
                        pool_conf     = round(match.confidence, 3)
                        counts["pool_matched"] += 1
                except Exception as e:
                    logger.debug("Pool matching error: %s", e)

            # ── SYSTEM #2: Frustration Detection ──────────────────────────
            try:
                frust_signals, frust_score = frustration_detector.analyze_message(
                    message, f"l2s09_run{run_idx}_{i}"
                )
                frust_level = frust_signals.level
                if frust_level >= 2:
                    counts["frustration_moderate_plus"] += 1
                elif frust_level == 1:
                    counts["frustration_soft"] += 1
            except Exception as e:
                logger.debug("Frustration detection error: %s", e)

            # ── SYSTEM #3: Context Signals ────────────────────────────────
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

            # ── SYSTEM #9: Memory Engine recall (NEW) ─────────────────────
            if not bot_response:
                try:
                    lead_id = tc.get("lead_username", f"ablation_lead_{i}")
                    conv_history = tc.get("turns", [])
                    memory_ctx, memory_meta = await recall_memory_for_lead(
                        creator_id, lead_id, message, conv_history,
                    )
                    if memory_ctx:
                        counts["memory_recalled"] += 1
                        counts["memory_total_chars"] = counts.get("memory_total_chars", 0) + len(memory_ctx)
                    if memory_meta.get("facts_added", 0) > 0:
                        counts["facts_extracted"] = counts.get("facts_extracted", 0) + memory_meta["facts_added"]
                except Exception as e:
                    logger.debug("[SYS09] Memory recall error case %d: %s", i, e)

            # ── LLM GENERATION (if not intercepted) ───────────────────────
            if not bot_response:
                counts["llm_calls"] += 1

                # Build prompt: base + memory + detection augmentation
                prompt_with_memory = inject_memory_into_prompt(base_prompt, memory_ctx)
                prompt = build_augmented_prompt(prompt_with_memory, frust_level, ctx_signals)
                augmented = (prompt != base_prompt)
                if augmented:
                    counts["prompt_augmented"] += 1

                messages = [
                    {"role": "system", "content": prompt},
                    {"role": "user",   "content": message},
                ]
                resp = None
                try:
                    resp = await call_deepinfra(
                        messages, max_tokens=150, temperature=0.7, model=model,
                    )
                except Exception as e:
                    logger.warning("[Run %d] LLM error case %d: %s", run_idx, i, e)

                bot_response = resp["content"].strip() if resp else ""
                tokens_in    = resp.get("tokens_in",  0) if resp else 0
                tokens_out   = resp.get("tokens_out", 0) if resp else 0

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        results.append({
            "id":            tc["id"],
            "test_input":    original_message,
            "ground_truth":  tc.get("ground_truth", ""),
            "bot_response":  bot_response,
            "category":      tc.get("category", ""),
            "language":      tc.get("language", ""),
            "elapsed_ms":    elapsed_ms,
            "tokens_in":     tokens_in,
            "tokens_out":    tokens_out,
            "run":           run_idx,
            # Layer 2 detection metadata
            "source":           source,
            "intercept_by":     intercept_by,
            "frustration_level": frust_level,
            "is_b2b":           getattr(ctx_signals, "is_b2b",         False) if ctx_signals else False,
            "is_correction":    getattr(ctx_signals, "is_correction",   False) if ctx_signals else False,
            "objection_type":   getattr(ctx_signals, "objection_type",  "")   if ctx_signals else "",
            "user_name":        getattr(ctx_signals, "user_name",       "")   if ctx_signals else "",
            "prompt_augmented": augmented,
            "pool_category":    pool_cat,
            "pool_conf":        pool_conf,
            "guard_flags":      guard_flags,
            # System #9 metadata
            "memory_recalled":  memory_meta.get("memory_recalled", False),
            "memory_chars":     memory_meta.get("memory_chars", 0),
            "facts_added":      memory_meta.get("facts_added", 0),
        })

        if i % 10 == 0 or not bot_response:
            tag = source.upper()[:5]
            mem_tag = f" MEM={len(memory_ctx)}ch" if memory_ctx else ""
            print(f"  [{tag:5}] [{i:02d}/{len(test_cases)}] {tc['id']}: {bot_response[:50]!r}{mem_tag}")

        if source == "llm":
            await asyncio.sleep(delay)

    n_ok  = sum(1 for r in results if r["bot_response"])
    ok_ms = [r["elapsed_ms"] for r in results if r["bot_response"] and r["elapsed_ms"] > 0]
    avg_ms = statistics.mean(ok_ms) if ok_ms else 0
    mem_n  = counts.get("memory_recalled", 0)
    facts_n = counts.get("facts_extracted", 0)
    print(
        f"  Run {run_idx}: {n_ok}/{len(results)} OK | "
        f"llm={counts['llm_calls']} pool={counts['pool_matched']} "
        f"crisis={counts['sensitive_escalated']} | "
        f"mem_recalled={mem_n} facts_extracted={facts_n} | avg {avg_ms:.0f}ms"
    )
    return results, dict(counts)


# =============================================================================
# LOAD LAYER 2 BASELINE per-case scores
# =============================================================================

def load_layer2_per_case(sweep_dir: Path) -> Dict[str, List[float]]:
    """Load per-case scores from the most recent complete Layer 2 3-run set."""
    from tests.cpe_ablation_layer2_full_detection import _extract_per_case_from_files

    by_ts: Dict[str, List[Path]] = defaultdict(list)
    for f in sorted(sweep_dir.glob("layer2_full_detection_run*.json")):
        parts = f.stem.split("_")
        ts = "_".join(parts[-2:])
        by_ts[ts].append(f)

    complete = sorted(
        [(ts, fs) for ts, fs in by_ts.items() if len(fs) == 3],
        key=lambda t: t[0], reverse=True,
    )
    if not complete:
        logger.warning("No complete layer2 3-run set found")
        return {}
    ts, files = complete[0]
    logger.info("Layer2 baseline: %s (%d files)", ts, len(files))
    return _extract_per_case_from_files(files)


# =============================================================================
# MAIN
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="CPE Ablation — Layer 2 + System #9 Memory Engine")
    parser.add_argument("--creator",        default="iris_bertran")
    parser.add_argument("--runs",    type=int, default=3)
    parser.add_argument("--model",          default=DEFAULT_MODEL)
    parser.add_argument("--delay",   type=float, default=RATE_LIMIT_DELAY)
    parser.add_argument("--evaluate-only",  action="store_true")
    args = parser.parse_args()

    creator_id = args.creator
    n_runs     = max(1, args.runs)
    model      = args.model

    data_dir  = Path(f"tests/cpe_data/{creator_id}")
    sweep_dir = data_dir / "sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 74)
    print("LAYER 2 + SYSTEM #9 ABLATION — Memory Engine")
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

    variator    = load_pool_variator(creator_id)
    calibration = load_calibration(creator_id)

    # Verify Memory Engine is enabled
    from services.memory_engine import ENABLE_MEMORY_ENGINE
    print(f"ENABLE_MEMORY_ENGINE: {ENABLE_MEMORY_ENGINE}")
    if not ENABLE_MEMORY_ENGINE:
        print("ERROR: ENABLE_MEMORY_ENGINE is False. Set env ENABLE_MEMORY_ENGINE=true.")
        sys.exit(1)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # ── GENERATION ────────────────────────────────────────────────────────────
    run_files: List[Path]  = []
    all_counts: List[dict] = []

    if args.evaluate_only:
        run_files = sorted(sweep_dir.glob("layer2_plus_system09_run*.json"))[:n_runs]
        if not run_files:
            print("ERROR: --evaluate-only but no layer2_plus_system09_run*.json found.")
            sys.exit(1)
        print(f"Evaluate-only: {len(run_files)} files")
        for rf in run_files:
            d = json.loads(rf.read_text())
            all_counts.append(d.get("intercept_counts", {}))
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
                _di._deepinfra_circuit_open_until   = 0.0
            except Exception:
                pass

            run_results, counts = await generate_run(
                conversations, base_prompt, variator, calibration,
                creator_id, model, run_idx, args.delay,
            )
            all_counts.append(counts)

            rf = sweep_dir / f"layer2_plus_system09_run{run_idx}_{ts}.json"
            payload = {
                "ablation":        "layer2_plus_system09",
                "creator":         creator_id,
                "model":           model,
                "system_prompt":   base_prompt,
                "systems_active":  [
                    "input_guards", "sensitive_detection", "pool_matching",
                    "frustration_detection", "context_signals", "compressed_doc_d",
                    "memory_engine",
                ],
                "run":             run_idx,
                "n_cases":         len(run_results),
                "timestamp":       datetime.now(timezone.utc).isoformat(),
                "intercept_counts": counts,
                "results":         run_results,
            }
            rf.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            print(f"Saved: {rf}")
            run_files.append(rf)

    # ── EVALUATION ────────────────────────────────────────────────────────────
    print("\n--- EVALUATING METRICS ---")
    all_run_results: List[List[Dict]] = []
    run_l1: List[dict] = []
    run_l2: List[dict] = []
    run_l3: List[dict] = []

    for rf in run_files:
        data    = json.loads(rf.read_text())
        results = data["results"]
        all_run_results.append(results)

        pool_n  = sum(1 for r in results if r.get("source") == "pool")
        crisis_n = sum(1 for r in results if r.get("source") == "crisis")
        llm_n   = sum(1 for r in results if r.get("source") == "llm")
        mem_n   = sum(1 for r in results if r.get("memory_recalled"))

        responses = [r["bot_response"] for r in results]
        l1 = compute_l1(responses, baseline_metrics)
        l2 = compute_l2(results)
        l3 = compute_l3_quick(results)
        run_l1.append(l1)
        run_l2.append(l2)
        run_l3.append(l3)

        print(f"  Run {data['run']}: L1={l1['score']}  "
              f"chrF={l2['chrf']:.4f}  BLEU={l2['bleu4']:.4f}  "
              f"ROUGE={l2['rouge_l']:.4f}  METEOR={l2['meteor']:.4f}  "
              f"rep={l3['rep_rate_pct']}%  "
              f"[llm={llm_n} pool={pool_n} mem={mem_n}]")

    # ── Aggregate intercept counts ─────────────────────────────────────────────
    agg_counts: Dict[str, float] = {}
    all_keys = set(k for c in all_counts for k in c)
    for k in sorted(all_keys):
        vals = [c.get(k, 0) for c in all_counts]
        agg_counts[k] = round(statistics.mean(vals), 1)

    # ── BERTScore ─────────────────────────────────────────────────────────────
    print("\nComputing BERTScore (L3)...")
    from bert_score import score as bert_score_fn

    bert_f1s: List[float] = []
    for run_data in all_run_results:
        bots  = [r["bot_response"] for r in run_data]
        leads = [r["test_input"]   for r in run_data]
        _, _, F1 = bert_score_fn(bots, leads, lang="es", verbose=False,
                                  model_type="distilbert-base-multilingual-cased")
        bert_f1s.append(float(F1.mean()))
        print(f"  BERTScore run: {F1.mean():.4f}")

    # ── STATISTICAL COMPARISONS ───────────────────────────────────────────────
    METRIC_MAP = {
        "has_emoji":    ("has_emoji",      "lower_is_better"),
        "has_excl":     ("has_excl",       "lower_is_better"),
        "q_rate":       ("q_rate",         "lower_is_better"),
        "len_mean":     ("char_len",       "lower_is_better"),
        "sentence_cnt": ("sentence_count", "lower_is_better"),
        "ca_rate":      ("is_ca",          "higher_is_better"),
        "chrf":         ("chrf",           "higher_is_better"),
        "bleu4":        ("bleu4",          "higher_is_better"),
        "rouge_l":      ("rouge_l",        "higher_is_better"),
        "meteor":       ("meteor",         "higher_is_better"),
        "len_ratio":    ("len_ratio",      "lower_is_better"),
        "rep_rate":     ("rep_rate",       "lower_is_better"),
    }

    current_pc = extract_per_case_from_results(all_run_results)

    def _compare(current: dict, reference: dict, ref_label: str) -> dict:
        out: dict = {}
        for label, (key, direction) in METRIC_MAP.items():
            cv = current.get(key, [])
            rv = reference.get(key, [])
            if not cv or not rv or len(cv) != len(rv):
                continue
            w_stat, p_val = wilcoxon_signed_rank(cv, rv)
            d = cliffs_delta(cv, rv)
            out[label] = {
                f"{ref_label}_mean": round(statistics.mean(rv), 4),
                "current_mean":      round(statistics.mean(cv), 4),
                "delta":             round(statistics.mean(cv) - statistics.mean(rv), 4),
                "wilcoxon_W":        w_stat,
                "p_value":           p_val,
                "cliffs_d":          d,
                "magnitude":         cliffs_magnitude(d),
                "significant":       p_val < 0.05,
                "direction":         direction,
            }
        return out

    print("\n--- LOADING BASELINES ---")
    layer2_pc = load_layer2_per_case(sweep_dir)
    stat_vs_layer2 = _compare(current_pc, layer2_pc, "layer2") if layer2_pc else {}

    # Layer 2 BERTScore baseline
    layer2_bert = 0.828
    try:
        with open(sweep_dir / "layer2_full_detection.json") as f:
            _l2 = json.load(f)
        layer2_bert = _l2["l3"]["agg"]["coherence_bert_f1"]["mean"]
    except Exception:
        pass

    # ── AGGREGATE ─────────────────────────────────────────────────────────────
    def _agg(vals: List[float]) -> dict:
        return {"mean": round(statistics.mean(vals), 4),
                "std":  round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
                "runs": [round(v, 4) for v in vals]}

    l1_agg: dict = {}
    for mk in ["has_emoji_pct", "has_excl_pct", "q_rate_pct", "len_mean_chars",
               "len_median_chars", "ca_rate_pct", "vocab_jac_pct", "sentence_count", "distinct_2"]:
        vals = [r["metrics"][mk]["bot"] for r in run_l1 if mk in r.get("metrics", {})]
        if vals:
            l1_agg[mk] = _agg(vals)

    # ── Memory-specific metrics ─────────────────────────────────────────────
    mem_metrics = {
        "recalls_per_run": [
            sum(1 for r in run_data if r.get("memory_recalled"))
            for run_data in all_run_results
        ],
        "avg_memory_chars": round(statistics.mean([
            r.get("memory_chars", 0) for run_data in all_run_results
            for r in run_data if r.get("memory_recalled")
        ] or [0]), 1),
        "facts_extracted_per_run": [
            sum(r.get("facts_added", 0) for r in run_data)
            for run_data in all_run_results
        ],
    }

    # ── SAMPLE CASES: 5 diverse (text-only GT) ─────────────────────────────
    import random
    random.seed(42)
    r1 = all_run_results[0]

    # Filter: only cases with real text ground_truth (no audio/sticker/media)
    r1_text = [r for r in r1 if _is_text_ground_truth(r.get("ground_truth", ""))]

    # Priority: cases where memory was recalled, then diverse sources
    memory_cases  = [r for r in r1_text if r.get("memory_recalled")]
    pool_cases    = [r for r in r1_text if r.get("source") == "pool"]
    frust_cases   = [r for r in r1_text if r.get("frustration_level", 0) >= 2]
    normal_cases  = [r for r in r1_text if r.get("source") == "llm" and not r.get("memory_recalled")]
    ctx_cases     = [r for r in r1_text if r.get("is_b2b") or r.get("is_correction") or r.get("objection_type")]

    sample: List[Dict] = []
    def _pick(pool: List, n: int = 1) -> List:
        return random.sample(pool, min(n, len(pool))) if pool else []

    # Pick 2 memory-recalled cases, 1 pool, 1 frustration/ctx, 1 normal
    for r in (_pick(memory_cases, 2) + _pick(pool_cases) + _pick(frust_cases or ctx_cases) + _pick(normal_cases)):
        if r["id"] not in {s["id"] for s in sample}:
            sample.append(r)

    remaining = [r for r in r1_text if r["id"] not in {s["id"] for s in sample}]
    sample += random.sample(remaining, max(0, 5 - len(sample)))
    sample = sample[:5]

    sample_cases = []
    for idx, r in enumerate(sample, 1):
        sample_cases.append({
            "case_idx":          idx,
            "id":                r["id"],
            "category":          r.get("category", ""),
            "language":          r.get("language", ""),
            "source":            r.get("source", ""),
            "intercept_by":      r.get("intercept_by"),
            "frustration_level": r.get("frustration_level", 0),
            "is_b2b":            r.get("is_b2b", False),
            "is_correction":     r.get("is_correction", False),
            "objection_type":    r.get("objection_type", ""),
            "user_name":         r.get("user_name", ""),
            "prompt_augmented":  r.get("prompt_augmented", False),
            "pool_category":     r.get("pool_category"),
            "pool_conf":         r.get("pool_conf", 0.0),
            "guard_flags":       r.get("guard_flags", {}),
            # System #9 fields
            "memory_recalled":   r.get("memory_recalled", False),
            "memory_chars":      r.get("memory_chars", 0),
            "facts_added":       r.get("facts_added", 0),
            "lead":              r["test_input"],
            "bot_response":      r["bot_response"],
            "ground_truth":      r["ground_truth"],
            "conversation_context": _get_conversation_context(r["id"], conversations),
        })

    # ── FINAL JSON ────────────────────────────────────────────────────────────
    final = {
        "ablation":          "layer2_plus_system09",
        "version":           "v1",
        "creator":           creator_id,
        "model":             model,
        "system_prompt":     base_prompt,
        "system_prompt_chars": len(base_prompt),
        "systems_active":    [
            "input_guards", "sensitive_detection", "pool_matching",
            "frustration_detection", "context_signals", "compressed_doc_d",
            "memory_engine",
        ],
        "n_runs":     len(all_run_results),
        "n_cases":    len(conversations),
        "computed":   datetime.now(timezone.utc).isoformat(),

        "intercept_counts_per_run":  all_counts,
        "intercept_counts_avg":      agg_counts,

        "l1": {
            "score_per_run": [r["score"] for r in run_l1],
            "agg_metrics":   l1_agg,
            "per_run":       [{"run": i+1, **r} for i, r in enumerate(run_l1)],
        },
        "l2": {
            "agg": {
                "chrf":      _agg([r["chrf"]      for r in run_l2]),
                "bleu4":     _agg([r["bleu4"]     for r in run_l2]),
                "rouge_l":   _agg([r["rouge_l"]   for r in run_l2]),
                "meteor":    _agg([r["meteor"]    for r in run_l2]),
                "len_ratio": _agg([r["len_ratio"] for r in run_l2]),
            },
            "per_run": [{"run": i+1, "chrf": r["chrf"], "bleu4": r["bleu4"],
                         "rouge_l": r["rouge_l"], "meteor": r["meteor"],
                         "len_ratio": r["len_ratio"], "n_pairs": r["n_pairs"]}
                        for i, r in enumerate(run_l2)],
        },
        "l3": {
            "agg": {
                "coherence_bert_f1":      _agg(bert_f1s),
                "repetition_rate_pct":    _agg([r["rep_rate_pct"]   for r in run_l3]),
                "hallucination_rate_pct": _agg([r["hallu_rate_pct"] for r in run_l3]),
            },
        },

        "memory_metrics":              mem_metrics,
        "statistical_comparison_vs_layer2": stat_vs_layer2,
        "sample_cases":                sample_cases,
    }

    out_path = sweep_dir / "layer2_plus_system09.json"
    out_path.write_text(json.dumps(final, indent=2, ensure_ascii=False))
    print(f"\nSaved → {out_path}")

    _print_report(final, layer2_bert)


# =============================================================================
# REPORT
# =============================================================================

def _print_report(data: dict, layer2_bert: float) -> None:
    n_total = data["n_runs"] * data["n_cases"]
    ac      = data["intercept_counts_avg"]
    mm      = data.get("memory_metrics", {})

    print(f"\n{'='*76}")
    print(f"ABLATION REPORT — Layer 2 + System #9 (Memory Engine)")
    print(f"Creator: {data['creator']} | Model: {data['model']}")
    print(f"Runs: {data['n_runs']} x {data['n_cases']} = {n_total} observations")
    print(f"{'='*76}")

    print(f"\n  SYSTEM INTERCEPTS (avg per run / {data['n_cases']} cases):")
    intercept_labels = [
        ("llm_calls",             "LLM calls"),
        ("pool_matched",          "#5 Pool matched"),
        ("sensitive_escalated",   "#1 Sensitive escalated → crisis"),
        ("frustration_moderate_plus", "#2 Frustration moderate+ (≥2)"),
        ("b2b_detected",          "#3 B2B detected"),
        ("prompt_augmented",      "   Prompt augmented (any signal)"),
        ("memory_recalled",       "#9 Memory recalled"),
        ("facts_extracted",       "#9 Facts extracted (new)"),
        ("media_flagged",         "#4 Media placeholder"),
    ]
    for key, label in intercept_labels:
        v = ac.get(key, 0)
        if v > 0 or key in ("llm_calls", "memory_recalled"):
            pct = v / data["n_cases"] * 100
            print(f"    {label:<42} {v:5.1f} ({pct:4.1f}%)")

    if mm:
        print(f"\n  MEMORY ENGINE METRICS:")
        print(f"    Recalls per run:         {mm.get('recalls_per_run', [])}")
        print(f"    Avg memory chars:        {mm.get('avg_memory_chars', 0)}")
        print(f"    Facts extracted per run:  {mm.get('facts_extracted_per_run', [])}")

    sc_l2 = data.get("statistical_comparison_vs_layer2", {})

    print(f"\n  {'METRIC':<22} {'L2(base)':>8} {'L2+Sys9':>8}  "
          f"{'delta':>8}  {'p-value':>8}  {'Cliff d':>8}  {'Mag':>9}  {'Sig':>4}")
    print(f"  {'─'*90}")

    DISPLAY = [
        ("has_emoji (%)",    "has_emoji"),
        ("has_excl (%)",     "has_excl"),
        ("q_rate (%)",       "q_rate"),
        ("len_mean (ch)",    "len_mean"),
        ("sentence_cnt",     "sentence_cnt"),
        ("ca_rate (%)",      "ca_rate"),
        ("chrF++",           "chrf"),
        ("BLEU-4",           "bleu4"),
        ("ROUGE-L",          "rouge_l"),
        ("METEOR",           "meteor"),
        ("len_ratio",        "len_ratio"),
        ("rep_rate (%)",     "rep_rate"),
    ]

    def _fmt(v): return f"{v:8.4f}" if isinstance(v, float) else f"{'—':>8}"

    for label, key in DISPLAY:
        d = sc_l2.get(key, {})
        l2_mean = d.get("layer2_mean", "—")
        cur     = d.get("current_mean", "—")
        delta   = d.get("delta", "—")
        p_val   = d.get("p_value", "—")
        cd      = d.get("cliffs_d", "—")
        sig     = "✓" if d.get("significant") else "·"
        mag     = d.get("magnitude", "—")
        print(f"  {label:<22} {_fmt(l2_mean)} {_fmt(cur)}  "
              f"{_fmt(delta)}  {_fmt(p_val)}  {_fmt(cd)}  {mag:>9}  {sig:>4}")

    bert_cur = data["l3"]["agg"]["coherence_bert_f1"]["mean"]
    bert_delta = bert_cur - layer2_bert
    print(f"  {'BERTScore':<22} {_fmt(layer2_bert)} {_fmt(bert_cur)}  "
          f"{_fmt(bert_delta)}")

    print(f"\n  L1 scores: {data['l1']['score_per_run']}")

    print(f"\n{'─'*76}")
    print("  5 SAMPLE CASES — diverse (prioritizes memory-recalled cases)")
    print(f"{'─'*76}")

    SOURCE_ICONS = {"pool": "🏊 POOL", "crisis": "🚨 CRISIS", "llm": "🤖 LLM", "empty_skip": "⭕ EMPTY"}
    for c in data["sample_cases"]:
        src_label = SOURCE_ICONS.get(c.get("source", ""), c.get("source", "?").upper())
        signals = []
        if c.get("memory_recalled"):
            signals.append(f"MEM={c.get('memory_chars', 0)}ch")
        if c.get("facts_added", 0) > 0:
            signals.append(f"facts={c['facts_added']}")
        if c.get("frustration_level", 0) >= 1:
            signals.append(f"frust={c['frustration_level']}")
        if c.get("is_b2b"):       signals.append("B2B")
        if c.get("is_correction"): signals.append("correction")
        if c.get("objection_type"): signals.append(f"obj={c['objection_type']}")
        if c.get("user_name"):    signals.append(f"name={c['user_name']!r}")
        if c.get("pool_category"): signals.append(f"pool_cat={c['pool_category']}")
        if c.get("prompt_augmented"): signals.append("aug_prompt")
        sig_str = " | ".join(signals) if signals else "—"
        print(f"\n  Case {c['case_idx']} [{src_label}] [{c['category']}/{c['language']}]")
        print(f"  Signals: {sig_str}")
        ctx = c.get("conversation_context", [])
        if ctx:
            print(f"  Context (last {len(ctx)} turns):")
            for t in ctx:
                role_tag = "👤" if t["role"] == "user" else "🤖"
                print(f"    {role_tag} {t['content'][:120]}")
        print(f"  Lead:    {c['lead'][:120]!r}")
        print(f"  Bot:     {c['bot_response'][:200]!r}")
        print(f"  GT:      {c['ground_truth'][:100]!r}")

    print(f"\n{'='*76}")
    print("CRITERION: IMPROVES = p<0.05 AND Cliff's |d| >= 0.147 (small effect)")
    print(f"{'='*76}\n")


if __name__ == "__main__":
    asyncio.run(main())
