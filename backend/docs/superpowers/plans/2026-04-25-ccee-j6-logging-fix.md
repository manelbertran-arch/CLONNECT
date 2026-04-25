# CCEE J6 Logging Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `probe_question_text` and response text fields to J6 `per_pair` (within-conv) and `per_probe` (cross-session) result dicts so that CCEE JSON outputs are fully self-diagnostic without reconstructing from raw conversation history.

**Architecture:** Minimal patch to `core/evaluation/multi_turn_scorer.py` — the two functions that already hold the text in local variables just need to include those variables in the returned dict. No structural change; full backwards compat (only additive).

**Tech Stack:** Python 3.11, pytest, FastAPI/SQLAlchemy project structure.

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `core/evaluation/multi_turn_scorer.py` | Modify | `score_j6_qa_consistency()` line ~1249: add 3 text fields to `per_pair` items; `_score_j6_cross_session()` line ~1470: add `probe_question_text` + `cross_session_responses` to `per_probe` items |
| `tests/test_metric_fixes.py` | Modify | Add `TestJ6LoggingFix` class with 4 tests |
| `docs/finetuning_sprint_iris/presprint7/10_ccee_j6_logging_fix.md` | Create | Schema before/after, smoke test result |

---

## Task 1: Fix `per_pair` in `score_j6_qa_consistency()`

**Files:**
- Modify: `core/evaluation/multi_turn_scorer.py:1249-1254`
- Test: `tests/test_metric_fixes.py`

### Current `per_pair` schema (lines 1249-1254):
```python
pair_details.append({
    "probe_id": probe_id,
    "early_turn": early_ans["turn_num"],
    "late_turn": late_ans["turn_num"],
    "score_1_5": score,
})
```

### Target `per_pair` schema (additive only):
```python
pair_details.append({
    "probe_id": probe_id,
    "early_turn": early_ans["turn_num"],
    "late_turn": late_ans["turn_num"],
    "score_1_5": score,
    "probe_question_text": early_ans["probe_question"],
    "early_turn_response_text": early_ans["bot_answer"],
    "late_turn_response_text": late_ans["bot_answer"],
})
```

- [ ] **Step 1.1: Write failing test**

Add to `tests/test_metric_fixes.py`:

```python
class TestJ6LoggingFix:
    """J6 per_pair and per_probe must include response texts (A2 fix)."""

    def _make_probe_history(self):
        """Two probe turns with the same probe_id at different turn positions."""
        return [
            {"role": "user",      "content": "What is your favourite food?",
             "is_qa_probe": True, "probe_id": "p1"},
            {"role": "assistant", "content": "I love sushi!"},
            {"role": "user",      "content": "Tell me about your day."},
            {"role": "assistant", "content": "It was great."},
            {"role": "user",      "content": "What is your favourite food?",
             "is_qa_probe": True, "probe_id": "p1"},
            {"role": "assistant", "content": "Sushi is definitely my favourite."},
        ]

    def test_per_pair_includes_probe_question_text(self):
        import core.evaluation.multi_turn_scorer as scorer
        conv = {"history": self._make_probe_history()}
        mock_raw = "Feedback: consistent [RESULT] 5"
        with patch.object(scorer, "_load_compressed_doc_d", return_value="doc d"), \
             patch.object(scorer, "_call_judge", return_value=mock_raw), \
             patch.object(scorer, "_parse_result_score", return_value=5):
            result = scorer.score_j6_qa_consistency(conv, "test_creator")
        assert result["mode"] == "probe_based"
        assert len(result["per_pair"]) == 1
        pair = result["per_pair"][0]
        assert pair["probe_question_text"] == "What is your favourite food?"

    def test_per_pair_includes_early_response_text(self):
        import core.evaluation.multi_turn_scorer as scorer
        conv = {"history": self._make_probe_history()}
        mock_raw = "Feedback: consistent [RESULT] 5"
        with patch.object(scorer, "_load_compressed_doc_d", return_value="doc d"), \
             patch.object(scorer, "_call_judge", return_value=mock_raw), \
             patch.object(scorer, "_parse_result_score", return_value=5):
            result = scorer.score_j6_qa_consistency(conv, "test_creator")
        pair = result["per_pair"][0]
        assert pair["early_turn_response_text"] == "I love sushi!"

    def test_per_pair_includes_late_response_text(self):
        import core.evaluation.multi_turn_scorer as scorer
        conv = {"history": self._make_probe_history()}
        mock_raw = "Feedback: consistent [RESULT] 5"
        with patch.object(scorer, "_load_compressed_doc_d", return_value="doc d"), \
             patch.object(scorer, "_call_judge", return_value=mock_raw), \
             patch.object(scorer, "_parse_result_score", return_value=5):
            result = scorer.score_j6_qa_consistency(conv, "test_creator")
        pair = result["per_pair"][0]
        assert pair["late_turn_response_text"] == "Sushi is definitely my favourite."
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
cd /Users/manelbertranluque/Clonnect/backend && \
.venv/bin/python3 -m pytest tests/test_metric_fixes.py::TestJ6LoggingFix -v 2>&1 | tail -20
```

Expected: FAIL with `KeyError: 'probe_question_text'`

- [ ] **Step 1.3: Apply the fix to `multi_turn_scorer.py`**

In `core/evaluation/multi_turn_scorer.py`, find the block at ~line 1249 that appends to `pair_details` inside `score_j6_qa_consistency()` and add the three text fields:

```python
# OLD:
pair_details.append({
    "probe_id": probe_id,
    "early_turn": early_ans["turn_num"],
    "late_turn": late_ans["turn_num"],
    "score_1_5": score,
})

# NEW:
pair_details.append({
    "probe_id": probe_id,
    "early_turn": early_ans["turn_num"],
    "late_turn": late_ans["turn_num"],
    "score_1_5": score,
    "probe_question_text": early_ans["probe_question"],
    "early_turn_response_text": early_ans["bot_answer"],
    "late_turn_response_text": late_ans["bot_answer"],
})
```

- [ ] **Step 1.4: Syntax-check the modified file**

```bash
cd /Users/manelbertranluque/Clonnect/backend && \
.venv/bin/python3 -c "import ast; ast.parse(open('core/evaluation/multi_turn_scorer.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 1.5: Run tests to verify they pass**

```bash
cd /Users/manelbertranluque/Clonnect/backend && \
.venv/bin/python3 -m pytest tests/test_metric_fixes.py::TestJ6LoggingFix -v 2>&1 | tail -20
```

Expected: 3 PASSED

- [ ] **Step 1.6: Commit**

```bash
git add core/evaluation/multi_turn_scorer.py tests/test_metric_fixes.py
git commit -m "fix(j6): add probe/response texts to per_pair in score_j6_qa_consistency"
```

---

## Task 2: Fix `per_probe` in `_score_j6_cross_session()`

**Files:**
- Modify: `core/evaluation/multi_turn_scorer.py:1470-1475`
- Test: `tests/test_metric_fixes.py`

### Current `per_probe` schema (lines 1470-1475):
```python
pair_details.append({
    "probe_id": probe_id,
    "n_conversations": len(conv_answers),
    "score_1_5": score,
    "feedback": raw[:300],
})
```

### Target `per_probe` schema (additive only):
```python
pair_details.append({
    "probe_id": probe_id,
    "n_conversations": len(conv_answers),
    "score_1_5": score,
    "feedback": raw[:300],
    "probe_question_text": conv_answers[0]["probe_question"],
    "cross_session_responses": [
        {"conv_idx": a["conv_idx"], "bot_answer": a["bot_answer"]}
        for a in conv_answers
    ],
})
```

- [ ] **Step 2.1: Write failing test**

Add to `TestJ6LoggingFix` class in `tests/test_metric_fixes.py`:

```python
def test_cross_session_per_probe_includes_texts(self):
    import core.evaluation.multi_turn_scorer as scorer
    probe_hist = self._make_probe_history()
    conv1 = {"history": probe_hist}
    # Slightly different answers in second conversation
    hist2 = [
        {"role": "user",      "content": "What is your favourite food?",
         "is_qa_probe": True, "probe_id": "p1"},
        {"role": "assistant", "content": "Without a doubt, sushi."},
    ]
    conv2 = {"history": hist2}
    mock_raw = "Feedback: consistent [RESULT] 5"
    with patch.object(scorer, "_load_compressed_doc_d", return_value="doc d"), \
         patch.object(scorer, "_call_judge", return_value=mock_raw), \
         patch.object(scorer, "_parse_result_score", return_value=5):
        result = scorer._score_j6_cross_session([conv1, conv2], "test_creator")
    assert result["score"] is not None
    probe = result["per_probe"][0]
    assert probe["probe_question_text"] == "What is your favourite food?"
    assert len(probe["cross_session_responses"]) == 2
    answers = {r["conv_idx"]: r["bot_answer"] for r in probe["cross_session_responses"]}
    assert answers[0] == "I love sushi!"
    assert answers[1] == "Without a doubt, sushi."
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
cd /Users/manelbertranluque/Clonnect/backend && \
.venv/bin/python3 -m pytest tests/test_metric_fixes.py::TestJ6LoggingFix::test_cross_session_per_probe_includes_texts -v 2>&1 | tail -20
```

Expected: FAIL with `KeyError: 'probe_question_text'`

- [ ] **Step 2.3: Apply the fix to `_score_j6_cross_session()`**

In `core/evaluation/multi_turn_scorer.py`, find the block at ~line 1470 that appends to `pair_details` inside `_score_j6_cross_session()` and add the two new fields:

```python
# OLD:
pair_details.append({
    "probe_id": probe_id,
    "n_conversations": len(conv_answers),
    "score_1_5": score,
    "feedback": raw[:300],
})

# NEW:
pair_details.append({
    "probe_id": probe_id,
    "n_conversations": len(conv_answers),
    "score_1_5": score,
    "feedback": raw[:300],
    "probe_question_text": conv_answers[0]["probe_question"],
    "cross_session_responses": [
        {"conv_idx": a["conv_idx"], "bot_answer": a["bot_answer"]}
        for a in conv_answers
    ],
})
```

- [ ] **Step 2.4: Syntax-check the modified file**

```bash
cd /Users/manelbertranluque/Clonnect/backend && \
.venv/bin/python3 -c "import ast; ast.parse(open('core/evaluation/multi_turn_scorer.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 2.5: Run all J6 logging tests**

```bash
cd /Users/manelbertranluque/Clonnect/backend && \
.venv/bin/python3 -m pytest tests/test_metric_fixes.py::TestJ6LoggingFix -v 2>&1 | tail -20
```

Expected: 4 PASSED

- [ ] **Step 2.6: Run full test suite (no regressions)**

```bash
cd /Users/manelbertranluque/Clonnect/backend && \
.venv/bin/python3 -m pytest tests/test_metric_fixes.py -v 2>&1 | tail -30
```

Expected: All previously-passing tests still pass.

- [ ] **Step 2.7: Commit**

```bash
git add core/evaluation/multi_turn_scorer.py tests/test_metric_fixes.py
git commit -m "fix(j6): add probe_question_text + cross_session_responses to per_probe in _score_j6_cross_session"
```

---

## Task 3: Write schema documentation

**Files:**
- Create: `docs/finetuning_sprint_iris/presprint7/10_ccee_j6_logging_fix.md`

- [ ] **Step 3.1: Create doc with before/after schema**

Create `docs/finetuning_sprint_iris/presprint7/10_ccee_j6_logging_fix.md` with:

```markdown
# A2: CCEE J6 Logging Fix

**Date:** 2026-04-25
**Branch:** fix/ccee-j6-logging
**Motivation:** Post-mortem on pre-sprint7 CCEE runs found that J6 probe/response
texts were missing from output JSON, making results undiagnosable without
re-running and re-reading conversation history.

---

## Problem

`score_j6_qa_consistency()` returned `per_pair` items without response text:
```json
{
  "probe_id": "p1",
  "early_turn": 0,
  "late_turn": 4,
  "score_1_5": 5
}
```

`_score_j6_cross_session()` returned `per_probe` items without question or answers:
```json
{
  "probe_id": "p1",
  "n_conversations": 5,
  "score_1_5": 4,
  "feedback": "..."
}
```

## Fix

### within_conv `per_pair` — added 3 fields

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

### cross_session `per_probe` — added 2 fields

```json
{
  "probe_id": "p1",
  "n_conversations": 5,
  "score_1_5": 4,
  "feedback": "...",
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

## Backwards Compatibility

Only additive. All existing fields preserved. Old analysis code reading the JSON
(e.g. reading `score_1_5`, `probe_id`) is unaffected.

## Smoke Test

Run:
```bash
# [fill in smoke test command and result after running]
```

Output JSON confirmed to have new fields: [YES/NO — fill in]
```

- [ ] **Step 3.2: Commit doc**

```bash
git add docs/finetuning_sprint_iris/presprint7/10_ccee_j6_logging_fix.md
git commit -m "docs(presprint7): add A2 J6 logging fix schema doc"
```

---

## Task 4: Smoke test

**Goal:** Verify that a real CCEE run (1 run, 1 case, 1 MT conversation) populates the new fields.

- [ ] **Step 4.1: Check available baseline JSON and CCEE config**

```bash
ls /Users/manelbertranluque/Clonnect/backend/ccee_outputs/iris_bertran/ 2>/dev/null | tail -5
# or
find /Users/manelbertranluque/Clonnect/backend -name "*.json" -path "*/ccee*" | head -5
```

- [ ] **Step 4.2: Run mini CCEE — confirm JSON has new fields**

Run a single CCEE pass with `--runs 1 --cases 1` and `--v41` (to enable J6) against
the baseline creator, then inspect the output JSON:

```bash
cd /Users/manelbertranluque/Clonnect/backend && \
source config/env_ccee_gemma4_full.sh && \
.venv/bin/python3 scripts/run_ccee.py \
  --creator iris_bertran \
  --runs 1 \
  --cases 1 \
  --multi-turn \
  --v41 \
  --save-as smoke_j6_fix_$(date +%Y%m%d_%H%M%S) \
  2>&1 | tail -40
```

Then inspect:
```bash
SMOKE=$(ls -t ccee_outputs/iris_bertran/smoke_j6_fix_*.json | head -1)
.venv/bin/python3 -c "
import json, sys
d = json.load(open('$SMOKE'))
found_pair = False
found_cross = False
for run in d.get('runs', []):
    mt = run.get('mt_results', {})
    pfc = mt.get('per_conversation_full', [])
    for conv in pfc:
        j6 = conv.get('J6_qa_consistency', {})
        pp = j6.get('per_pair', [])
        if pp:
            print('per_pair[0]:', json.dumps(pp[0], indent=2))
            assert 'probe_question_text' in pp[0], 'FAIL: probe_question_text missing from per_pair'
            assert 'early_turn_response_text' in pp[0], 'FAIL: early_turn_response_text missing from per_pair'
            assert 'late_turn_response_text' in pp[0], 'FAIL: late_turn_response_text missing from per_pair'
            found_pair = True
            break
    cross = mt.get('J6_cross_session', {})
    pp2 = cross.get('per_probe', [])
    if pp2:
        print('cross per_probe[0]:', json.dumps(pp2[0], indent=2))
        assert 'probe_question_text' in pp2[0], 'FAIL: probe_question_text missing from per_probe'
        assert 'cross_session_responses' in pp2[0], 'FAIL: cross_session_responses missing from per_probe'
        found_cross = True
    break
if not found_pair:
    print('WARNING: per_pair not found — J6 probe-based mode may not have fired')
    print('Top-level run keys:', list(d.get('runs', [{}])[0].keys()) if d.get('runs') else 'no runs')
if not found_cross:
    print('INFO: cross_session per_probe not found — need 2+ conversations for cross-session J6')
print('Smoke test: per_pair=%s, cross=%s' % (found_pair, found_cross))
"
```

- [ ] **Step 4.3: Update smoke test result in doc**

Fill in the smoke test result in `docs/finetuning_sprint_iris/presprint7/10_ccee_j6_logging_fix.md`.

- [ ] **Step 4.4: Final commit**

```bash
git add docs/finetuning_sprint_iris/presprint7/10_ccee_j6_logging_fix.md
git commit -m "docs(presprint7): A2 smoke test result confirmed"
```

---

## Checklist Before Marking Complete

- [ ] `per_pair` has `probe_question_text`, `early_turn_response_text`, `late_turn_response_text`
- [ ] `per_probe` (cross-session) has `probe_question_text`, `cross_session_responses`
- [ ] All 4 new tests pass
- [ ] All previously-passing tests still pass
- [ ] Syntax check on `multi_turn_scorer.py` passes
- [ ] Smoke test JSON confirms new fields populated
- [ ] Doc written with schema before/after
- [ ] All changes on branch `fix/ccee-j6-logging`
