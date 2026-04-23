# Few-Shot Injection — Description

**Date:** 2026-04-23
**Sprint:** top-6 activations
**Flag:** `flags.few_shot` (env: `ENABLE_FEW_SHOT`)

## Value proposition

Injects k=5 creator-specific example pairs `(user_message, response)` into the LLM prompt at every turn, selected via intent-stratified + semantic-hybrid matching against the incoming message. The examples come from the creator's own calibration pack (`calibrations/<creator_id>_unified.json`) built from their real historical responses.

Purpose: give the base LLM runtime persona grounding (same idea as RoleLLM / ACL 2024) without fine-tuning. Without few-shot, the LLM generates in its own register; with few-shot, it mirrors the creator's length, vocabulary, emoji usage, punctuation, and rhythm.

## Why it matters for CCEE

Primary dimensions expected to move when flag is ON:

| Dim | Rationale | Expected Δ |
|---|---|---|
| **B2 (baseline adherence)** | Bot's message length and structure snap towards the creator's median. | +3 to +6 |
| **S1 (style fidelity)** | Vocabulary, emoji rate, punctuation rate, register pulled from examples. | +2 to +4 |
| **L1 (length calibration)** | Examples anchor short-message norm (Iris median ≈ 40 chars). | +1.5 to +3 |
| **J3 (journey appropriateness)** | Intent-stratified selection shows turn-appropriate responses. | +1 to +2 |

Secondary (watch for regression):
- K1 (context coherence): examples may push generic patterns. Guard with semantic hybrid.
- S4 (adaptation): examples may reduce personalization; offset by diversity in pool.

## Callsite (hot path)

```
backend/core/dm/phases/context.py:1350
  if ENABLE_FEW_SHOT and agent.calibration:
      few_shot_section = get_few_shot_section(
          agent.calibration,
          max_examples=5,   # RoleLLM (ACL 2024): k=5 empirically optimal
          current_message=message,
          lead_language=detect_message_language(message),
          detected_intent=intent_value,
      )
```

## Selection pipeline

1. **Language filter** (`detect_message_language(message)` → ISO code or `ca-es` tag): keep examples matching the lead's language; for code-switching (`ca-es`) keep full pool.
2. **Stratified selection** (`_select_stratified`): 3 examples for detected intent, 1 per other intent-group (up to 5), 2 semantic matches if message >15 chars.
3. **Format**: `=== EJEMPLOS REALES DE COMO RESPONDES ===` block with `Follower:` / `Tu:` pairs, closing directive.

## Non-goals

- This is NOT a learned example selector (EPR/vote-k/LENS). Those live in DEFER-Q2 per `04_state_of_art.md`.
- This is NOT static templates — every turn re-selects from the creator pool.
- This is NOT persona-in-system-prompt — that's Doc D; few-shot complements it.
