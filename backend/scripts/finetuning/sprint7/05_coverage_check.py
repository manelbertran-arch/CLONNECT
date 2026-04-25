#!/usr/bin/env python3
"""Sprint 7 — Coverage check vs CCEE eval set.

Threshold ≥0.92 + response-side matching (Patrón 8).
Solo flagear instancias reales, no patrones.

Usage:
    python3 scripts/finetuning/sprint7/05_coverage_check.py data/dpo/trl/sft_eval.jsonl
"""

import json
import sys
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

THRESHOLD = 0.92  # NOT 0.85 (Patrón 8: threshold ≥0.92 + response-side)
DATASET_PATH = "data/dpo/trl/sprint7/sft_sprint7.jsonl"


def load_jsonl(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def extract_assistant_responses(records: list) -> list:
    """Extract first assistant response per record."""
    responses = []
    for r in records:
        for m in r.get("messages", []):
            if m["role"] == "assistant":
                responses.append(m["content"])
                break
    return responses


def main() -> None:
    eval_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not eval_path or not Path(eval_path).exists():
        print(f"ERROR: eval path required. Got: {eval_path}")
        sys.exit(1)

    print(f"Loading dataset: {DATASET_PATH}")
    train = load_jsonl(DATASET_PATH)
    print(f"Loading eval: {eval_path}")
    eval_set = load_jsonl(eval_path)

    train_responses = extract_assistant_responses(train)
    eval_responses  = extract_assistant_responses(eval_set)

    print(f"Train assistant responses: {len(train_responses)}")
    print(f"Eval assistant responses:  {len(eval_responses)}")

    print("Loading sentence-transformer (paraphrase-multilingual-MiniLM-L12-v2)...")
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    print("Embedding train responses...")
    train_emb = model.encode(train_responses, show_progress_bar=True, batch_size=128)
    print("Embedding eval responses...")
    eval_emb  = model.encode(eval_responses,  show_progress_bar=True, batch_size=128)

    print("Computing cosine similarity matrix...")
    sim_matrix = cosine_similarity(eval_emb, train_emb)

    contaminated:       list = []
    high_sim_pattern:   list = []

    for i, eval_resp in enumerate(eval_responses):
        max_sim = float(sim_matrix[i].max())
        max_idx = int(sim_matrix[i].argmax())

        if max_sim >= THRESHOLD:
            contaminated.append({
                "eval_idx":  i,
                "train_idx": max_idx,
                "sim":       max_sim,
                "eval":      eval_resp[:120],
                "train":     train_responses[max_idx][:120],
            })
        elif max_sim >= 0.85:
            high_sim_pattern.append({
                "eval_idx": i,
                "sim":      max_sim,
                "eval":     eval_resp[:80],
            })

    n_eval = len(eval_responses)
    n_cont = len(contaminated)
    n_pat  = len(high_sim_pattern)

    print(f"\n{'='*60}")
    print(f"COVERAGE CHECK RESULTS")
    print(f"{'='*60}")
    print(f"Threshold (Patrón 8): {THRESHOLD}")
    print(f"Eval cases total:     {n_eval}")
    print(f"Contaminated (≥{THRESHOLD}):  {n_cont}  ({n_cont/n_eval*100:.1f}%)")
    print(f"Pattern-only (0.85–{THRESHOLD}): {n_pat}  ({n_pat/n_eval*100:.1f}%)")

    if contaminated:
        print(f"\n=== Contaminated samples ===")
        for c in contaminated[:10]:
            print(f"\n  eval[{c['eval_idx']}] sim={c['sim']:.3f}:")
            print(f"    EVAL:      {c['eval']}")
            print(f"    TRAIN[{c['train_idx']}]: {c['train']}")

    # ── Write report ─────────────────────────────────────────────────────────
    report_path = Path("docs/finetuning_sprint_iris/sprint7/coverage_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with report_path.open("w", encoding="utf-8") as f:
        f.write("# Sprint 7 — Coverage Check vs CCEE Eval\n\n")
        f.write(f"**Date:** 2026-04-26  \n")
        f.write(f"**Dataset:** `{DATASET_PATH}` ({len(train)} records)  \n")
        f.write(f"**Eval set:** `{eval_path}` ({n_eval} records)  \n")
        f.write(f"**Threshold:** {THRESHOLD} (Patrón 8 — response-side, no patrones)  \n\n")
        f.write("## Results\n\n")
        f.write(f"| Metric | Value |\n|---|---|\n")
        f.write(f"| Eval cases | {n_eval} |\n")
        f.write(f"| Contaminated (sim ≥ {THRESHOLD}) | **{n_cont}** ({n_cont/n_eval*100:.1f}%) |\n")
        f.write(f"| Pattern-only (0.85 ≤ sim < {THRESHOLD}) | {n_pat} ({n_pat/n_eval*100:.1f}%) |\n\n")

        if contaminated:
            f.write("## Contaminated Samples\n\n")
            for c in contaminated:
                f.write(f"### eval[{c['eval_idx']}]  sim={c['sim']:.3f}\n\n")
                f.write(f"- **EVAL:**  `{c['eval']}`\n")
                f.write(f"- **TRAIN[{c['train_idx']}]:** `{c['train']}`\n\n")
        else:
            f.write("## Verdict\n\n")
            f.write("✅ **No contamination detected** at threshold 0.92 (response-side).\n\n")
            f.write("Fase 2 coverage check PASS — proceed to Fase 3 (smoke training).\n")

    print(f"\nReport: {report_path}")

    if n_cont > 0:
        print(f"\n⚠️  {n_cont} contaminated case(s) require removal from sft_sprint7.jsonl")
    else:
        print(f"\n✅ No contamination at threshold {THRESHOLD} — Fase 2 PASS")


if __name__ == "__main__":
    main()
