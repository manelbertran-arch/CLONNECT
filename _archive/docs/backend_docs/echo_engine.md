# ECHO Engine — Architecture & Reference

## Overview

The ECHO Engine is Clonnect's quality evaluation and memory system for creator clones. It consists of three subsystems:

1. **CloneScore Engine** — 6-dimension quality evaluation
2. **Memory Engine** — Per-lead fact extraction and semantic recall
3. **LLM Judge** — GPT-4o-mini based evaluation component

## Architecture

```
                    ┌─────────────────────────────────┐
                    │         ECHO Engine              │
                    │                                  │
   DM Pipeline ───▶│  ┌──────────────┐  ┌──────────┐ │
   (dm_agent_v2)   │  │ CloneScore   │  │ Memory   │ │
                    │  │ Engine       │  │ Engine   │ │
                    │  │              │  │          │ │
                    │  │ 6 dimensions │  │ extract  │ │
                    │  │ weighted avg │  │ search   │ │
                    │  │              │  │ recall   │ │
                    │  └──────┬───────┘  └────┬─────┘ │
                    │         │               │       │
                    │    ┌────▼────┐    ┌─────▼────┐  │
                    │    │LLM Judge│    │ pgvector │  │
                    │    │(GPT-4o  │    │ semantic │  │
                    │    │ -mini)  │    │ search   │  │
                    │    └─────────┘    └──────────┘  │
                    └─────────────────────────────────┘
```

## CloneScore Dimensions

| # | Dimension | Weight | Method | Latency |
|---|-----------|--------|--------|---------|
| 1 | `style_fidelity` | 0.20 | Stylometric analysis (no LLM) | ~0ms |
| 2 | `knowledge_accuracy` | 0.20 | LLM Judge (GPT-4o-mini) | ~500ms |
| 3 | `persona_consistency` | 0.20 | LLM Judge (GPT-4o-mini) | ~500ms |
| 4 | `tone_appropriateness` | 0.15 | LLM Judge (GPT-4o-mini) | ~500ms |
| 5 | `sales_effectiveness` | 0.15 | Data-driven (DB queries) | ~50ms |
| 6 | `safety_score` | 0.10 | Rule-based (regex, no LLM) | ~0ms |

### Style Fidelity (0.20)
Compares bot response against creator's stylometric baseline:
- Message length ratio (25%)
- Emoji rate similarity (20%)
- Question frequency match (20%)
- Informal marker usage (15%)
- Vocabulary overlap (20%)

### Knowledge Accuracy (0.20)
LLM judge evaluates information correctness:
- Product prices match real data?
- Service descriptions accurate?
- Hallucinated information detected?
- Critical info omissions?

### Persona Consistency (0.20)
LLM judge evaluates personality alignment:
- Matches Doc D personality profile?
- Consistent with conversation history?
- Same formality/informality level?
- Respects creator boundaries?

### Tone Appropriateness (0.15)
LLM judge evaluates contextual tone:
- Appropriate for lead stage (new/hot/customer)?
- Matches relationship type (friend/lead/customer)?
- Empathetic when frustration detected?
- Not overly sales-y for casual conversations?

### Sales Effectiveness (0.15)
Data-driven metrics from DB:
- Stage progression rate (30%)
- Copilot approval rate (25%)
- Anti-ghost rate (20%)
- Edit distance similarity (25%)

### Safety Score (0.10)
Rule-based checks:
- No false promises (-15 per match)
- No offensive words (-30 per match)
- No leaked contact info (-20 per match)
- Creator's own contacts are allowed

### Aggregation
```
overall = weighted_sum(dimension_scores * weights)
if safety_score < 30:
    overall *= 0.5  # Safety penalty
```

## Memory Engine

### Three-Level Architecture
1. **Conversation Buffer** — Last messages (in dm_agent_v2)
2. **Lead Memory** — Extracted facts + pgvector search (this module)
3. **Creator Knowledge** — RAG + personality

### Fact Types
- `preference` — Lead's interests, likes
- `commitment` — Promises made by bot/creator
- `topic` — Discussed subjects
- `objection` — Resistance, doubts
- `personal_info` — Name, city, profession
- `purchase_history` — Transactions

### Ebbinghaus Decay
```
decay_factor = exp(-0.693 * days_since_last_access / half_life)
half_life = 30 * (1 + times_accessed)
if confidence * decay_factor < 0.1 → deactivate
```

## Feature Flags

| Flag | Default | Description |
|------|---------|-------------|
| `ENABLE_CLONE_SCORE` | `false` | Real-time style_fidelity scoring |
| `ENABLE_CLONE_SCORE_EVAL` | `false` | Daily batch evaluation job |
| `ENABLE_MEMORY_ENGINE` | `false` | Fact extraction + recall |
| `ENABLE_MEMORY_DECAY` | `false` | Daily Ebbinghaus decay job |
| `ENABLE_LEARNING_RULES` | `false` | Inject learned rules into DM prompts |

### Activation Sequence
1. `ENABLE_CLONE_SCORE=true` — Enables real-time style scoring (logging only)
2. `ENABLE_MEMORY_ENGINE=true` — Enables fact extraction + recall
3. `ENABLE_MEMORY_DECAY=true` — Enables daily memory decay
4. `ENABLE_CLONE_SCORE_EVAL=true` — Enables daily batch evaluation
5. `ENABLE_LEARNING_RULES=true` — Enables autolearning rule injection

## Background Jobs

| Job | Interval | Delay | Flag | Description |
|-----|----------|-------|------|-------------|
| #21 | 24h | 600s | `ENABLE_CLONE_SCORE_EVAL` | Daily CloneScore batch eval |
| #22 | 24h | 630s | `ENABLE_MEMORY_DECAY` | Daily memory decay |

## API Endpoints

### CloneScore
```
GET  /clone-score/{creator_id}          # Latest score + trend
GET  /clone-score/{creator_id}/history  # 30-day score history
POST /clone-score/{creator_id}/evaluate # Trigger manual evaluation
```

### Maintenance
```
GET  /health/scheduler                  # All background job status
POST /maintenance/recalculate-scores/{creator}  # Manual score recalc
```

## CLI Tools

### Baseline Measurement
```bash
python scripts/echo_baseline.py --creator-id stefano_auto
python scripts/echo_baseline.py --creator-id stefano_auto --sample-size 100
python scripts/echo_baseline.py --creator-id stefano_auto --output-dir results/
```

Requires: `DATABASE_URL`, `OPENAI_API_KEY`

## Key Files

| File | Purpose |
|------|---------|
| `services/clone_score_engine.py` | CloneScore 6-dimension evaluation |
| `services/memory_engine.py` | Fact extraction, search, recall, decay |
| `services/llm_judge.py` | GPT-4o-mini judge component |
| `api/routers/clone_score.py` | API endpoints |
| `api/startup.py` | Background jobs (lines 691-788) |
| `tests/echo/conftest.py` | Test fixtures, data classes |
| `tests/echo/test_validation_local.py` | Local validation tests |
| `tests/echo/test_baseline_measurement.py` | E2E mock evaluation tests |
| `scripts/echo_baseline.py` | Production baseline CLI |

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `CLONE_SCORE_JUDGE_MODEL` | `gpt-4o-mini` | LLM model for judge |
| `CLONE_SCORE_JUDGE_TIMEOUT` | `15` | Judge call timeout (seconds) |
| `MEMORY_MAX_FACTS_PER_EXTRACTION` | `5` | Max facts per LLM extraction |
| `MEMORY_MAX_FACTS_IN_PROMPT` | `10` | Max facts injected into DM prompt |
| `MEMORY_MIN_SIMILARITY` | `0.4` | Minimum cosine similarity for recall |
| `MEMORY_DECAY_HALF_LIFE_DAYS` | `30` | Base half-life for decay |
| `MEMORY_DECAY_THRESHOLD` | `0.1` | Below this, memory is deactivated |

## Performance Optimizations (FASE 8)

1. **RAG skip for simple intents** — Greeting/farewell/thanks skip RAG (~200-400ms saved)
2. **Few-shot cap** — Max 2 examples from calibration (was unbounded)
3. **System prompt cap** — Truncated to ~6000 tokens before LLM call
4. **Memory context cap** — Reduced from 1500 to 1200 chars (~300 tokens)
5. **Judge prompt cap** — Truncated to ~2000 tokens to control cost
