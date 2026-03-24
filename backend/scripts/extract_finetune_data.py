"""
Extract CPT, SFT, and DPO datasets for Iris Bertran fine-tuning.

Usage:
    railway run python3 scripts/extract_finetune_data.py

Outputs:
    data/dpo/cpt_iris.jsonl  — Iris manual messages for continued pre-training
    data/dpo/sft_iris.jsonl  — Calibration few-shot examples in TRL chat format
    data/dpo/dpo_iris.jsonl  — Preference pairs in TRL DPO format
"""

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

CREATOR_ID = "iris_bertran"
CREATOR_UUID = "8e9d1705-4772-40bd-83b1-c6821c5593bf"
OUT_DIR = REPO / "data" / "dpo"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def get_db_connection():
    import psycopg2
    return psycopg2.connect(os.environ["DATABASE_URL"])


def extract_cpt():
    """Extract all manual Iris messages (last 6 months) for continued pre-training."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT m.content
        FROM messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE l.creator_id = %s
          AND m.role = 'assistant'
          AND m.created_at > NOW() - INTERVAL '6 months'
          AND m.deleted_at IS NULL
          AND (
              m.copilot_action = 'resolved_externally'
              OR (m.copilot_action IS NULL AND m.approved_by = 'creator_manual')
          )
          AND LENGTH(m.content) > 3
        ORDER BY m.created_at
    """, (CREATOR_UUID,))

    seen = set()
    lines = []
    for (content,) in cur.fetchall():
        key = content.strip()[:80]
        if key in seen:
            continue
        seen.add(key)
        text = content.strip()
        if len(text) < 5 or "Waze" in text or "hora de llegada" in text:
            continue
        lines.append(json.dumps({"text": text}, ensure_ascii=False))

    path = OUT_DIR / "cpt_iris.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    total_chars = sum(len(json.loads(l)["text"]) for l in lines)
    conn.close()
    return {"lines": len(lines), "chars": total_chars, "tokens_est": total_chars // 4}


def extract_sft():
    """Build SFT dataset from calibration file in TRL chat format."""
    cal_path = REPO / "calibrations" / "iris_bertran.json"
    with open(cal_path) as f:
        cal = json.load(f)

    # Load Doc D from DB
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT pd.content FROM personality_docs pd
        JOIN creators c ON c.id::text = pd.creator_id
        WHERE c.name = %s AND pd.doc_type IN ('doc_d_distilled', 'doc_d')
        ORDER BY CASE pd.doc_type WHEN 'doc_d_distilled' THEN 0 ELSE 1 END
        LIMIT 1
    """, (CREATOR_ID,))
    row = cur.fetchone()
    doc_d = row[0][:3000] if row else "Eres Iris Bertran, instructora de fitness en Barcelona."
    conn.close()

    lines = []
    for ex in cal.get("few_shot_examples", []):
        user_msg = ex.get("user_message", "")
        response = ex.get("response", "")
        if not user_msg or not response:
            continue
        entry = {
            "messages": [
                {"role": "system", "content": doc_d},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": response},
            ]
        }
        lines.append(json.dumps(entry, ensure_ascii=False))

    path = OUT_DIR / "sft_iris.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    total_chars = sum(len(l) for l in lines)
    return {"lines": len(lines), "chars": total_chars, "tokens_est": total_chars // 4}


def extract_dpo():
    """Export preference pairs in TRL DPO format."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT pp.chosen_response, pp.rejected_response,
               pp.user_message, pp.context_summary
        FROM preference_pairs pp
        WHERE pp.creator_id = %s AND pp.is_active = true
        ORDER BY pp.created_at
    """, (CREATOR_UUID,))

    lines = []
    for chosen, rejected, user_msg, ctx in cur.fetchall():
        if not chosen or not rejected or len(chosen) < 4 or len(rejected) < 4:
            continue
        prompt = user_msg or ""
        if ctx:
            prompt = f"[Context: {ctx[:200]}]\n{prompt}"
        lines.append(json.dumps({
            "prompt": prompt.strip(),
            "chosen": chosen.strip(),
            "rejected": rejected.strip(),
        }, ensure_ascii=False))

    path = OUT_DIR / "dpo_iris.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    conn.close()
    total_chars = sum(len(l) for l in lines)
    return {"lines": len(lines), "chars": total_chars, "tokens_est": total_chars // 4}


if __name__ == "__main__":
    print("=" * 55)
    print("  FINETUNE DATA EXTRACTION — iris_bertran")
    print("=" * 55)

    print("\n1. CPT (Continued Pre-Training)...")
    cpt = extract_cpt()
    print(f"   {cpt['lines']} lines, {cpt['chars']:,} chars, ~{cpt['tokens_est']:,} tokens")

    print("\n2. SFT (Supervised Fine-Tuning)...")
    sft = extract_sft()
    print(f"   {sft['lines']} lines, {sft['chars']:,} chars, ~{sft['tokens_est']:,} tokens")

    print("\n3. DPO (Direct Preference Optimization)...")
    dpo = extract_dpo()
    print(f"   {dpo['lines']} lines, {dpo['chars']:,} chars, ~{dpo['tokens_est']:,} tokens")

    total_tokens = cpt["tokens_est"] + sft["tokens_est"] + dpo["tokens_est"]

    print("\n" + "=" * 55)
    print("  SUMMARY")
    print("=" * 55)
    print(f"  CPT:  {cpt['lines']:>5} lines  ~{cpt['tokens_est']:>7,} tokens  data/dpo/cpt_iris.jsonl")
    print(f"  SFT:  {sft['lines']:>5} lines  ~{sft['tokens_est']:>7,} tokens  data/dpo/sft_iris.jsonl")
    print(f"  DPO:  {dpo['lines']:>5} lines  ~{dpo['tokens_est']:>7,} tokens  data/dpo/dpo_iris.jsonl")
    print(f"  Total:              ~{total_tokens:>7,} tokens")
    print()
    print("  GPU time estimate (A100 80GB, Qwen3-32B QLoRA r=32):")
    print(f"    CPT (1 epoch):  ~{max(1, cpt['tokens_est'] // 5000)} min")
    print(f"    SFT (3 epochs): ~{max(1, sft['tokens_est'] * 3 // 5000)} min")
    print(f"    DPO (1 epoch):  ~{max(1, dpo['tokens_est'] // 3000)} min")
    print("=" * 55)
