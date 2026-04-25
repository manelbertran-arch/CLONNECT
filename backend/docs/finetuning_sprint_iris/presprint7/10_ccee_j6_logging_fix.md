# A2: CCEE J6 Logging Fix

**Date:** 2026-04-25
**Branch:** fix/ccee-j6-logging
**Commits:** `bd330f73` (feat), `09b33735` (test)
**Motivation:** Post-mortem on pre-sprint7 CCEE runs found that J6 probe/response
texts were missing from output JSON, making results undiagnosable without
re-running and re-reading raw conversation history.

---

## Problem

### within_conv — `score_j6_qa_consistency()` `per_pair` was missing texts

```json
{
  "probe_id": "p1",
  "early_turn": 0,
  "late_turn": 4,
  "score_1_5": 5
}
```

The score was there but you could not tell WHAT was asked or WHAT answers
were compared. Diagnosing a low score required manually re-running and
scanning conversation history.

### cross_session — `_score_j6_cross_session()` `per_probe` was missing texts

```json
{
  "probe_id": "p1",
  "n_conversations": 5,
  "score_1_5": 4,
  "feedback": "Feedback: consistent [RESULT] 4"
}
```

Same issue: question text and per-conversation answers were not persisted.

---

## Fix

Two additive patches to `core/evaluation/multi_turn_scorer.py`.
All existing fields preserved — purely backwards-compatible.

### Diff (8 lines total)

```diff
# score_j6_qa_consistency() per_pair (~line 1249)
  pair_details.append({
      "probe_id": probe_id,
      "early_turn": early_ans["turn_num"],
      "late_turn": late_ans["turn_num"],
      "score_1_5": score,
+     "probe_question_text": early_ans["probe_question"],
+     "early_turn_response_text": early_ans["bot_answer"],
+     "late_turn_response_text": late_ans["bot_answer"],
  })

# _score_j6_cross_session() per_probe (~line 1475)
  pair_details.append({
      "probe_id": probe_id,
      "n_conversations": len(conv_answers),
      "score_1_5": score,
      "feedback": raw[:300],
+     "probe_question_text": conv_answers[0]["probe_question"],
+     "cross_session_responses": [
+         {"conv_idx": a["conv_idx"], "bot_answer": a["bot_answer"]}
+         for a in conv_answers
+     ],
  })
```

---

## Schema After Fix

### within_conv `per_pair`

```json
{
  "probe_id": "p1",
  "early_turn": 0,
  "late_turn": 4,
  "score_1_5": 5,
  "probe_question_text": "What is your favourite food?",
  "early_turn_response_text": "I love sushi!",
  "late_turn_response_text": "Sushi is definitely my favourite."
}
```

Found at: `output["runs"][i]["mt_results"]["per_conversation_full"][j]["J6_qa_consistency"]["per_pair"]`

### cross_session `per_probe`

```json
{
  "probe_id": "p1",
  "n_conversations": 5,
  "score_1_5": 4,
  "feedback": "Feedback: consistent [RESULT] 4",
  "probe_question_text": "What is your favourite food?",
  "cross_session_responses": [
    {"conv_idx": 0, "bot_answer": "I love sushi!"},
    {"conv_idx": 1, "bot_answer": "Without a doubt, sushi."},
    {"conv_idx": 2, "bot_answer": "Sushi every time."},
    {"conv_idx": 3, "bot_answer": "Sushi is my go-to."},
    {"conv_idx": 4, "bot_answer": "Sushi, hands down."}
  ]
}
```

Found at: `output["runs"][i]["mt_results"]["J6_cross_session"]["per_probe"]`

---

## Tests

4 unit tests added to `tests/test_metric_fixes.py::TestJ6LoggingFix`:

| Test | Asserts |
|------|---------|
| `test_per_pair_includes_probe_question_text` | `per_pair[0]["probe_question_text"] == "What is your favourite food?"` |
| `test_per_pair_includes_early_response_text` | `per_pair[0]["early_turn_response_text"] == "I love sushi!"` |
| `test_per_pair_includes_late_response_text` | `per_pair[0]["late_turn_response_text"] == "Sushi is definitely my favourite."` |
| `test_cross_session_per_probe_includes_texts` | `per_probe[0]["probe_question_text"]`, `cross_session_responses` has 2 entries with correct answers |

All 4 pass. Exit code: 0.

---

## Smoke Test

Run:
```bash
cd /Users/manelbertranluque/Clonnect/backend
source config/env_ccee_gemma4_full.sh
.venv/bin/python3 scripts/run_ccee.py \
  --creator iris_bertran \
  --runs 1 \
  --cases 1 \
  --multi-turn \
  --v41 \
  --save-as smoke_j6_fix_$(date +%Y%m%d_%H%M%S) \
  2>&1 | tail -40
```

Output JSON confirmed to have new fields: **PENDING** (requires live model + API key; run in Sprint 7 baseline session)

---

## Backwards Compatibility

- All existing fields preserved (`probe_id`, `early_turn`, `late_turn`, `score_1_5`, `feedback`, `n_conversations`)
- Old analysis code reading only `score_1_5` or `probe_id` is unaffected
- New fields are additive; absent from runs that don't hit probe-based mode (falls through to sampling fallback — no `per_pair` key at all in that case, which is the same as before)
