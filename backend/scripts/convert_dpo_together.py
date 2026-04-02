"""
Convert DPO dataset from TRL format to Together AI format.

Input  (data/dpo/trl/dpo_iris.jsonl):
  {"prompt": "user: ...\nuser: ...\nassistant: ...", "chosen": "...", "rejected": "..."}

Output (data/dpo/trl/dpo_together_iris.jsonl):
  {
    "input": {"messages": [{"role": "system", ...}, {"role": "user", ...}, ...]},
    "preferred_output": [{"role": "assistant", "content": "..."}],
    "non_preferred_output": [{"role": "assistant", "content": "..."}]
  }

Usage:
    python3 scripts/convert_dpo_together.py
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

INPUT_PATH  = REPO_ROOT / "data" / "dpo" / "trl" / "dpo_iris.jsonl"
OUTPUT_PATH = REPO_ROOT / "data" / "dpo" / "trl" / "dpo_together_iris.jsonl"
DOC_D_PATH  = REPO_ROOT / "data" / "personality_extractions" / "iris_bertran_v2_distilled.md"

# ── Load system prompt (same as SFT) ──────────────────────────────────────
def load_system_prompt() -> str:
    if DOC_D_PATH.exists():
        text = DOC_D_PATH.read_text(encoding="utf-8")
        m = re.search(r"```\n(.*?)```", text, re.DOTALL)
        if m:
            prompt = m.group(1).strip()
            if len(prompt) > 600:
                prompt = prompt[:600].rsplit("\n", 1)[0].strip()
            return prompt
    return (
        "Eres Iris Bertran. Instructora de fitness/danza en Barcelona. "
        "Respondes DMs como lo harías tú: corto, directo, con emojis, "
        "code-switching catalán/castellano natural. NUNCA preguntes '¿en qué puedo ayudarte?'."
    )


SYSTEM_PROMPT = load_system_prompt()


# ── Parse prompt string → messages list ───────────────────────────────────
def parse_prompt(prompt_str: str) -> list[dict]:
    """
    Convert the multi-line prompt string into an OpenAI-style messages list.

    Input:  "user: msg1\nuser: msg2\nassistant: reply\nuser: msg3"
    Output: [
        {"role": "user",      "content": "msg1\nmsg2"},
        {"role": "assistant", "content": "reply"},
        {"role": "user",      "content": "msg3"},
    ]
    Consecutive same-role lines are merged with \n.
    """
    lines = prompt_str.strip().split("\n")
    messages = []
    current_role = None
    current_parts = []

    for line in lines:
        line = line.strip()
        if line.startswith("user: "):
            content = line[len("user: "):]
            if current_role == "user":
                current_parts.append(content)
            else:
                if current_role is not None and current_parts:
                    messages.append({"role": current_role, "content": "\n".join(current_parts)})
                current_role = "user"
                current_parts = [content]
        elif line.startswith("assistant: "):
            content = line[len("assistant: "):]
            if current_role == "assistant":
                current_parts.append(content)
            else:
                if current_role is not None and current_parts:
                    messages.append({"role": current_role, "content": "\n".join(current_parts)})
                current_role = "assistant"
                current_parts = [content]
        elif line:
            # Unknown prefix — append to current role if active
            if current_role and current_parts:
                current_parts.append(line)

    if current_role is not None and current_parts:
        messages.append({"role": current_role, "content": "\n".join(current_parts)})

    return messages


# ── Validation ─────────────────────────────────────────────────────────────
BAD_CHOSEN_PATTERNS = [
    "en qué puedo ayudarte", "cuéntame qué te trae",
    "¡hola! gracias por tu mensaje", "como asistente",
    "lo siento, no", "sorry", "```",
]


def is_bad_chosen(text: str) -> bool:
    """Skip pairs where 'chosen' looks like a generic bot response, not Iris."""
    t = text.lower()
    return any(p in t for p in BAD_CHOSEN_PATTERNS)


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    if not INPUT_PATH.exists():
        print(f"ERROR: Input not found: {INPUT_PATH}")
        sys.exit(1)

    lines_in = INPUT_PATH.read_text(encoding="utf-8").splitlines()
    print(f"Input lines: {len(lines_in)}")
    print(f"System prompt: {len(SYSTEM_PROMPT)} chars")

    converted = []
    skipped_bad_chosen = 0
    skipped_bad_json = 0
    skipped_no_user = 0

    for i, line in enumerate(lines_in):
        line = line.strip()
        if not line:
            continue

        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            skipped_bad_json += 1
            print(f"  Line {i+1}: JSON error — {e}")
            continue

        prompt   = obj.get("prompt", "")
        chosen   = obj.get("chosen", "").strip()
        rejected = obj.get("rejected", "").strip()

        if not chosen or not rejected:
            skipped_bad_json += 1
            continue

        if is_bad_chosen(chosen):
            skipped_bad_chosen += 1
            continue

        # Parse conversation history
        history = parse_prompt(prompt)

        # The last message must be from the user (it's what the model responds to)
        # If history ends with assistant, pop it (it will be chosen/rejected instead)
        while history and history[-1]["role"] == "assistant":
            history.pop()

        if not history or history[-1]["role"] != "user":
            skipped_no_user += 1
            continue

        # Build input messages: system + history
        input_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

        together_obj = {
            "input": {
                "messages": input_messages
            },
            "preferred_output": [
                {"role": "assistant", "content": chosen}
            ],
            "non_preferred_output": [
                {"role": "assistant", "content": rejected}
            ],
        }

        # Validate the output JSON serializes correctly
        try:
            json.dumps(together_obj, ensure_ascii=False)
        except Exception as e:
            skipped_bad_json += 1
            print(f"  Line {i+1}: serialization error — {e}")
            continue

        converted.append(together_obj)

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for obj in converted:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # Verify every line is valid JSON
    errors = 0
    with open(OUTPUT_PATH, encoding="utf-8") as f:
        for j, line in enumerate(f):
            try:
                json.loads(line)
            except Exception:
                errors += 1
                print(f"  Validation error at line {j+1}")

    print()
    print("=" * 50)
    print("DPO CONVERSION — Together AI format")
    print("=" * 50)
    print(f"  Input lines:         {len(lines_in)}")
    print(f"  Converted:           {len(converted)}")
    print(f"  Skipped (bad JSON):  {skipped_bad_json}")
    print(f"  Skipped (bad chosen):{skipped_bad_chosen}")
    print(f"  Skipped (no user):   {skipped_no_user}")
    print(f"  JSON validation:     {'✓ all valid' if errors == 0 else f'✗ {errors} errors'}")
    print(f"  Output: {OUTPUT_PATH}")
    print()
    print("Ejemplo (primera línea):")
    print("-" * 50)
    example = converted[0] if converted else {}
    if example:
        msgs = example["input"]["messages"]
        last_user = next((m for m in reversed(msgs) if m["role"] == "user"), {})
        print(f"  user:               {last_user.get('content','')[:80]}")
        print(f"  preferred_output:   {example['preferred_output'][0]['content'][:80]}")
        print(f"  non_preferred:      {example['non_preferred_output'][0]['content'][:80]}")
    print("=" * 50)


if __name__ == "__main__":
    main()
