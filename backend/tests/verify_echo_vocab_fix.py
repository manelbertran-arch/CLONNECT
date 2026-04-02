"""Quick verification: anti-echo + vocabulary rules in new Doc D.

Runs 10 cases from the stratified test set (skipping sticker/audio/media),
prints each response, flags echoes (Jaccard > 0.70) and potential invented words.

Usage:
    railway run python3 tests/verify_echo_vocab_fix.py --creator iris_bertran
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DEEPINFRA_TIMEOUT", "30")
os.environ.setdefault("DEEPINFRA_CB_THRESHOLD", "999")

# Known invented vocabulary patterns flagged in previous runs
_INVENTED_PATTERNS = [
    r"ets de feri",
    r"super flor",
    r"quin\s+\w+\s+tan\s+\w+",  # nonsensical Catalan constructs
]


def jaccard(a: str, b: str) -> float:
    wa = set(re.sub(r'[^\w\s]', '', a.lower()).split())
    wb = set(re.sub(r'[^\w\s]', '', b.lower()).split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def flag_invented(text: str) -> list[str]:
    flags = []
    for pat in _INVENTED_PATTERNS:
        if re.search(pat, text, re.I):
            flags.append(pat)
    return flags


async def call_deepinfra(system_prompt: str, messages: list, model: str) -> str:
    from core.providers.deepinfra_provider import call_deepinfra as _call
    full_messages = [{"role": "system", "content": system_prompt}] + list(messages)
    result = await _call(
        full_messages,
        max_tokens=120,
        temperature=0.7,
        model=model,
    )
    if not result:
        return ""
    return result.get("content", "").strip()


def load_doc_d(creator_id: str) -> str:
    from core.dm.compressed_doc_d import build_compressed_doc_d
    return build_compressed_doc_d(creator_id)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--creator", default="iris_bertran")
    parser.add_argument("--model", default="Qwen/Qwen3-14B")
    parser.add_argument("--n", type=int, default=10)
    args = parser.parse_args()

    creator_id = args.creator
    model = args.model

    # Load test set
    test_path = REPO_ROOT / "tests" / "cpe_data" / creator_id / "test_set_v2_stratified.json"
    with open(test_path) as f:
        data = json.load(f)
    convs = data["conversations"]

    # Filter out media/sticker/audio-only messages (non-text leads)
    text_convs = [
        c for c in convs
        if not c["test_input"].startswith("[")
        and len(c["test_input"].strip()) > 0
    ]

    # Pick n cases
    selected = text_convs[: args.n]

    # Build system prompt (new Doc D with anti-echo + vocab rules)
    print("Building Doc D (new rules)...")
    doc_d = load_doc_d(creator_id)
    # Show the REGLAS section so we can verify new rules are present
    rules_start = doc_d.find("REGLAS")
    if rules_start >= 0:
        print("\n--- REGLAS SECTION ---")
        print(doc_d[rules_start:rules_start + 500])
        print("--- END REGLAS ---\n")

    print(f"\nRunning {len(selected)} cases | model={model}")
    print("=" * 80)

    echo_count = 0
    invented_count = 0

    for i, conv in enumerate(selected, 1):
        lead_msg = conv["test_input"]
        gt = conv["ground_truth"]
        history = conv.get("turns", [])
        cat = conv.get("category", "?")
        lang = conv.get("language", "?")

        # Build messages list (history + current)
        messages = list(history) + [{"role": "user", "content": lead_msg}]

        t0 = time.monotonic()
        bot_resp = await call_deepinfra(doc_d, messages, model)
        elapsed = int((time.monotonic() - t0) * 1000)

        # Check echo
        j = jaccard(lead_msg, bot_resp)
        is_echo = j > 0.70 and len(lead_msg.split()) >= 3

        # Check invented vocabulary
        inv_flags = flag_invented(bot_resp)

        status = "✓"
        if is_echo:
            status = "🔁 ECHO"
            echo_count += 1
        if inv_flags:
            status += f" 🔴 INVENTED({inv_flags})"
            invented_count += 1

        print(f"[{i:02d}/{len(selected)}] {cat}/{lang}  {status}  {elapsed}ms")
        print(f"  Lead: {lead_msg[:80]!r}")
        print(f"  Bot:  {bot_resp[:120]!r}")
        print(f"  GT:   {gt[:80]!r}")
        if is_echo:
            print(f"  ⚠️  Jaccard={j:.2f} (ECHO — would be caught by A3 postprocessor)")
        print()

        await asyncio.sleep(0.8)

    print("=" * 80)
    print(f"ECHO responses : {echo_count}/{len(selected)}")
    print(f"Invented vocab : {invented_count}/{len(selected)}")
    print()
    print("Note: echoes shown here would be caught by A3 postprocessor in production.")


if __name__ == "__main__":
    asyncio.run(main())
