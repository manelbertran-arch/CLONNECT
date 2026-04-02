"""
CPE Ablation — Layer 2 + System #6: Conversation State Loader.

Inherits all Layer 2 systems:
  #4 Input Guards, #1 Sensitive, #5 Pool Matching,
  #2 Frustration, #3 Context Signals, Doc D v3

ADDS System #6:
  - Injects conversation history (last 10 messages) as multi-turn context
  - Multi-turn test cases use their `turns` field
  - Single-turn cases get no history (as in production for first message)
  - Media placeholders cleaned via _clean_media_placeholders()
  - Leading assistant messages stripped (Gemini compatibility)
  - Consecutive same-role messages merged
  - Individual messages truncated to 600 chars

Methodology:
  - PersonaGym (EMNLP 2025) + AbGen (ACL 2025)
  - 3 runs × 50 cases = 150 observations
  - L1 (9) + L2 (5+SemSim) + L3 (BERTScore + rep + hallucination)

Usage:
    python3 tests/cpe_ablation_layer2_plus_sys06.py --creator iris_bertran
    python3 tests/cpe_ablation_layer2_plus_sys06.py --creator iris_bertran --evaluate-only

Output:
    tests/cpe_data/{creator}/sweep/layer2_plus_system06_run{N}_{ts}.json
    tests/cpe_data/{creator}/sweep/layer2_plus_system06.json
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
logger = logging.getLogger("cpe_l2_sys06")
logger.setLevel(logging.INFO)

# Import everything we need from the Layer 2 script
from tests.cpe_ablation_layer2_full_detection import (
    DEFAULT_MODEL,
    RATE_LIMIT_DELAY,
    SENSITIVE_CONFIDENCE,
    SENSITIVE_ESCALATION,
    POOL_CONFIDENCE,
    POOL_MAX_MSG_LEN,
    INPUT_MAX_LEN,
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
    load_naked_per_case,
    load_layer1_per_case,
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

ABLATION_NAME = "layer2_plus_system06"
SYSTEMS_ACTIVE = [
    "input_guards", "sensitive_detection", "pool_matching",
    "frustration_detection", "context_signals", "compressed_doc_d",
    "conversation_state_loader",
]

# History processing constants (from generation.py)
MAX_HISTORY = 10
MAX_MSG_CHARS = 600


# =============================================================================
# SYSTEM #6: Conversation History Processing
# =============================================================================

def process_history(turns: List[Dict]) -> List[Dict[str, str]]:
    """Process conversation turns into LLM-ready multi-turn messages.

    Mirrors production pipeline (generation.py:308-336):
    1. Take last 10 messages
    2. Clean media placeholders
    3. Strip leading assistant messages (Gemini requires user first)
    4. Merge consecutive same-role messages
    5. Truncate individual messages to 600 chars
    """
    if not turns:
        return []

    # Step 1: Take last 10
    history = [
        {"role": t.get("role", "user"), "content": t.get("content", "")}
        for t in turns[-MAX_HISTORY:]
        if t.get("content")
    ]

    # Step 2: Clean media placeholders
    from core.dm.helpers import _clean_media_placeholders
    history = _clean_media_placeholders(history)

    # Step 3: Strip leading assistant messages
    while history and history[0]["role"] == "assistant":
        history.pop(0)

    if not history:
        return []

    # Step 4: Merge consecutive same-role messages
    merged = [history[0]]
    for msg in history[1:]:
        if msg["role"] == merged[-1]["role"]:
            merged[-1]["content"] += "\n" + msg["content"]
        else:
            merged.append(msg)

    # Step 5: Truncate individual messages
    for msg in merged:
        if len(msg["content"]) > MAX_MSG_CHARS:
            msg["content"] = msg["content"][:MAX_MSG_CHARS]

    return merged


# =============================================================================
# GENERATION — Layer 2 + System #6
# =============================================================================

async def generate_l2_sys06_run(
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
    One run through Layer 2 + System #6 (conversation history).
    Identical to Layer 2 except multi-turn messages are injected before user message.
    """
    from core.sensitive_detector import detect_sensitive_content, get_crisis_resources
    from core.frustration_detector import get_frustration_detector
    from core.context_detector import detect_all as detect_context
    from services.length_controller import classify_lead_context
    from core.providers.deepinfra_provider import call_deepinfra

    frustration_detector = get_frustration_detector()

    counts = defaultdict(int)

    logger.info("[Run %d] l2+sys06 | model=%s | cases=%d", run_idx, model, len(test_cases))

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

        # System #6: Process conversation history
        raw_turns = tc.get("turns", [])
        history = process_history(raw_turns)
        n_history = len(history)
        if n_history > 0:
            counts["history_injected"] += 1
            counts["total_history_msgs"] += n_history

        # ── GUARD #4: Input Guards ─────────────────────────────────────────
        message, guard_flags = run_input_guards(original_message)

        if guard_flags["is_empty"]:
            counts["empty_skipped"] += 1
            source       = "empty_skip"
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
                        source       = "crisis"
                        intercept_by = f"sensitive_{sensitive.type.value}"
                        counts["sensitive_escalated"] += 1
            except Exception as e:
                logger.debug("Sensitive detection error: %s", e)

            # ── SYSTEM #5: Pool Matching ───────────────────────────────────
            if not bot_response and len(message.strip()) <= POOL_MAX_MSG_LEN:
                try:
                    pool_context = classify_lead_context(message)
                    match = variator.try_pool_response(
                        lead_message   = message,
                        min_confidence = 0.70,
                        calibration    = calibration,
                        turn_index     = i,
                        conv_id        = f"l2s06_run{run_idx}_{i}",
                        context        = pool_context,
                        creator_id     = creator_id,
                    )
                    if match.matched and match.confidence >= POOL_CONFIDENCE:
                        bot_response = match.response.strip()
                        source       = "pool"
                        intercept_by = f"pool_{match.category}"
                        pool_cat     = match.category
                        pool_conf    = round(match.confidence, 3)
                        counts["pool_matched"] += 1
                except Exception as e:
                    logger.debug("Pool matching error: %s", e)

            # ── SYSTEM #2: Frustration Detection ───────────────────────────
            try:
                frust_signals, frust_score = frustration_detector.analyze_message(
                    message, f"l2s06_run{run_idx}_{i}"
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

            # ── LLM GENERATION with history (System #6) ────────────────────
            if not bot_response:
                counts["llm_calls"] += 1
                prompt = build_augmented_prompt(base_prompt, frust_level, ctx_signals)
                augmented = (prompt != base_prompt)
                if augmented:
                    counts["prompt_augmented"] += 1

                # Build messages: system + history + current user message
                messages = [{"role": "system", "content": prompt}]

                # Inject conversation history (System #6)
                if history:
                    messages.extend(history)

                messages.append({"role": "user", "content": message})

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
            "id":               tc["id"],
            "test_input":       original_message,
            "ground_truth":     tc.get("ground_truth", ""),
            "bot_response":     bot_response,
            "category":         tc.get("category", ""),
            "language":         tc.get("language", ""),
            "is_multi_turn":    tc.get("is_multi_turn", False),
            "n_history_turns":  n_history,
            "elapsed_ms":       elapsed_ms,
            "tokens_in":        tokens_in,
            "tokens_out":       tokens_out,
            "run":              run_idx,
            "source":           source,
            "intercept_by":     intercept_by,
            "frustration_level": frust_level,
            "is_b2b":           getattr(ctx_signals, "is_b2b",        False) if ctx_signals else False,
            "is_correction":    getattr(ctx_signals, "is_correction",  False) if ctx_signals else False,
            "objection_type":   getattr(ctx_signals, "objection_type", "")   if ctx_signals else "",
            "user_name":        getattr(ctx_signals, "user_name",      "")   if ctx_signals else "",
            "prompt_augmented": augmented,
            "pool_category":    pool_cat,
            "pool_conf":        pool_conf,
            "guard_flags":      guard_flags,
        })

        if i % 10 == 0 or not bot_response:
            tag = source.upper()[:5]
            mt  = "MT" if tc.get("is_multi_turn") else "ST"
            print(f"  [{tag:5}] [{i:02d}/{len(test_cases)}] {tc['id']} ({mt},h={n_history}): {bot_response[:55]!r}")

        if source == "llm":
            await asyncio.sleep(delay)

    n_ok   = sum(1 for r in results if r["bot_response"])
    ok_ms  = [r["elapsed_ms"] for r in results if r["bot_response"] and r["elapsed_ms"] > 0]
    avg_ms = statistics.mean(ok_ms) if ok_ms else 0
    mt_n   = sum(1 for r in results if r["is_multi_turn"])
    h_avg  = statistics.mean(r["n_history_turns"] for r in results) if results else 0
    print(
        f"  Run {run_idx}: {n_ok}/{len(results)} OK | "
        f"llm={counts['llm_calls']} pool={counts['pool_matched']} "
        f"crisis={counts.get('sensitive_escalated', 0)} | "
        f"multi-turn={mt_n} history_avg={h_avg:.1f} | avg {avg_ms:.0f}ms"
    )
    return results, dict(counts)


# =============================================================================
# LOAD Layer 2 PER-CASE for statistical comparison
# =============================================================================

def load_layer2_per_case(sweep_dir: Path) -> Dict[str, List[float]]:
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
# SEMSIM
# =============================================================================

def compute_semsim(all_run_results: List[List[Dict]]) -> List[float]:
    """Compute SemSim (cosine similarity) per run using multilingual embeddings."""
    import numpy as np
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    except ImportError:
        logger.warning("sentence-transformers not installed, skipping SemSim")
        return []

    semsim_per_run = []
    for run_data in all_run_results:
        bots = [r["bot_response"] for r in run_data]
        gts  = [r["ground_truth"] for r in run_data]
        bot_embs = model.encode(bots, show_progress_bar=False)
        gt_embs  = model.encode(gts,  show_progress_bar=False)
        sims = [
            float(np.dot(b, g) / (np.linalg.norm(b) * np.linalg.norm(g) + 1e-9))
            for b, g in zip(bot_embs, gt_embs)
        ]
        semsim_per_run.append(round(float(np.mean(sims)), 4))
        print(f"  SemSim run: {semsim_per_run[-1]:.4f}")

    return semsim_per_run


# =============================================================================
# REPORT
# =============================================================================

def _print_report(data: dict, naked_bert: float, layer1_bert: float, layer2_bert: float) -> None:
    n_total = data["n_runs"] * data["n_cases"]
    ac      = data["intercept_counts_avg"]

    print(f"\n{'='*80}")
    print(f"ABLATION REPORT — Layer 2 + System #6: Conversation State Loader")
    print(f"Creator: {data['creator']} | Model: {data['model']}")
    print(f"Runs: {data['n_runs']} × {data['n_cases']} = {n_total} observations")
    print(f"{'='*80}")

    print(f"\n  SYSTEM INTERCEPTS (avg per run / {data['n_cases']} cases):")
    intercept_labels = [
        ("llm_calls",                "LLM calls"),
        ("pool_matched",             "#5 Pool matched"),
        ("sensitive_escalated",      "#1 Sensitive escalated → crisis"),
        ("frustration_moderate_plus","#2 Frustration moderate+ (≥2)"),
        ("b2b_detected",             "#3 B2B detected"),
        ("prompt_augmented",         "   Prompt augmented (any signal)"),
        ("media_flagged",            "#4 Media placeholder"),
        ("history_injected",         "#6 History injected (multi-turn)"),
        ("total_history_msgs",       "#6 Total history messages"),
    ]
    for key, label in intercept_labels:
        v = ac.get(key, 0)
        if v > 0 or key in ("llm_calls",):
            pct = v / data["n_cases"] * 100
            print(f"    {label:<42} {v:5.1f} ({pct:4.1f}%)")

    sc_n  = data.get("statistical_comparison_vs_naked",  {})
    sc_l1 = data.get("statistical_comparison_vs_layer1", {})
    sc_l2 = data.get("statistical_comparison_vs_layer2", {})

    print(f"\n  {'METRIC':<22} {'NAKED':>8} {'L1':>8} {'L2':>8} {'L2+S6':>8}  "
          f"{'vs-L2 p':>8}  {'Cliff':>7}  {'Sig':>6}")
    print(f"{'─'*96}")

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
        n   = sc_n.get(key,  {})
        l1  = sc_l1.get(key, {})
        l2  = sc_l2.get(key, {})
        n_mean  = n.get("naked_mean",   "—")
        l1_mean = l1.get("layer1_mean",  "—")
        l2_mean = l2.get("layer2_mean",  "—")
        cur     = l2.get("current_mean", n.get("current_mean", "—"))
        lp_val  = l2.get("p_value",  "—")
        ld      = l2.get("cliffs_d", "—")
        ls      = "✓" if l2.get("significant") else "·"
        print(f"  {label:<22} {_fmt(n_mean)} {_fmt(l1_mean)} {_fmt(l2_mean)} {_fmt(cur)} "
              f"  {_fmt(lp_val)} {ls}  {_fmt(ld)}  {l2.get('magnitude','—'):>9}")

    bert_cur = data["l3"]["agg"]["coherence_bert_f1"]["mean"]
    print(f"  {'BERTScore':<22} {_fmt(naked_bert)} {_fmt(layer1_bert)} {_fmt(layer2_bert)} {_fmt(bert_cur)}")

    semsim = data["l3"]["agg"].get("semsim", {})
    if semsim:
        print(f"  {'SemSim':<22} {'—':>8} {'—':>8} {'—':>8} {_fmt(semsim['mean'])}")

    print(f"\n  L1 scores: {data['l1']['score_per_run']}")

    print(f"\n{'─'*80}")
    print("  5 CASES FOR HUMAN EVALUATION")
    print(f"{'─'*80}")

    SOURCE_ICONS = {"pool": "🏊 POOL", "crisis": "🚨 CRISIS", "llm": "🤖 LLM", "empty_skip": "⭕ EMPTY"}
    for c in data["sample_cases"]:
        src_label = SOURCE_ICONS.get(c.get("source", ""), c.get("source", "?").upper())
        mt_label  = "MT" if c.get("is_multi_turn") else "ST"
        h_n       = c.get("n_history_turns", 0)
        signals   = []
        if c.get("frustration_level", 0) >= 1:
            signals.append(f"frust={c['frustration_level']}")
        if c.get("is_b2b"):        signals.append("B2B")
        if c.get("is_correction"):  signals.append("correction")
        if c.get("objection_type"): signals.append(f"obj={c['objection_type']}")
        if c.get("prompt_augmented"): signals.append("aug_prompt")
        sig_str = " | ".join(signals) if signals else "—"

        print(f"\n  Case {c['case_idx']} [{src_label}] [{c['category']}/{c['language']}] ({mt_label}, history={h_n})")
        print(f"  Signals: {sig_str}")
        ctx = c.get("conversation_context", [])
        if ctx:
            print(f"  Context (last {len(ctx)} turns):")
            for t in ctx:
                role_tag = "👤" if t["role"] == "user" else "🤖"
                print(f"    {role_tag} {t['content'][:120]}")
        print(f"  Lead:      \"{c['lead'][:120]}\"")
        print(f"  Bot:       \"{c['bot_response'][:200]}\"")
        print(f"  Iris real: \"{c['ground_truth'][:120]}\"")

    print(f"\n{'='*80}")
    print("CRITERION: IMPROVES = p<0.05 AND Cliff's |d| ≥ 0.147 (small effect)")
    print(f"{'='*80}\n")


# =============================================================================
# MAIN
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="CPE Ablation — Layer 2 + System #6")
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

    print("\n" + "="*80)
    print("LAYER 2 + SYSTEM #6 ABLATION — Conversation State Loader")
    print("="*80)

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

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # ── GENERATION ────────────────────────────────────────────────────────────
    run_files: List[Path]      = []
    all_counts: List[dict]     = []

    if args.evaluate_only:
        run_files = sorted(sweep_dir.glob(f"{ABLATION_NAME}_run*.json"))[:n_runs]
        if not run_files:
            print(f"ERROR: --evaluate-only but no {ABLATION_NAME}_run*.json found.")
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

            run_results, counts = await generate_l2_sys06_run(
                conversations, base_prompt, variator, calibration,
                creator_id, model, run_idx, args.delay,
            )
            all_counts.append(counts)

            rf = sweep_dir / f"{ABLATION_NAME}_run{run_idx}_{ts}.json"
            payload = {
                "ablation":        ABLATION_NAME,
                "creator":         creator_id,
                "model":           model,
                "system_prompt":   base_prompt,
                "systems_active":  SYSTEMS_ACTIVE,
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
        aug_n   = sum(1 for r in results if r.get("prompt_augmented"))

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
              f"[llm={llm_n} pool={pool_n} crisis={crisis_n} aug={aug_n}]")

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

    # ── SemSim ────────────────────────────────────────────────────────────────
    print("\nComputing SemSim...")
    semsim_runs = compute_semsim(all_run_results)

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
    naked_pc  = load_naked_per_case(sweep_dir)
    layer1_pc = load_layer1_per_case(sweep_dir)
    layer2_pc = load_layer2_per_case(sweep_dir)

    stat_vs_naked  = _compare(current_pc, naked_pc,  "naked")  if naked_pc  else {}
    stat_vs_layer1 = _compare(current_pc, layer1_pc, "layer1") if layer1_pc else {}
    stat_vs_layer2 = _compare(current_pc, layer2_pc, "layer2") if layer2_pc else {}

    # Load BERTScore baselines
    naked_bert  = 0.828
    layer1_bert = 0.828
    layer2_bert = 0.859

    naked_def = data_dir / "naked_baseline_definitive.json"
    if naked_def.exists():
        try:
            _nb = json.loads(naked_def.read_text())
            naked_bert = statistics.mean(_nb["l3"]["metrics"]["coherence_bert_f1"]["runs"])
        except Exception:
            pass
    try:
        with open(sweep_dir / "layer1_doc_d.json") as f:
            _l1 = json.load(f)
        layer1_bert = _l1["l3"]["agg"]["coherence_bert_f1"]["mean"]
    except Exception:
        pass
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

    # ── SAMPLE CASES: diverse selection (text-only GT) ──────────────────────
    import random
    random.seed(42)
    r1 = all_run_results[0]

    # Filter: only cases with real text ground_truth
    r1_text = [r for r in r1 if _is_text_ground_truth(r.get("ground_truth", ""))]

    # Prioritize multi-turn cases (System #6 only affects these)
    mt_cases     = [r for r in r1_text if r.get("is_multi_turn")]
    pool_cases   = [r for r in r1_text if r.get("source") == "pool"]
    frust_cases  = [r for r in r1_text if r.get("frustration_level", 0) >= 2]
    normal_cases = [r for r in r1_text if r.get("source") == "llm" and not r.get("is_multi_turn")
                    and not r.get("frustration_level") and not r.get("is_b2b")]
    ctx_cases    = [r for r in r1_text if r.get("is_b2b") or r.get("objection_type")]

    sample: List[Dict] = []
    def _pick(pool: List, n: int = 1) -> List:
        return random.sample(pool, min(n, len(pool))) if pool else []

    # Pick 2-3 multi-turn (the interesting ones for System #6), then fill
    for r in (_pick(mt_cases, 3) + _pick(frust_cases) + _pick(pool_cases) +
              _pick(normal_cases) + _pick(ctx_cases)):
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
            "is_multi_turn":     r.get("is_multi_turn", False),
            "n_history_turns":   r.get("n_history_turns", 0),
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
            "lead":              r["test_input"],
            "bot_response":      r["bot_response"],
            "ground_truth":      r["ground_truth"],
            "conversation_context": _get_conversation_context(r["id"], conversations),
        })

    # ── FINAL JSON ────────────────────────────────────────────────────────────
    l3_agg = {
        "coherence_bert_f1":      _agg(bert_f1s),
        "repetition_rate_pct":    _agg([r["rep_rate_pct"]   for r in run_l3]),
        "hallucination_rate_pct": _agg([r["hallu_rate_pct"] for r in run_l3]),
    }
    if semsim_runs:
        l3_agg["semsim"] = _agg(semsim_runs)

    final = {
        "ablation":          ABLATION_NAME,
        "version":           "v1",
        "creator":           creator_id,
        "model":             model,
        "system_prompt":     base_prompt,
        "system_prompt_chars": len(base_prompt),
        "systems_active":    SYSTEMS_ACTIVE,
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
        "l3": {"agg": l3_agg},

        "statistical_comparison_vs_naked":  stat_vs_naked,
        "statistical_comparison_vs_layer1": stat_vs_layer1,
        "statistical_comparison_vs_layer2": stat_vs_layer2,
        "sample_cases": sample_cases,
    }

    out_path = sweep_dir / f"{ABLATION_NAME}.json"
    out_path.write_text(json.dumps(final, indent=2, ensure_ascii=False))
    print(f"\nSaved → {out_path}")

    _print_report(final, naked_bert, layer1_bert, layer2_bert)


if __name__ == "__main__":
    asyncio.run(main())
