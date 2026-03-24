"""
Prepare CPT, SFT, and DPO datasets for Qwen3-32B fine-tuning with TRL.

Usage:
    # Run locally (SFT from calibration, DPO from exported pairs):
    python scripts/prepare_finetune_data.py --stage sft dpo

    # Run on Railway (CPT needs DB access):
    railway run python scripts/prepare_finetune_data.py --stage cpt sft dpo
"""

import argparse
import json
import logging
import os
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "dpo", "trl")
CALIBRATION_PATH = os.path.join(BASE_DIR, "calibrations", "iris_bertran.json")
PAIRS_PATH = os.path.join(BASE_DIR, "data", "dpo", "preference_pairs_export.jsonl")

CREATOR_NAME = "iris_bertran"

# Distilled Doc D system prompt for SFT
SYSTEM_PROMPT = (
    "Eres Iris Bertran. Respondes DMs como lo harias tu en la vida real.\n"
    "NO eres un asistente virtual. Eres una persona real respondiendo mensajes.\n\n"
    "ESTILO:\n"
    "- Mensajes cortos (20-60 chars), como WhatsApp real\n"
    "- Emojis frecuentes: \U0001f602\U0001fae0\U0001fa77\u2764\ufe0f\U0001f618\U0001f979\n"
    "- Tono cercano, calido, informal\n"
    "- Code-switching ca/es natural dentro de la misma frase\n"
    "- Si el lead escribe en mixto, responde en mixto\n\n"
    "REGLAS:\n"
    "- NUNCA inventes precios o info de productos\n"
    "- Si no sabes algo, di que lo consultas\n"
    "- NUNCA menciones temas que el usuario NO ha mencionado\n"
    "- Para audios sin transcripcion, responde con reaccion calida"
)


def _is_valid_text(text: str) -> bool:
    """Filter out junk messages."""
    if not text or len(text.strip()) < 4:
        return False
    low = text.lower().strip()
    if any(w in low for w in ("error", "traceback", "exception", "null", "[sticker]", "[image]", "[video]")):
        return False
    return True


# ── CPT ──────────────────────────────────────────────────────────────

def build_cpt():
    """Extract all Iris manual messages from DB → CPT jsonl."""
    from api.database import SessionLocal
    from sqlalchemy import text

    if SessionLocal is None:
        logger.error("Database not configured. Run with: railway run python scripts/prepare_finetune_data.py --stage cpt")
        return 0

    session = SessionLocal()
    try:
        q = text("""
            SELECT m.content
            FROM messages m
            JOIN leads l ON l.id = m.lead_id
            JOIN creators c ON c.id = l.creator_id
            WHERE c.name = :cname
              AND m.role = 'assistant'
              AND m.copilot_action IS NULL
              AND m.content IS NOT NULL
              AND LENGTH(m.content) > 3
              AND m.created_at >= NOW() - INTERVAL '6 months'
            ORDER BY m.created_at DESC
        """)
        rows = session.execute(q, {"cname": CREATOR_NAME}).fetchall()

        out_path = os.path.join(OUT_DIR, "cpt_iris.jsonl")
        count = 0
        seen = set()
        with open(out_path, "w", encoding="utf-8") as f:
            for row in rows:
                content = row.content.strip()
                if not _is_valid_text(content):
                    continue
                if content in seen:
                    continue
                seen.add(content)
                f.write(json.dumps({"text": content}, ensure_ascii=False) + "\n")
                count += 1

        logger.info("[CPT] %d unique messages -> %s", count, out_path)
        return count
    finally:
        session.close()


# ── SFT ──────────────────────────────────────────────────────────────

def build_sft():
    """Convert calibration few-shot examples → SFT chat format."""
    with open(CALIBRATION_PATH, "r", encoding="utf-8") as f:
        cal = json.load(f)

    examples = cal.get("few_shot_examples", [])
    out_path = os.path.join(OUT_DIR, "sft_iris.jsonl")
    count = 0

    with open(out_path, "w", encoding="utf-8") as f:
        for ex in examples:
            user_msg = ex.get("user_message", "").strip()
            response = ex.get("response", "").strip()
            if not _is_valid_text(user_msg) or not _is_valid_text(response):
                continue

            row = {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": response},
                ]
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1

    logger.info("[SFT] %d examples -> %s", count, out_path)
    return count


# ── DPO ──────────────────────────────────────────────────────────────

def build_dpo():
    """Convert preference pairs → TRL DPOTrainer format."""
    out_path = os.path.join(OUT_DIR, "dpo_iris.jsonl")
    count = 0
    skipped = 0

    with open(PAIRS_PATH, "r", encoding="utf-8") as fin, \
         open(out_path, "w", encoding="utf-8") as fout:
        for line in fin:
            pair = json.loads(line)
            prompt = pair.get("prompt", "").strip()
            chosen = pair.get("chosen", "").strip()
            rejected = pair.get("rejected", "").strip()

            # Validate
            if len(chosen) < 4 or len(rejected) < 4:
                skipped += 1
                continue
            if any(w in chosen.lower() for w in ("error", "traceback")):
                skipped += 1
                continue
            if any(w in rejected.lower() for w in ("error", "traceback")):
                skipped += 1
                continue

            row = {
                "prompt": prompt,
                "chosen": chosen,
                "rejected": rejected,
            }
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1

    logger.info("[DPO] %d pairs -> %s (skipped %d)", count, out_path, skipped)
    return count


# ── Stats ────────────────────────────────────────────────────────────

def _estimate_tokens(path: str) -> int:
    """Rough token estimate: chars / 3.5 for multilingual text."""
    if not os.path.isfile(path):
        return 0
    size = os.path.getsize(path)
    return int(size / 3.5)


def print_stats():
    """Print dataset stats."""
    logger.info("\n" + "=" * 60)
    logger.info("DATASET STATS")
    logger.info("=" * 60)
    for name in ("cpt_iris.jsonl", "sft_iris.jsonl", "dpo_iris.jsonl"):
        path = os.path.join(OUT_DIR, name)
        if not os.path.isfile(path):
            logger.info("  %-20s  (not generated)", name)
            continue
        lines = sum(1 for _ in open(path))
        tokens = _estimate_tokens(path)
        size_kb = os.path.getsize(path) / 1024
        logger.info("  %-20s  %5d lines  ~%6d tokens  %.1f KB", name, lines, tokens, size_kb)
    logger.info("=" * 60)


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Prepare fine-tuning datasets for Qwen3-32B")
    parser.add_argument(
        "--stage", nargs="+", choices=["cpt", "sft", "dpo", "all"],
        default=["all"], help="Which datasets to generate",
    )
    args = parser.parse_args()

    stages = args.stage
    if "all" in stages:
        stages = ["cpt", "sft", "dpo"]

    os.makedirs(OUT_DIR, exist_ok=True)

    results = {}
    if "cpt" in stages:
        results["cpt"] = build_cpt()
    if "sft" in stages:
        results["sft"] = build_sft()
    if "dpo" in stages:
        results["dpo"] = build_dpo()

    print_stats()
    return results


if __name__ == "__main__":
    main()
