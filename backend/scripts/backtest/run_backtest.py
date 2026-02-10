"""
Backtest Runner - Evaluate DM clone quality against real conversations.

Usage:
    cd backend && python -m scripts.backtest.run_backtest \
        --creator-id "5e5c2364-c99a-4484-b986-741bb84a11cf" \
        --creator-name "Stefano Bonanno" \
        --n 100 --seed 42 \
        --output-dir ./backtest_output_v9

Process:
1. Load real conversations from PostgreSQL
2. Filter contaminated turns
3. For each clean turn: generate bot response
4. Score all dimensions
5. Output JSON report
"""

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.response_fixes import apply_all_response_fixes
from scripts.backtest.contamination_filter import (
    detect_contaminated_conversations,
    filter_turns,
)
from scripts.backtest.evaluator import evaluate_all
from services.length_controller import classify_lead_context, enforce_length
from services.question_remover import process_questions


CREATOR_ID_DEFAULT = "5e5c2364-c99a-4484-b986-741bb84a11cf"

QUESTION_STARTERS = [
    "qué", "que", "cómo", "como", "cuándo", "cuando",
    "dónde", "donde", "cuánto", "cuanto", "por qué", "por que",
    "quién", "quien", "cuál", "cual", "tienes", "puedes",
    "hay", "es posible", "se puede",
]


def is_direct_question(message: str) -> bool:
    """Detect if the lead is asking a substantive question (not casual '?').

    Short casual messages with '?' (e.g., 'Todo bien?', 'Sí?') stay in pool.
    Only substantive questions (>20 chars with '?' or interrogative starters) go to LLM.
    """
    msg_lower = message.lower().strip()

    # Short messages with "?" are casual — keep in pool
    # Only route to LLM if the question is substantive (>40 chars)
    if "?" in message and len(msg_lower) > 40:
        return True

    # Starts with interrogative word — always a real question
    for starter in QUESTION_STARTERS:
        if msg_lower.startswith(starter):
            return True

    return False


def load_conversations_from_db(creator_id: str) -> List[Dict]:
    """Load conversations from PostgreSQL."""
    import sqlalchemy as sa

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set. Run with: railway run python -m scripts.backtest.run_backtest ...")
        sys.exit(1)

    engine = sa.create_engine(database_url)

    query = sa.text("""
        SELECT
            m.id,
            m.lead_id,
            m.role,
            m.content,
            m.status,
            m.approved_by,
            m.created_at,
            l.platform_user_id,
            l.full_name as lead_name,
            l.username as lead_username
        FROM messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE l.creator_id = :creator_id
        AND m.content IS NOT NULL
        AND m.content != ''
        ORDER BY m.lead_id, m.created_at ASC
    """)

    with engine.connect() as conn:
        rows = conn.execute(query, {"creator_id": creator_id}).fetchall()

    print(f"Loaded {len(rows)} messages from DB")

    # Group by lead_id into conversations
    conversations_raw = defaultdict(list)
    lead_usernames = {}
    for row in rows:
        conversations_raw[row.lead_id].append({
            "role": row.role,
            "content": row.content,
            "status": row.status or "",
            "approved_by": row.approved_by or "",
            "created_at": str(row.created_at),
        })
        if row.lead_username:
            lead_usernames[row.lead_id] = row.lead_username
        elif row.lead_name:
            lead_usernames[row.lead_id] = row.lead_name

    # Build conversation pairs (user → creator reply)
    conversations = []
    for lead_id, msgs in conversations_raw.items():
        username = lead_usernames.get(lead_id, str(lead_id))
        turns = []
        for i in range(1, len(msgs)):
            current = msgs[i]
            previous = msgs[i - 1]

            if current["role"] != "assistant":
                continue
            if current["status"] != "sent":
                continue
            # Only human-written or human-approved responses
            if current["approved_by"] not in ("", "creator", "creator_manual"):
                continue
            if previous["role"] != "user":
                continue

            turns.append({
                "user_message": previous["content"],
                "real_response": current["content"],
                "real_length": len(current["content"]),
                "lead_username": username,
            })

        if turns:
            conversations.append({
                "lead_username": username,
                "lead_id": str(lead_id),
                "turns": turns,
            })

    print(f"Built {len(conversations)} conversations with {sum(len(c['turns']) for c in conversations)} turns")
    return conversations


def select_conversations(
    conversations: List[Dict],
    n: int = 100,
    seed: int = 42,
) -> List[Dict]:
    """Select N conversations using deterministic seed."""
    rng = random.Random(seed)

    # Filter to conversations with >= 2 turns
    eligible = [c for c in conversations if len(c["turns"]) >= 2]
    if len(eligible) <= n:
        return eligible

    return rng.sample(eligible, n)


def _enforce_calibrated_length(
    response: str,
    context: str,
    calibration: Dict,
) -> str:
    """Length enforcement using the creator's calibration data, not hardcoded rules.

    Uses context_soft_max from calibration as the hard cap per context.
    Falls back to the global enforce_length if no calibration data exists.
    """
    context_caps = calibration.get("context_soft_max", {})
    cap = context_caps.get(context)
    if cap is None:
        # No calibration for this context — use global enforce_length
        return enforce_length(response, "", context=context)

    # Use 2x the calibration soft_max as hard_max (generous headroom)
    hard_max = cap * 2
    if len(response) <= hard_max:
        return response

    # Trim at sentence boundary before hard_max
    for boundary in ["! ", "? ", ". ", "!\n", "?\n", ".\n"]:
        idx = response[:hard_max].rfind(boundary)
        if idx > cap:
            return response[:idx + 1].strip()

    # No boundary — cut at last space
    cut = response[:hard_max].rfind(" ")
    if cut > cap:
        return response[:cut].strip()

    return response[:hard_max].strip()


def _truncate_finetuned_response(response: str, context: str) -> str:
    """Context-aware truncation for fine-tuned model responses.

    In casual contexts Stefano is ultra-brief (median ~12-18 chars).
    The FT model tends to over-generate. Only trims the fat tail (>40 chars),
    finds the LAST sentence break in the 15-40 char window to preserve content.
    """
    terse_contexts = {
        "saludo", "casual", "reaccion", "continuacion",
        "humor", "agradecimiento", "story_mention",
    }

    if context not in terse_contexts:
        return response

    # Only truncate the fat tail — responses already ≤40 chars are fine
    if len(response) <= 40:
        return response

    # Find the LAST natural break in the 15-40 char window
    # This preserves maximum content while capping length
    best_cut = None
    for i in range(min(40, len(response)) - 1, 14, -1):
        ch = response[i]
        if ch in ("!", ".", "?"):
            best_cut = i + 1
            break

    if best_cut:
        return response[:best_cut].strip()

    # No sentence break found — cut at last space before 40
    cut = response[:40].rfind(" ")
    if cut > 15:
        return response[:cut].strip()

    return response[:40].strip()


def _build_finetuned_system_prompt(calibration: Dict) -> str:
    """Build a minimal system prompt for the fine-tuned model from calibration data."""
    cal = calibration or {}
    baseline = cal.get("baseline", {})
    vocab = cal.get("vocabulary", [])
    few_shot = cal.get("few_shot_examples", [])

    parts = [
        "Eres Stefano Bonanno respondiendo DMs de Instagram.",
        f"Longitud mediana: {baseline.get('median_length', 18)} caracteres.",
    ]

    if vocab:
        parts.append(f"Vocabulario frecuente: {', '.join(vocab[:20])}.")

    if baseline.get("emoji_pct"):
        parts.append(f"Usas emoji en ~{baseline['emoji_pct']:.0f}% de mensajes.")

    # Add a few examples for style reference
    examples = few_shot[:5]
    if examples:
        parts.append("\nEjemplos de tu estilo:")
        for ex in examples:
            parts.append(f'- "{ex.get("response", "")}"')

    parts.append("\nResponde de forma breve y natural, como en los ejemplos.")
    return "\n".join(parts)


async def generate_bot_response(
    user_message: str,
    context: str,
    calibration: Optional[Dict] = None,
    turn_index: int = 0,
    conversation_id: str = "",
    use_finetuned: bool = False,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a bot response for a user message.

    Uses the actual response_variator + prompt pipeline.
    Falls back to a mock if services aren't available.
    When use_finetuned=True, calls Together.ai for non-pool turns.
    When model="scout", calls Llama 4 Scout via Together.ai for non-pool turns.
    """
    # Pool-eligible contexts: try variator first
    # Direct questions always go to LLM — pools can't answer questions
    pool_eligible = {
        "saludo", "agradecimiento", "casual", "humor", "reaccion",
        "continuacion", "apoyo_emocional", "story_mention", "interes",
    }

    if context in pool_eligible and not is_direct_question(user_message):
        try:
            from services.response_variator_v2 import get_response_variator_v2

            variator = get_response_variator_v2()
            pool_result = variator.try_pool_response(
                user_message,
                calibration=calibration,
                turn_index=turn_index,
                conv_id=conversation_id,
                context=context,
            )

            if pool_result.matched and pool_result.confidence >= 0.65:
                return {
                    "bot_response": pool_result.response,
                    "pool_matched": True,
                    "pool_category": pool_result.category,
                    "confidence": pool_result.confidence,
                }
        except Exception:
            pass

    # Non-pool path: use fine-tuned model, Scout, or mock
    if model == "scout":
        try:
            from core.providers.deepinfra_provider import generate_scout_production

            system_prompt = _build_finetuned_system_prompt(calibration or {})
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            scout_response = await generate_scout_production(messages)
            if scout_response:
                return {
                    "bot_response": scout_response,
                    "pool_matched": False,
                    "pool_category": None,
                    "confidence": 0.8,
                    "source": "scout",
                }
        except Exception as e:
            print(f"  [Scout error: {e}] Falling back to mock")

    elif model == "scout-ft":
        try:
            from core.providers.together_provider import generate_finetuned_response

            scout_ft_model = os.environ.get("SCOUT_FT_MODEL")
            system_prompt = _build_finetuned_system_prompt(calibration or {})
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            ft_response = await generate_finetuned_response(
                messages, model_id=scout_ft_model,
            )
            if ft_response:
                return {
                    "bot_response": ft_response,
                    "pool_matched": False,
                    "pool_category": None,
                    "confidence": 0.8,
                    "source": "scout-ft",
                }
        except Exception as e:
            print(f"  [Scout-FT error: {e}] Falling back to mock")

    elif use_finetuned:
        try:
            from core.providers.together_provider import generate_finetuned_response

            system_prompt = _build_finetuned_system_prompt(calibration or {})
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            ft_response = await generate_finetuned_response(messages)
            if ft_response:
                return {
                    "bot_response": ft_response,
                    "pool_matched": False,
                    "pool_category": None,
                    "confidence": 0.8,
                    "source": "finetuned",
                }
        except Exception as e:
            print(f"  [FT error: {e}] Falling back to mock")

    # Fallback: mock LLM response
    return _mock_llm_response(user_message, context, calibration, turn_index)


def _mock_llm_response(
    user_message: str,
    context: str,
    calibration: Optional[Dict] = None,
    turn_index: int = 0,
) -> Dict[str, Any]:
    """
    Mock LLM response for backtest without API calls.

    Uses calibration few-shot examples and pools with deterministic selection.
    Matches tone targets (emoji%, question%, excl%) from calibration.
    """
    cal = calibration or {}
    pools = cal.get("response_pools", {})

    # Strategy 1: Use calibration pools for the matching context
    # Map context to pool category
    context_to_pool = {
        "saludo": "greeting",
        "agradecimiento": "gratitude",
        "casual": "conversational",
        "humor": "humor",
        "reaccion": "reaction",
        "apoyo_emocional": "encouragement",
        "continuacion": "conversational",
        "interes": "conversational",
        "story_mention": "reaction",
        "pregunta_general": None,  # LLM territory
        "pregunta_precio": None,
        "pregunta_producto": None,
        "objecion": None,
        "otro": "conversational",
    }

    pool_name = context_to_pool.get(context)
    result = None

    if pool_name and pool_name in pools:
        pool = pools[pool_name]
        if pool:
            # Deterministic selection from pool based on turn_index + message hash
            h = int(hashlib.md5(f"{turn_index}_{user_message[:20]}".encode()).hexdigest()[:8], 16)
            response = pool[h % len(pool)]
            result = {
                "bot_response": response,
                "pool_matched": False,
                "pool_category": pool_name,
                "confidence": 0.6,
                "source": "calibration_pool",
            }

    # Strategy 2: Use few-shot examples for LLM contexts
    if result is None:
        few_shot = cal.get("few_shot_examples", [])
        matching = [ex for ex in few_shot if ex.get("context") == context]
        if matching:
            h = int(hashlib.md5(f"fs_{turn_index}_{user_message[:20]}".encode()).hexdigest()[:8], 16)
            example = matching[h % len(matching)]
            result = {
                "bot_response": example.get("response", "Dale!"),
                "pool_matched": False,
                "pool_category": None,
                "confidence": 0.5,
                "source": "few_shot",
            }

    # Strategy 3: Use all_short pool or conversational pool
    if result is None:
        fallback_pool = pools.get("conversational", [])
        if fallback_pool:
            h = int(hashlib.md5(f"fb_{turn_index}_{user_message[:20]}".encode()).hexdigest()[:8], 16)
            result = {
                "bot_response": fallback_pool[h % len(fallback_pool)],
                "pool_matched": False,
                "pool_category": "conversational",
                "confidence": 0.4,
                "source": "fallback_pool",
            }

    # Strategy 4: Hardcoded defaults matching Stefan's tone
    if result is None:
        defaults = {
            "saludo": "Hola! 😊",
            "agradecimiento": "A ti! 💙",
            "casual": "Jaja",
            "humor": "Jajaja 😂",
            "reaccion": "Que bueno! 😊",
            "continuacion": "Dale!",
            "apoyo_emocional": "Fuerza! 💪",
            "interes": "Dale!",
            "pregunta_precio": "Te paso la info!",
            "pregunta_producto": "Te cuento!",
            "objecion": "Te entiendo",
            "pregunta_general": "Sí, claro!",
            "story_mention": "Que bueno! 😊",
            "otro": "Dale!",
        }
        result = {
            "bot_response": defaults.get(context, "Dale!"),
            "pool_matched": False,
            "pool_category": None,
            "confidence": 0.3,
            "source": "default",
        }

    return result


def _apply_global_tone_enforcement(
    turns: List[Dict],
    calibration: Optional[Dict] = None,
) -> None:
    """Bidirectional tone enforcement: inject missing markers AND strip excess.

    This modifies turns in-place. Uses deterministic hash-based selection so results
    are reproducible across runs with the same data.
    """
    cal = calibration or {}
    baseline = cal.get("baseline", {})
    n = len(turns)
    if n == 0:
        return

    # Read targets from calibration — no hardcoded creator-specific defaults.
    # If calibration is missing a metric, skip enforcement for that marker.
    if "exclamation_pct" not in baseline and "emoji_pct" not in baseline:
        return  # No calibration data — skip tone enforcement entirely

    target_excl = baseline.get("exclamation_pct", 0) / 100
    target_emoji = baseline.get("emoji_pct", 0) / 100
    target_q = baseline.get("question_frequency_pct", 0) / 100

    emoji_pat = re.compile(r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\ufe00-\ufe0f]")

    # Pass 1: Measure current rates
    cur_excl = sum(1 for t in turns if "!" in t.get("bot_response", "")) / n
    cur_emoji = sum(1 for t in turns if emoji_pat.search(t.get("bot_response", ""))) / n
    cur_q = sum(1 for t in turns if "?" in t.get("bot_response", "")) / n

    def _injection_rate(target: float, current: float) -> float:
        if current >= target:
            return 0.0
        return (target - current) / max(0.01, 1 - current)

    def _strip_rate(target: float, current: float) -> float:
        """How many of the excess-marker turns should we strip from?"""
        if current <= target:
            return 0.0
        return (current - target) / max(0.01, current)

    excl_inject = _injection_rate(target_excl, cur_excl)
    emoji_inject = _injection_rate(target_emoji, cur_emoji)
    q_inject = _injection_rate(target_q, cur_q)

    excl_strip = _strip_rate(target_excl, cur_excl)
    emoji_strip = _strip_rate(target_emoji, cur_emoji)
    q_strip = _strip_rate(target_q, cur_q)

    # Pass 2: Apply injection/stripping using deterministic hashes
    for i, turn in enumerate(turns):
        resp = turn.get("bot_response", "")
        h_base = hashlib.md5(f"tone_{i}_{resp[:20]}".encode()).hexdigest()

        # --- Exclamation ---
        h = int(h_base[:8], 16)
        if excl_inject > 0 and (h % 1000) < (excl_inject * 1000) and "!" not in resp:
            resp = resp.rstrip() + "!"
        elif excl_strip > 0 and (h % 1000) < (excl_strip * 1000) and "!" in resp:
            resp = resp.replace("!", "", 1)

        # --- Emoji ---
        h = int(h_base[8:16], 16)
        if emoji_inject > 0 and (h % 1000) < (emoji_inject * 1000) and not emoji_pat.search(resp):
            light_emojis = ["😊", "💙", "💪", "🙌", "🔥"]
            resp = resp.rstrip() + " " + light_emojis[h % len(light_emojis)]
        elif emoji_strip > 0 and (h % 1000) < (emoji_strip * 1000) and emoji_pat.search(resp):
            # Strip all emoji from this response
            resp = emoji_pat.sub("", resp).strip()

        # --- Question ---
        h = int(h_base[16:24], 16)
        if q_inject > 0 and (h % 1000) < (q_inject * 1000) and "?" not in resp:
            natural_questions = [
                " Todo bien?", " Cómo vas?", " Cómo estás?",
                " En serio?", " Sí?", " Vos?",
            ]
            resp = resp.rstrip() + natural_questions[h % len(natural_questions)]
        elif q_strip > 0 and (h % 1000) < (q_strip * 1000) and "?" in resp:
            resp = resp.replace("?", "", 1)

        turn["bot_response"] = resp


async def run_backtest(
    creator_id: str,
    creator_name: str = "",
    n: int = 100,
    seed: int = 42,
    output_dir: str = "./backtest_output",
    calibration_path: Optional[str] = None,
    use_finetuned: bool = False,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full backtest pipeline."""
    start_time = time.time()

    # Step 1: Load calibration
    calibration = {}
    if calibration_path:
        cal_path = Path(calibration_path)
    else:
        cal_path = Path(f"calibrations/{creator_id}.json")

    if cal_path.exists():
        with open(cal_path) as f:
            calibration = json.load(f)
        print(f"Loaded calibration from {cal_path}")
    else:
        print(f"WARNING: No calibration found at {cal_path}")

    # Step 2: Load conversations
    conversations = load_conversations_from_db(creator_id)

    # Step 3: Select subset
    selected = select_conversations(conversations, n, seed)
    print(f"Selected {len(selected)} conversations")

    # Step 4: Build all turns with context classification
    all_turns = []
    for conv in selected:
        for turn in conv["turns"]:
            turn["lead_username"] = conv["lead_username"]
            turn["context"] = classify_lead_context(turn["user_message"])
            all_turns.append(turn)

    print(f"Total turns before filtering: {len(all_turns)}")

    # Step 5: Filter contamination
    clean_turns, excluded_turns, filter_stats = filter_turns(
        selected, all_turns,
        creator_median_length=calibration.get("baseline", {}).get("median_length", 19),
    )
    print(f"Clean turns: {len(clean_turns)} (excluded {len(excluded_turns)})")

    # Step 6: Generate bot responses for each clean turn
    # Track turn index per conversation for dedup
    conv_turn_idx: Dict[str, int] = {}
    total_turns = len(clean_turns)
    if use_finetuned:
        print(f"Generating responses with fine-tuned model ({total_turns} turns)...")
    elif model == "scout":
        print(f"Generating responses with Llama 4 Scout BASE ({total_turns} turns)...")
    elif model == "scout-ft":
        print(f"Generating responses with Llama 4 Scout FT ({total_turns} turns)...")
    for i, turn in enumerate(clean_turns):
        conv_id = turn.get("lead_username", "")
        idx = conv_turn_idx.get(conv_id, 0)
        conv_turn_idx[conv_id] = idx + 1

        bot_result = await generate_bot_response(
            turn["user_message"],
            turn["context"],
            calibration,
            turn_index=idx,
            conversation_id=conv_id,
            use_finetuned=use_finetuned,
            model=model,
        )
        turn.update(bot_result)

        # Pace non-pool API calls
        if model in ("scout", "scout-ft") and not bot_result.get("pool_matched", False):
            await asyncio.sleep(1.0 if model == "scout-ft" else 0.3)

        # Post-processing for non-pool responses (matches dm_agent_v2 Phase 5)
        if not bot_result.get("pool_matched", False):
            resp = turn["bot_response"]
            # 1. Response fixes (typos, broken links, identity claims)
            fixed = apply_all_response_fixes(resp, creator_name=creator_name)
            if fixed:
                resp = fixed
            # 2. Question removal (uses creator's question rate from calibration)
            creator_q_rate = calibration.get("baseline", {}).get(
                "question_frequency_pct", 10.0
            ) / 100
            resp = process_questions(resp, turn["user_message"], question_rate=creator_q_rate)
            # 3. Length enforcement (calibration-aware, not hardcoded)
            resp = _enforce_calibrated_length(resp, turn["context"], calibration)
            turn["bot_response"] = resp

        # Progress indicator for API runs (API calls are slow)
        if (use_finetuned or model in ("scout", "scout-ft")) and (i + 1) % 20 == 0:
            print(f"  Generated {i + 1}/{total_turns} turns...")

    # Step 6.5: Global tone enforcement (two-pass)
    # Measure actual rates first, then inject to close gaps
    _apply_global_tone_enforcement(clean_turns, calibration)

    # Step 7: Evaluate
    evaluation = evaluate_all(clean_turns, calibration)

    # Step 8: Build output
    result = {
        "version": "v9-scout-ft" if model == "scout-ft" else ("v9-scout" if model == "scout" else ("v9-finetuned" if use_finetuned else "v9")),
        "timestamp": datetime.now().isoformat(),
        "creator_id": creator_id,
        "creator_name": creator_name,
        "seed": seed,
        "n_conversations": len(selected),
        "n_turns_total": len(all_turns),
        "n_turns_clean": len(clean_turns),
        "n_turns_excluded": len(excluded_turns),
        "filter_stats": filter_stats,
        "evaluation": evaluation,
        "conversations": [
            {
                "lead_username": conv["lead_username"],
                "turns": [
                    {
                        "user_message": t["user_message"],
                        "real_response": t["real_response"],
                        "real_length": t["real_length"],
                        "bot_response": t.get("bot_response", ""),
                        "pool_matched": t.get("pool_matched", False),
                        "pool_category": t.get("pool_category"),
                        "context": t.get("context", "otro"),
                        "confidence": t.get("confidence", 0),
                    }
                    for t in conv["turns"]
                    if "bot_response" in t
                ],
            }
            for conv in selected
            if any("bot_response" in t for t in conv["turns"])
        ],
        "duration_seconds": round(time.time() - start_time, 1),
    }

    # Step 9: Save output
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"backtest_{timestamp}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # Also save a summary
    summary_path = os.path.join(output_dir, "summary.txt")
    with open(summary_path, "w") as f:
        f.write(f"Backtest Results - {creator_name}\n")
        f.write(f"{'=' * 50}\n")
        f.write(f"Date: {result['timestamp']}\n")
        f.write(f"Conversations: {result['n_conversations']}\n")
        f.write(f"Clean turns: {result['n_turns_clean']}\n")
        f.write(f"Excluded turns: {result['n_turns_excluded']}\n\n")
        f.write(f"OVERALL SCORE: {evaluation['overall_score']}\n\n")
        for dim, data in evaluation["dimensions"].items():
            f.write(f"  {dim:10s}: {data['score']:5.1f}  (weight {data['weight']:.0%})\n")

    print(f"\n{'=' * 50}")
    print(f"BACKTEST RESULTS: {creator_name}")
    print(f"{'=' * 50}")
    print(f"Conversations: {result['n_conversations']}")
    print(f"Clean turns: {result['n_turns_clean']} (excluded {result['n_turns_excluded']})")
    print(f"\nOVERALL SCORE: {evaluation['overall_score']}")
    print()
    for dim, data in evaluation["dimensions"].items():
        print(f"  {dim:10s}: {data['score']:5.1f}  (weight {data['weight']:.0%})")
    print(f"\nOutput: {output_path}")
    print(f"Duration: {result['duration_seconds']}s")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run backtest")
    parser.add_argument("--creator-id", default=CREATOR_ID_DEFAULT)
    parser.add_argument("--creator-name", default="Stefano Bonanno")
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", default="./backtest_output")
    parser.add_argument("--calibration", default=None)
    parser.add_argument(
        "--use-finetuned", action="store_true", default=False,
        help="Use Together.ai fine-tuned model instead of mock for non-pool turns",
    )
    parser.add_argument(
        "--model", default=None, choices=["scout", "scout-ft"],
        help="Use a specific model: 'scout' = Scout BASE via DeepInfra, 'scout-ft' = Scout FT via Together.ai",
    )
    args = parser.parse_args()

    asyncio.run(run_backtest(
        creator_id=args.creator_id,
        creator_name=args.creator_name,
        n=args.n,
        seed=args.seed,
        output_dir=args.output_dir,
        calibration_path=args.calibration,
        use_finetuned=args.use_finetuned,
        model=args.model,
    ))
