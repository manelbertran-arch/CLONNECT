"""
Build SFT v4 dataset — Sprint 10 W2.

Fixes:
  BUG-12: 100% 1-turn → 60% 1-turn + 40% multi-turn (Llama 3 ratio)
  BUG-13: filter assistant responses >200 chars (Doc D conformity)
  BUG-14: rotate 3 system prompt variants (prevents overfitting on single prompt)

Usage:
  cd ~/Clonnect/backend
  set -a && source .env && set +a
  .venv/bin/python3.11 scripts/finetuning/build_sft_v4.py [--dry-run] [--target N]
"""

import argparse
import json
import os
import re
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import create_engine, text

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

IRIS_UUID = "8e9d1705-4772-40bd-83b1-c6821c5593bf"
SFT_V3_PATH = Path("data/dpo/trl/sft_v3_clean.jsonl")
SFT_V4_PATH = Path("data/dpo/trl/sft_v4_multiturn.jsonl")
SPRINT7_DOC_D = Path("data/personality_extractions/iris_bertran/doc_d_bot_configuration_sprint7_freeze.md")

TARGET_TOTAL = 10_000
SINGLE_TURN_RATIO = 0.60
MAX_ASST_CHARS = 200
RANDOM_SEED = 42
MAX_SEQ_LEN = 8192          # Training context window (Opción A decision)
CHARS_PER_TOKEN = 3.5       # Conservative estimate for ES/CA mixed text
MAX_TOTAL_CHARS = int(MAX_SEQ_LEN * CHARS_PER_TOKEN * 0.95)  # 5% safety margin

_MEDIA_PATTERN = re.compile(
    r"^\s*\[(audio|video|image|foto|sticker|gif|document)\]\s*$", re.IGNORECASE
)


def is_media_only(text: str) -> bool:
    return bool(_MEDIA_PATTERN.match(text.strip()))


def clean_content(text: str) -> str:
    cleaned = re.sub(
        r"\[(audio|video|image|foto|sticker|gif|document)\]", "", text, flags=re.IGNORECASE
    )
    return cleaned.strip()


def merge_consecutive_roles(messages: list) -> list:
    """Merge consecutive messages from same role (real DM behavior)."""
    if not messages:
        return []
    merged = [messages[0].copy()]
    for m in messages[1:]:
        if m["role"] == merged[-1]["role"]:
            merged[-1]["content"] = merged[-1]["content"] + "\n" + m["content"]
        else:
            merged.append(m.copy())
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# System prompt variants (BUG-14)
# Uses 3 existing validated Doc D versions.
# Per CLAUDE.md: do NOT synthesize or compress identity signals.
# ─────────────────────────────────────────────────────────────────────────────

def load_system_variants(eng) -> list:
    """Load existing Doc D system prompt variants (2-3 versions)."""
    variants = []

    # V0: SFT v3 system prompt — sprint7 freeze baseline (validated)
    if SPRINT7_DOC_D.exists():
        variants.append(SPRINT7_DOC_D.read_text().strip())
    else:
        with open(SFT_V3_PATH) as f:
            rec = json.loads(f.readline())
        sys_msg = next(m for m in rec["messages"] if m["role"] == "system")
        variants.append(sys_msg["content"])

    # V1: doc_d from DB — current live system (updated, expanded)
    with eng.connect() as c:
        row = c.execute(text("""
            SELECT content FROM personality_docs
            WHERE creator_id = :cid AND doc_type = 'doc_d'
            ORDER BY created_at DESC LIMIT 1
        """), {"cid": IRIS_UUID}).fetchone()
    if row:
        sp = _extract_system_block(row[0])
        if sp and len(sp) > 500:
            variants.append(sp)

    # V2: doc_d_v1 from DB — original full Doc D
    with eng.connect() as c:
        row = c.execute(text("""
            SELECT content FROM personality_docs
            WHERE creator_id = :cid AND doc_type = 'doc_d_v1'
            ORDER BY created_at DESC LIMIT 1
        """), {"cid": IRIS_UUID}).fetchone()
    if row:
        sp = _extract_system_block(row[0])
        if sp and len(sp) > 500:
            # Cap at 16,000 chars: verified Qwen3 tokenizer gives 7,003 tokens
            # Full record = 7,003 + ~100 conv = ~7,100 → fits in 8000 with margin
            variants.append(sp[:16000])

    print(f"Loaded {len(variants)} system prompt variants:")
    for i, v in enumerate(variants):
        print(f"  V{i}: {len(v)} chars")

    if len(variants) < 2:
        variants.append(variants[0])  # fallback: duplicate V0

    return variants


def _extract_system_block(doc_text: str) -> str:
    """Extract the system prompt from the ``` block after ## 4.1 section."""
    # Find the ``` block right after ## 4.1
    m = re.search(r"##\s*4\.1[^\n]*\n```[^\n]*\n(.*?)```", doc_text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Fallback: any ``` block of >500 chars
    for m in re.finditer(r"```[^\n]*\n(.*?)```", doc_text, re.DOTALL):
        content = m.group(1).strip()
        if len(content) > 500:
            return content
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Single-turn data (from SFT v3, with BUG-13 filter)
# ─────────────────────────────────────────────────────────────────────────────

def load_single_turn() -> list:
    """Load user+assistant pairs from SFT v3, dropping asst >200 chars."""
    single = []
    skipped = 0
    with open(SFT_V3_PATH) as f:
        for line in f:
            rec = json.loads(line)
            msgs = [m for m in rec["messages"] if m["role"] != "system"]
            asst_msgs = [m for m in msgs if m["role"] == "assistant"]
            if any(len(m["content"]) > MAX_ASST_CHARS for m in asst_msgs):
                skipped += 1
                continue
            single.append(msgs)
    print(f"\nSingle-turn (SFT v3): {len(single)} kept, {skipped} dropped (BUG-13)")
    return single


# ─────────────────────────────────────────────────────────────────────────────
# Multi-turn data (from DB messages, with sliding window)
# ─────────────────────────────────────────────────────────────────────────────

def load_multiturn_raw(eng) -> dict:
    """Load all Iris conversations from DB, cleaned and merged."""
    with eng.connect() as c:
        rows = c.execute(text("""
            SELECT m.lead_id, m.role, m.content, m.created_at
            FROM messages m
            JOIN leads l ON m.lead_id = l.id
            WHERE l.creator_id = :cid
              AND m.deleted_at IS NULL
              AND m.content IS NOT NULL
              AND LENGTH(m.content) > 0
            ORDER BY m.lead_id, m.created_at
        """), {"cid": IRIS_UUID}).fetchall()

    convs = defaultdict(list)
    for r in rows:
        content = clean_content(r[2])
        if content:
            convs[str(r[0])].append({"role": r[1], "content": content})

    print(f"\nRaw conversations loaded: {len(convs)}")
    return dict(convs)


def extract_windows(messages: list, window_size: int = 4) -> list:
    """
    Extract multi-turn windows of window_size messages (must be even).
    Slides by 1 (not 2) to maximise yield from real DM conversations.
    Windows must be strictly alternating user/assistant starting with user.
    """
    windows = []
    expected_roles = ["user", "assistant"] * (window_size // 2)

    for start in range(len(messages) - window_size + 1):
        window = messages[start : start + window_size]
        actual_roles = [m["role"] for m in window]
        if actual_roles != expected_roles:
            continue
        if any(is_media_only(m["content"]) for m in window):
            continue
        if any(
            m["role"] == "assistant" and len(m["content"]) > MAX_ASST_CHARS
            for m in window
        ):
            continue
        # Require at least one substantive assistant message (>5 chars)
        asst_contents = [m["content"] for m in window if m["role"] == "assistant"]
        if not any(len(c) > 5 for c in asst_contents):
            continue
        windows.append(window)
    return windows


def build_multiturn_pool(raw_convs: dict, target_mt: int) -> list:
    """
    Build multi-turn pool using sliding windows.
    Adaptive per-conversation cap proportional to conversation length.
    """
    all_windows = []
    valid_conv_count = 0
    skipped_short = 0
    skipped_no_windows = 0

    # Two-pass: first count valid convs, then set cap
    valid_convs = {}
    for cid, raw_msgs in raw_convs.items():
        merged = merge_consecutive_roles(raw_msgs)
        if len(merged) >= 4:
            valid_convs[cid] = merged

    if not valid_convs:
        print("  No valid conversations found!")
        return []

    # Adaptive cap: proportional to length, but bounded
    # aim to get target_mt total, distributing across valid convs
    base_cap = max(3, (target_mt // len(valid_convs)) + 2)

    for cid, merged in valid_convs.items():
        # Use both window sizes 4 and 6 for variety
        wins = extract_windows(merged, 4) + extract_windows(merged, 6)

        if not wins:
            skipped_no_windows += 1
            continue

        valid_conv_count += 1

        # Deduplicate by first-message content prefix
        seen = set()
        unique = []
        for w in wins:
            key = w[0]["content"][:40]
            if key not in seen:
                seen.add(key)
                unique.append(w)

        # Adaptive cap: longer convs contribute more (but still bounded)
        cap = min(base_cap, max(2, len(merged) // 4))
        # Allow longer convs to contribute proportionally more
        if len(merged) > 20:
            cap = min(cap * 2, base_cap + 4)

        random.shuffle(unique)
        for w in unique[:cap]:
            all_windows.append(w)

    print(f"\nMulti-turn pool: {len(all_windows)} windows from {valid_conv_count} conversations")
    print(f"  Skipped (no valid windows after filter): {skipped_no_windows}")
    return all_windows


# ─────────────────────────────────────────────────────────────────────────────
# Build final dataset
# ─────────────────────────────────────────────────────────────────────────────

def build_dataset(
    single_turn: list,
    multi_turn: list,
    system_variants: list,
    target_total: int,
) -> list:
    target_st = int(target_total * SINGLE_TURN_RATIO)
    target_mt = target_total - target_st

    rng = random.Random(RANDOM_SEED)
    rng.shuffle(single_turn)
    rng.shuffle(multi_turn)

    st_sample = single_turn[:target_st]
    mt_sample = multi_turn[:target_mt]

    actual_mt = len(mt_sample)
    if actual_mt < target_mt:
        print(f"\n⚠ Only {actual_mt} multi-turn available (target {target_mt})")
        extra = target_mt - actual_mt
        st_sample = st_sample + single_turn[target_st : target_st + extra]
        print(f"  Padding with {min(extra, len(single_turn) - target_st)} extra 1-turn records")

    # Build records with rotated system prompt (BUG-14)
    n_variants = len(system_variants)
    records = []
    for msgs in st_sample:
        variant_idx = rng.randint(0, n_variants - 1)
        records.append({
            "messages": [
                {"role": "system", "content": system_variants[variant_idx]},
                *msgs,
            ],
            "system_variant": variant_idx,
            "turn_type": "single",
        })
    for msgs in mt_sample:
        variant_idx = rng.randint(0, n_variants - 1)
        records.append({
            "messages": [
                {"role": "system", "content": system_variants[variant_idx]},
                *msgs,
            ],
            "system_variant": variant_idx,
            "turn_type": "multi",
        })

    rng.shuffle(records)

    # ── Token budget filter (Opción A: max_seq_len=8192) ────────────────────
    # Estimate tokens via chars / CHARS_PER_TOKEN. Remove records that would
    # exceed MAX_SEQ_LEN, preventing truncation silently killing long records.
    pre_filter = len(records)
    records = [
        r for r in records
        if sum(len(m["content"]) for m in r["messages"]) <= MAX_TOTAL_CHARS
    ]
    filtered_count = pre_filter - len(records)
    if filtered_count:
        print(f"\nToken filter: removed {filtered_count} records (>{MAX_SEQ_LEN} est. tokens)")

    total = len(records)
    st_count = sum(1 for r in records if r["turn_type"] == "single")
    mt_count = sum(1 for r in records if r["turn_type"] == "multi")

    print(f"\n=== SFT v4 dataset ===")
    print(f"Total records: {total}")
    print(f"Single-turn: {st_count} ({st_count/total*100:.1f}%)")
    print(f"Multi-turn: {mt_count} ({mt_count/total*100:.1f}%)")
    sv = Counter(r["system_variant"] for r in records)
    print(f"System variants: {dict(sv)}")

    return records


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_dataset(records: list) -> bool:
    ok = True
    print(f"\n=== Validation ===")

    # BUG-13
    violations = [
        r for r in records
        for m in r["messages"]
        if m["role"] == "assistant" and len(m["content"]) > MAX_ASST_CHARS
    ]
    if violations:
        print(f"❌ BUG-13 violations (asst >{MAX_ASST_CHARS} chars): {len(violations)}")
        ok = False
    else:
        print(f"✓ BUG-13: 0 violations (all asst ≤{MAX_ASST_CHARS} chars)")

    # Turn distribution
    turn_dist = Counter(
        len([m for m in r["messages"] if m["role"] != "system"]) // 2
        for r in records
    )
    print(f"Turn pair distribution: {dict(sorted(turn_dist.items()))}")

    # BUG-12: multi-turn ratio
    mt_count = sum(1 for r in records if r["turn_type"] == "multi")
    mt_ratio = mt_count / len(records) if records else 0
    if mt_ratio < 0.25:
        print(f"❌ BUG-12: multi-turn ratio {mt_ratio:.1%} < minimum 25%")
        ok = False
    else:
        print(f"✓ BUG-12: multi-turn ratio {mt_ratio:.1%}")

    # BUG-14: system rotation
    sv_count = len(set(r["system_variant"] for r in records))
    if sv_count < 2:
        print(f"❌ BUG-14: only {sv_count} system variant(s)")
        ok = False
    else:
        sv_dist = Counter(r["system_variant"] for r in records)
        print(f"✓ BUG-14: {sv_count} system variants — {dict(sv_dist)}")

    # Asst length stats
    asst_lens = [
        len(m["content"])
        for r in records
        for m in r["messages"]
        if m["role"] == "assistant"
    ]
    print(
        f"Asst length: min={min(asst_lens)}, max={max(asst_lens)}, "
        f"mean={statistics.mean(asst_lens):.1f}, median={statistics.median(asst_lens):.1f}"
    )

    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--target", type=int, default=TARGET_TOTAL)
    args = parser.parse_args()

    random.seed(RANDOM_SEED)

    eng = create_engine(os.environ["DATABASE_URL"])

    print("=== Step 1: Load system prompt variants ===")
    system_variants = load_system_variants(eng)

    print("\n=== Step 2: Load single-turn data (SFT v3) ===")
    single_turn = load_single_turn()

    print("\n=== Step 3: Load multi-turn data from DB ===")
    raw_convs = load_multiturn_raw(eng)
    target_mt = int(args.target * (1 - SINGLE_TURN_RATIO))
    multi_turn = build_multiturn_pool(raw_convs, target_mt)

    print("\n=== Step 4: Build dataset ===")
    records = build_dataset(single_turn, multi_turn, system_variants, args.target)

    all_ok = validate_dataset(records)
    if not all_ok:
        print("\n⚠ Validation warnings — check stats above.")

    if args.dry_run:
        print("\nDry run — not writing output.")
        return

    print(f"\n=== Step 5: Write {SFT_V4_PATH} ===")
    SFT_V4_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SFT_V4_PATH, "w") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    file_mb = SFT_V4_PATH.stat().st_size / 1024 / 1024
    print(f"✓ Written {len(records)} records → {SFT_V4_PATH} ({file_mb:.1f} MB)")


if __name__ == "__main__":
    main()
