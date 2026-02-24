# ECHO Engine Runbook

## Activation Steps

### Step 1: Enable CloneScore (real-time, logging only)
```bash
railway variables set ENABLE_CLONE_SCORE=true
```
- **What it does**: Enables real-time `style_fidelity` scoring in the DM pipeline
- **Impact**: Logging only, no user-facing changes
- **Verify**: Check logs for `[CLONE_SCORE]` entries

### Step 2: Enable Memory Engine
```bash
railway variables set ENABLE_MEMORY_ENGINE=true
```
- **What it does**: Enables fact extraction from conversations and semantic recall
- **Impact**: Adds memory context to DM prompts (non-blocking)
- **Verify**: Check logs for `[MemoryEngine]` entries

### Step 3: Enable Memory Decay
```bash
railway variables set ENABLE_MEMORY_DECAY=true
```
- **What it does**: Daily job deactivates stale memories via Ebbinghaus decay
- **Impact**: Background job, no user-facing changes
- **Verify**: `GET /health/scheduler` shows memory_decay as active

### Step 4: Enable CloneScore Daily Eval
```bash
railway variables set ENABLE_CLONE_SCORE_EVAL=true
```
- **What it does**: Daily batch evaluation of all active creators
- **Impact**: Stores scores in DB, logs warnings for low scores
- **Cost**: ~$0.03/creator/day (50 LLM judge calls)
- **Verify**: `GET /health/scheduler` shows clone_score as active

### Step 5: Enable Learning Rules (optional)
```bash
railway variables set ENABLE_LEARNING_RULES=true
```
- **What it does**: Injects learned rules from creator corrections into DM prompts
- **Impact**: Modifies DM generation behavior
- **Verify**: Check logs for `[LEARNING]` entries

## Monitoring

### Health Check
```bash
curl https://api.clonnectapp.com/health/scheduler
```
Look for:
```json
{
  "clone_score_daily": {"status": "running", "last_run": "..."},
  "memory_decay": {"status": "running", "last_run": "..."}
}
```

### Score Monitoring
```bash
# Latest score for a creator
curl https://api.clonnectapp.com/clone-score/stefano_auto

# Score history (30 days)
curl https://api.clonnectapp.com/clone-score/stefano_auto/history
```

### Baseline Measurement (manual)
```bash
cd backend
python scripts/echo_baseline.py --creator-id stefano_auto --sample-size 50
```

## Alert Thresholds

| Level | Overall Score | Action |
|-------|--------------|--------|
| Excellent | >= 90 | No action |
| Good | >= 75 | No action |
| Acceptable | >= 60 | Monitor |
| Needs Improvement | >= 40 | Investigate, check per-dimension |
| Critical | < 40 | Urgent: check safety, knowledge |

### Per-Dimension Alerts
- **safety_score < 40**: CRITICAL — Check for offensive content, leaked PII
- **knowledge_accuracy < 40**: HIGH — Check RAG index, product data freshness
- **persona_consistency < 40**: MEDIUM — Check Doc D, personality extraction
- **style_fidelity < 40**: LOW — Check tone profile, calibration data
- **tone_appropriateness < 40**: MEDIUM — Check lead stage detection
- **sales_effectiveness < 40**: LOW — Check copilot approval rates

## Common Failure Modes

### CloneScore returns all 50.0
**Cause**: LLM judge unavailable (OPENAI_API_KEY missing or quota exceeded)
**Fix**: Check `OPENAI_API_KEY` env var, verify OpenAI billing

### Memory Engine not extracting facts
**Cause**: `ENABLE_MEMORY_ENGINE=false` or Gemini provider down
**Fix**: Check flag, check logs for `[MemoryEngine]` errors

### Memory Decay not running
**Cause**: `ENABLE_MEMORY_DECAY=false` or no active creators with bot_active=true
**Fix**: Check flag, verify creators table

### High LLM costs
**Cause**: Large batch size or uncapped prompts
**Fix**: Reduce `sample_size` in daily job, verify prompt truncation is active

### Score drop after deploy
**Possible causes**:
1. Personality data changed (Doc D update)
2. Tone profile regression
3. New products not in RAG
4. Calibration file updated

**Debug**:
```bash
# Check personality
curl https://api.clonnectapp.com/debug/agent-config/stefano_auto

# Check system prompt
curl https://api.clonnectapp.com/debug/system-prompt/stefano_auto

# Manual evaluation
python scripts/echo_baseline.py --creator-id stefano_auto
```

## Rollback

To disable all ECHO features:
```bash
railway variables set ENABLE_CLONE_SCORE=false
railway variables set ENABLE_CLONE_SCORE_EVAL=false
railway variables set ENABLE_MEMORY_ENGINE=false
railway variables set ENABLE_MEMORY_DECAY=false
railway variables set ENABLE_LEARNING_RULES=false
```

## Cost Estimation

| Component | Per Creator/Day | Notes |
|-----------|----------------|-------|
| CloneScore daily eval | ~$0.03 | 50 samples x 3 LLM calls x $0.0002/call |
| Memory extraction | ~$0.01 | Per active conversation |
| LLM Judge | ~$0.0002 | Per judge call (GPT-4o-mini) |
| Memory decay | $0 | No LLM, pure DB operations |

**Total per creator**: ~$0.04-0.05/day with defaults
