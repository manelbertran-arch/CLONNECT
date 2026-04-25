#!/usr/bin/env python3
"""Sprint 7 — Combine MT + Q&A + Adversarial → dedup → final dataset.

Pipeline (v2 — post quality gate fixes):
  1. Load inputs
  2. Force Doc D 100% as system prompt
  3. Fix role alternation (re-merge consecutive same-role bursts)
  4. Filter error strings  (B3)
  5. Filter solo-artifact  (B4)
  6. Mask PII in assistant (B6)
  7. Filter CCEE eval overlap (B7)
  8. Exact dedup by user+assistant content hash

Decisions:
  B1 re-merge bursts  — applies to multi_turn source only
  B2 Q&A gate count  — ignored (gate bug, source field is correct)
  B3 filter 14       — error string records
  B4 filter 6        — solo-artifact assistant responses
  B5 inline artifacts — ACCEPTED (representan estilo real Iris)
  B6 mask PII        — @handles, phones, emails masked (no filter)
  B7 filter 9        — CCEE eval overlap records
"""

import json
import hashlib
import re
from collections import Counter
from hashlib import md5 as _md5
from pathlib import Path

# ─── Inputs / outputs ─────────────────────────────────────────────────────
INPUTS = [
    ("data/dpo/trl/sprint7/sft_mt.jsonl",                    "multi_turn"),
    ("data/dpo/trl/sprint7/sft_persona_qa_b3nbu4vss.jsonl",  "persona_qa"),
    ("data/dpo/trl/sprint7/sft_adversarial.jsonl",            "adversarial"),
]
OUTPUT     = Path("data/dpo/trl/sprint7/sft_sprint7.jsonl")
DOC_D_PATH = Path("data/personality_extractions/iris_bertran/doc_d_bot_configuration.md")
EVAL_PATHS = [
    Path("data/eval/sft_eval.jsonl"),
    Path("data/eval/ccee_real.jsonl"),
    Path("data/dpo/trl/sft_eval.jsonl"),
]

# ─── Exact patterns from 09_dataset_quality_gate.py ───────────────────────
ERROR_STRINGS = [
    "lo siento, hubo un error",
    "sorry, i",
    "sorry i couldn",
    "error occurred",
    "traceback",
    "exception:",
    "hubuntoo un error",
    "se produjo un error",
]

ARTIFACT_ONLY_PATTERNS = [
    r"^\s*\[sticker\]\s*$",
    r"^\s*\[photo\]\s*$",
    r"^\s*\[audio\]\s*$",
    r"^\s*\[video\]\s*$",
    r"^\s*\[contact\]\s*$",
    r"^\s*\[🎤[^\]]*\]\s*$",
    r"^\s*\[🎬[^\]]*\]\s*$",
    r"^\s*sent an attachment\s*$",
]

PII_PHONE  = re.compile(r"\b[67]\d{8}\b|\+34\s*\d{9}|\b\d{10,11}\b")
PII_EMAIL  = re.compile(r"[\w.\-+]+@[\w.\-]+\.\w{2,}")
PII_HANDLE = re.compile(r"@[a-zA-Z0-9_.]{3,}")
PII_WHITELIST_HANDLES = {"@iris_bertran", "@iraais5"}


# ─── Helpers ──────────────────────────────────────────────────────────────

def load_doc_d() -> str:
    return DOC_D_PATH.read_text(encoding="utf-8")


def hash_messages(messages: list) -> str:
    """Hash by user+assistant content (ignore system) for dedup."""
    content = ""
    for m in messages:
        if m["role"] in ("user", "assistant"):
            content += f"{m['role']}:{m['content']}\n"
    return hashlib.sha256(content.encode()).hexdigest()


def md5_user(messages: list) -> str:
    """MD5 of joined user content — mirrors gate's get_user_content + md5."""
    parts = [m["content"] for m in messages if m.get("role") == "user"]
    combined = " ".join(parts)
    return _md5(combined.encode()).hexdigest() if combined else ""


def has_error_string(rec: dict) -> bool:
    for m in rec["messages"]:
        if m["role"] == "system":
            continue
        low = m["content"].lower()
        if any(e in low for e in ERROR_STRINGS):
            return True
    return False


def is_solo_artifact(rec: dict) -> bool:
    """Mirrors gate's get_assistant_content: join ALL assistant turns, then check."""
    parts = [m.get("content", "") for m in rec["messages"] if m.get("role") == "assistant"]
    combined = " ".join(parts)
    return any(re.match(p, combined.strip(), re.IGNORECASE) for p in ARTIFACT_ONLY_PATTERNS)


def mask_pii(rec: dict) -> dict:
    """Mask PII in assistant messages, preserving whitelisted handles."""
    for m in rec["messages"]:
        if m["role"] != "assistant":
            continue
        content = m["content"]

        # Protect whitelisted handles
        protected: dict[str, str] = {}
        for handle in PII_WHITELIST_HANDLES:
            if handle.lower() in content.lower():
                ph = f"__WL{len(protected)}__"
                content = re.sub(re.escape(handle), ph, content, flags=re.IGNORECASE)
                protected[ph] = handle

        content = PII_PHONE.sub("[PHONE]", content)
        content = PII_EMAIL.sub("[EMAIL]", content)

        def _mask_handle(match: re.Match) -> str:
            h = match.group(0).lower()
            if h in PII_WHITELIST_HANDLES:
                return match.group(0)
            return "[HANDLE]"

        content = PII_HANDLE.sub(_mask_handle, content)

        for ph, original in protected.items():
            content = content.replace(ph, original)

        m["content"] = content
    return rec


def fix_role_alternation(rec: dict) -> dict:
    """Fix two issues:
    1. Re-merge consecutive same-role turns (burst merge).
    2. Drop leading assistant turns so conversation starts with user.
    """
    msgs = rec["messages"]
    if not msgs:
        return rec

    # Step A: merge consecutive same-role turns (skip system at index 0)
    fixed = [msgs[0]]            # keep system
    for m in msgs[1:]:
        if fixed and fixed[-1]["role"] == m["role"]:
            fixed[-1] = {
                "role": m["role"],
                "content": fixed[-1]["content"].rstrip() + "\n" + m["content"].lstrip(),
            }
        else:
            fixed.append(dict(m))

    # Step B: drop leading assistant turns until first user
    sys_msg = fixed[0]
    non_sys = fixed[1:]
    while non_sys and non_sys[0]["role"] != "user":
        non_sys.pop(0)

    rec["messages"] = [sys_msg] + non_sys
    return rec


def has_alternation_violation(messages: list) -> bool:
    roles = [m["role"] for m in messages[1:]]   # skip system
    return any(roles[i] == roles[i + 1] for i in range(len(roles) - 1))


def load_eval_hashes() -> set:
    for p in EVAL_PATHS:
        if p.exists():
            hashes: set = set()
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        user_text = (
                            obj.get("user") or
                            obj.get("question") or
                            obj.get("prompt") or
                            next(
                                (m["content"] for m in obj.get("messages", [])
                                 if m.get("role") == "user"),
                                None,
                            ) or ""
                        )
                        if user_text:
                            hashes.add(_md5(user_text.encode()).hexdigest())
                    except json.JSONDecodeError:
                        pass
            print(f"  Eval hashes loaded: {len(hashes)} from {p}")
            return hashes
    print("  WARNING: no eval set found — G6.1 overlap not filtered")
    return set()


# ─── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    doc_d = load_doc_d()
    print(f"Doc D: {len(doc_d)} chars\n")

    # ── 1. Load ───────────────────────────────────────────────────────────
    all_records: list[dict] = []
    source_counts: Counter = Counter()
    for path, source in INPUTS:
        p = Path(path)
        if not p.exists():
            print(f"ERROR: {path} missing — aborting"); raise SystemExit(1)
        n = 0
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                rec["source"] = source
                all_records.append(rec)
                source_counts[source] += 1
                n += 1
        print(f"  Loaded {n:5d} ← {path}")

    print(f"\n[0] Loaded:         {len(all_records):5d}  {dict(source_counts)}")

    # ── 2. Force Doc D 100% ───────────────────────────────────────────────
    replaced = added = 0
    for rec in all_records:
        msgs = rec.get("messages", [])
        if not msgs:
            continue
        if msgs[0].get("role") == "system":
            if msgs[0]["content"] != doc_d:
                msgs[0]["content"] = doc_d; replaced += 1
        else:
            msgs.insert(0, {"role": "system", "content": doc_d}); added += 1
    print(f"[1] Doc D enforce:  {len(all_records):5d}  (replaced={replaced}, added={added})")

    # ── 3. Fix role alternation (B1) ──────────────────────────────────────
    for rec in all_records:
        fix_role_alternation(rec)
    violations_after = sum(1 for r in all_records if has_alternation_violation(r["messages"]))
    print(f"[2] Role fix done:  {len(all_records):5d}  (violations remaining={violations_after})")

    # ── 3b. Drop records left empty after role fix (no user OR no assistant) ──
    pre = len(all_records)
    def has_user_and_assistant(rec: dict) -> bool:
        roles = {m["role"] for m in rec["messages"]}
        return "user" in roles and "assistant" in roles
    all_records = [r for r in all_records if has_user_and_assistant(r)]
    print(f"[2b] Empty post-fix:{len(all_records):5d}  (filtered={pre - len(all_records)})")

    # ── 4. Filter error strings (B3) ─────────────────────────────────────
    pre = len(all_records)
    all_records = [r for r in all_records if not has_error_string(r)]
    print(f"[3] Error strings:  {len(all_records):5d}  (filtered={pre - len(all_records)})")

    # ── 5. Filter solo-artifact (B4) ─────────────────────────────────────
    pre = len(all_records)
    all_records = [r for r in all_records if not is_solo_artifact(r)]
    print(f"[4] Solo-artifact:  {len(all_records):5d}  (filtered={pre - len(all_records)})")

    # ── 6. Mask PII (B6) ─────────────────────────────────────────────────
    for rec in all_records:
        mask_pii(rec)
    print(f"[5] PII masked:     {len(all_records):5d}  (in-place)")

    # ── 7. Filter CCEE eval overlap (B7) ─────────────────────────────────
    eval_hashes = load_eval_hashes()
    if eval_hashes:
        pre = len(all_records)
        all_records = [r for r in all_records
                       if md5_user(r["messages"]) not in eval_hashes]
        print(f"[6] Eval overlap:   {len(all_records):5d}  (filtered={pre - len(all_records)})")
    else:
        print(f"[6] Eval overlap:   {len(all_records):5d}  (skipped — no eval file)")

    # ── 8. Exact dedup ────────────────────────────────────────────────────
    seen: set = set()
    unique: list = []
    dups = 0
    for rec in all_records:
        h = hash_messages(rec["messages"])
        if h in seen:
            dups += 1
        else:
            seen.add(h); unique.append(rec)
    print(f"[7] Dedup:          {len(unique):5d}  (removed={dups})")

    # ── Write ─────────────────────────────────────────────────────────────
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as f:
        for rec in unique:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    final_src = Counter(r["source"] for r in unique)
    bad_sys = sum(
        1 for r in unique
        if r["messages"][0]["role"] != "system" or r["messages"][0]["content"] != doc_d
    )
    bad_alt = sum(1 for r in unique if has_alternation_violation(r["messages"]))

    print(f"\n{'='*55}")
    print(f"FINAL:              {len(unique):5d}  records")
    print(f"Sources:            {dict(final_src)}")
    print(f"Bad system prompt:  {bad_sys}   (must be 0)")
    print(f"Role violations:    {bad_alt}   (must be 0)")
    print(f"Wrote → {OUTPUT}")


if __name__ == "__main__":
    main()
