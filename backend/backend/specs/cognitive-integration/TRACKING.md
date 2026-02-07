# TRACKING: Cognitive Module Integration

## Progress

```
P0 SECURITY       [⬜⬜⬜] 0/3
P1 QUALITY        [⬜⬜⬜⬜] 0/4  
P2 INTELLIGENCE   [⬜⬜⬜⬜⬜] 0/5
P3 PERSONTIC      [⬜⬜⬜] 0/3

TOTAL             [⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜] 0/15 (0%)
FLAGS             5/20
```

---

## P0: Security

### Step 1: sensitive_detector
- [ ] 1.1 Create test file `tests/unit/test_dm_agent_sensitive.py`
- [ ] 1.2 Run test (verify module exists)
- [ ] 1.3 Add import to dm_agent_v2.py
- [ ] 1.4 Add feature flag ENABLE_SENSITIVE_DETECTION
- [ ] 1.5 Add pre-pipeline check in process_dm()
- [ ] 1.6 Run test (must pass)
- [ ] 1.7 Run all tests
- [ ] 1.8 Commit: `feat: integrate sensitive_detector pre-pipeline`

### Step 2: output_validator
- [ ] 2.1 Create test file `tests/unit/test_dm_agent_output_validator.py`
- [ ] 2.2 Run test (verify module exists)
- [ ] 2.3 Add import to dm_agent_v2.py
- [ ] 2.4 Add feature flag ENABLE_OUTPUT_VALIDATION
- [ ] 2.5 Add post-LLM validation in process_dm()
- [ ] 2.6 Run test (must pass)
- [ ] 2.7 Run all tests
- [ ] 2.8 Commit: `feat: integrate output_validator post-LLM`

### Step 3: response_fixes
- [ ] 3.1 Create test file `tests/unit/test_dm_agent_response_fixes.py`
- [ ] 3.2 Run test (verify module exists)
- [ ] 3.3 Add import to dm_agent_v2.py
- [ ] 3.4 Add feature flag ENABLE_RESPONSE_FIXES
- [ ] 3.5 Add fixes after validator in process_dm()
- [ ] 3.6 Run test (must pass)
- [ ] 3.7 Run all tests
- [ ] 3.8 Commit: `feat: integrate response_fixes for corrections`

**P0 Checkpoint:**
```bash
grep -c "ENABLE_" backend/core/dm_agent_v2.py  # Must be 8
pytest backend/tests/ -x -q                     # All pass
```

---

## P1: Quality

### Step 4: question_remover
- [ ] 4.1 Create test file `tests/unit/test_dm_agent_question_remover.py`
- [ ] 4.2 Run test (verify module exists)
- [ ] 4.3 Add import to dm_agent_v2.py
- [ ] 4.4 Add feature flag ENABLE_QUESTION_REMOVER
- [ ] 4.5 Add in process_dm() after guardrails
- [ ] 4.6 Run test (must pass)
- [ ] 4.7 Run all tests
- [ ] 4.8 Commit: `feat: integrate question_remover`

### Step 5: bot_question_analyzer
- [ ] 5.1 Create test file `tests/unit/test_dm_agent_question_analyzer.py`
- [ ] 5.2 Run test (verify module exists)
- [ ] 5.3 Add import to dm_agent_v2.py
- [ ] 5.4 Add feature flag ENABLE_QUESTION_CONTEXT
- [ ] 5.5 Add in _init_services() and process_dm() phase 2
- [ ] 5.6 Run test (must pass)
- [ ] 5.7 Run all tests
- [ ] 5.8 Commit: `feat: integrate bot_question_analyzer`

### Step 6: query_expansion
- [ ] 6.1 Create test file `tests/unit/test_dm_agent_query_expansion.py`
- [ ] 6.2 Run test (verify module exists)
- [ ] 6.3 Add import to dm_agent_v2.py
- [ ] 6.4 Add feature flag ENABLE_QUERY_EXPANSION
- [ ] 6.5 Add in _init_services() and process_dm() before RAG
- [ ] 6.6 Run test (must pass)
- [ ] 6.7 Run all tests
- [ ] 6.8 Commit: `feat: integrate query_expansion`

### Step 7: reflexion_engine
- [ ] 7.1 Create test file `tests/unit/test_dm_agent_reflexion.py`
- [ ] 7.2 Run test (verify module exists)
- [ ] 7.3 Add import to dm_agent_v2.py
- [ ] 7.4 Add feature flag ENABLE_REFLEXION
- [ ] 7.5 Add in _init_services() and process_dm() post-fixes
- [ ] 7.6 Run test (must pass)
- [ ] 7.7 Run all tests
- [ ] 7.8 Commit: `feat: integrate reflexion_engine`

**P1 Checkpoint:**
```bash
grep -c "ENABLE_" backend/core/dm_agent_v2.py  # Must be 12
pytest backend/tests/ -x -q                     # All pass
```

---

## P2: Intelligence

### Step 8: lead_categorizer
- [ ] 8.1 Create test file `tests/unit/test_dm_agent_lead_categorizer.py`
- [ ] 8.2 Run test (verify module exists)
- [ ] 8.3 Add import to dm_agent_v2.py
- [ ] 8.4 Add feature flag ENABLE_LEAD_CATEGORIZER
- [ ] 8.5 Add in _init_services() and replace _get_lead_stage
- [ ] 8.6 Run test (must pass)
- [ ] 8.7 Run all tests
- [ ] 8.8 Commit: `feat: integrate lead_categorizer`

### Step 9: conversation_state
- [ ] 9.1 Create test file `tests/unit/test_dm_agent_conversation_state.py`
- [ ] 9.2 Run test (verify module exists)
- [ ] 9.3 Add import to dm_agent_v2.py
- [ ] 9.4 Add feature flag ENABLE_CONVERSATION_STATE (default=false)
- [ ] 9.5 Add in _init_services() and process_dm() phase 2
- [ ] 9.6 Run test (must pass)
- [ ] 9.7 Run all tests
- [ ] 9.8 Commit: `feat: integrate conversation_state`

### Step 10: conversation_memory (fact tracking)
- [ ] 10.1 Create test file `tests/unit/test_dm_agent_fact_tracking.py`
- [ ] 10.2 Run test (verify module exists)
- [ ] 10.3 Add feature flag ENABLE_FACT_TRACKING
- [ ] 10.4 Add in _update_follower_memory()
- [ ] 10.5 Run test (must pass)
- [ ] 10.6 Run all tests
- [ ] 10.7 Commit: `feat: integrate fact_tracking`

### Step 11: chain_of_thought (activate flag)
- [ ] 11.1 Create test file `tests/unit/test_dm_agent_chain_of_thought.py`
- [ ] 11.2 Run test (verify module exists)
- [ ] 11.3 Change ENABLE_CHAIN_OF_THOUGHT default to true
- [ ] 11.4 Verify CoT code exists in process_dm()
- [ ] 11.5 Run test (must pass)
- [ ] 11.6 Run all tests
- [ ] 11.7 Commit: `feat: activate chain_of_thought`

### Step 12: prompt_builder (advanced)
- [ ] 12.1 Create test file `tests/unit/test_dm_agent_advanced_prompt.py`
- [ ] 12.2 Run test (verify module exists)
- [ ] 12.3 Add import to dm_agent_v2.py
- [ ] 12.4 Add feature flag ENABLE_ADVANCED_PROMPTS (default=false)
- [ ] 12.5 Add in process_dm() phase 3
- [ ] 12.6 Run test (must pass)
- [ ] 12.7 Run all tests
- [ ] 12.8 Commit: `feat: integrate advanced prompt_builder`

**P2 Checkpoint:**
```bash
grep -c "ENABLE_" backend/core/dm_agent_v2.py  # Must be 17
pytest backend/tests/ -x -q                     # All pass
```

---

## P3: Personalization

### Step 13: dna_update_triggers
- [ ] 13.1 Create test file `tests/unit/test_dm_agent_dna_triggers.py`
- [ ] 13.2 Run test (verify module exists)
- [ ] 13.3 Add import to dm_agent_v2.py
- [ ] 13.4 Add feature flag ENABLE_DNA_TRIGGERS
- [ ] 13.5 Add in _init_services() and process_dm() phase 5
- [ ] 13.6 Run test (must pass)
- [ ] 13.7 Run all tests
- [ ] 13.8 Commit: `feat: integrate dna_update_triggers`

### Step 14: relationship_type_detector
- [ ] 14.1 Create test file `tests/unit/test_dm_agent_relationship_detector.py`
- [ ] 14.2 Run test (verify module exists)
- [ ] 14.3 Add import to dm_agent_v2.py
- [ ] 14.4 Add feature flag ENABLE_RELATIONSHIP_DETECTION (default=false)
- [ ] 14.5 Add in _init_services() and process_dm() phase 2
- [ ] 14.6 Run test (must pass)
- [ ] 14.7 Run all tests
- [ ] 14.8 Commit: `feat: integrate relationship_type_detector`

### Step 15: vocabulary_extractor
- [ ] 15.1 Create test file `tests/unit/test_dm_agent_vocabulary.py`
- [ ] 15.2 Run test (verify module exists)
- [ ] 15.3 Add import to dm_agent_v2.py
- [ ] 15.4 Add feature flag ENABLE_VOCABULARY_EXTRACTION (default=false)
- [ ] 15.5 Add in _init_services() and process_dm() phase 5
- [ ] 15.6 Run test (must pass)
- [ ] 15.7 Run all tests
- [ ] 15.8 Commit: `feat: integrate vocabulary_extractor`

**P3 Checkpoint (FINAL):**
```bash
grep -c "ENABLE_" backend/core/dm_agent_v2.py  # Must be 20
wc -l backend/core/dm_agent_v2.py              # Must be <1,400
pytest backend/tests/ -x -q                     # All pass
python -c "from core.dm_agent_v2 import DMResponderAgent; print('OK')"
```

---

## Completion Log

| Step | Module | Date | Commit | Notes |
|------|--------|------|--------|-------|
| 1 | sensitive_detector | | | |
| 2 | output_validator | | | |
| 3 | response_fixes | | | |
| 4 | question_remover | | | |
| 5 | bot_question_analyzer | | | |
| 6 | query_expansion | | | |
| 7 | reflexion_engine | | | |
| 8 | lead_categorizer | | | |
| 9 | conversation_state | | | |
| 10 | conversation_memory | | | |
| 11 | chain_of_thought | | | |
| 12 | prompt_builder | | | |
| 13 | dna_update_triggers | | | |
| 14 | relationship_detector | | | |
| 15 | vocabulary_extractor | | | |
