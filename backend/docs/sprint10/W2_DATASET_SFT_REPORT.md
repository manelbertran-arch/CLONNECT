# W2 Report — SFT v4 Dataset (Sprint 10)

## Output

`data/dpo/trl/sft_v4_multiturn.jsonl` — 10,000 records, 186 MB

## Bug fixes applied

| Bug | Fix | Result |
|-----|-----|--------|
| BUG-12: 100% 1-turn | 60%/40% split target | **31.4% multi-turn** (above 25% min) |
| BUG-13: 8.1% asst >200 chars | Hard filter MAX_ASST_CHARS=200 | **0 violations** |
| BUG-14: 1 system prompt variant | Rotate 2 existing Doc D versions | **V0: 50.7%, V1: 49.3%** |

## Dataset stats

```
Total records:    10,000
Single-turn:       6,856 (68.6%)
Multi-turn:        3,144 (31.4%)

Turn pair distribution:
  1-pair (2 msgs):  6,856  (single-turn from SFT v3)
  2-pair (4 msgs):  3,120  (multi-turn 4-window)
  3-pair (6 msgs):     24  (multi-turn 6-window)

Assistant length:
  min=1, max=200, mean=52.9, median=39.0
```

## Data sources

### Single-turn (SFT v3, filtered)
- Source: `data/dpo/trl/sft_v3_clean.jsonl` (9,268 records)
- After BUG-13 filter: 8,515 valid records
- Dropped: 753 records with assistant >200 chars (8.1%)

### Multi-turn (DB messages)
- Source: `messages` table, `leads` → creator `iris_bertran`
- Total messages in DB: 60,754
- Total conversations: 1,681
- Conversations with valid windows: 625
- Total windows extracted: 3,144
- Max per-conversation cap: adaptive (proportional to conv length)

### System prompt variants
- V0: `data/personality_extractions/iris_bertran/doc_d_bot_configuration_sprint7_freeze.md` (7,154 chars)
  - "Doc D v2 destilado" — sprint7 freeze, validated baseline
- V1: `doc_d` from DB (truncated to 30,000 chars)
  - Current live system prompt — more complete version
- Note: `doc_d_v1` (47K chars) regex extraction failed on this build; V1 uses `doc_d`.
  Re-run with --debug-variants if 3rd variant needed.

## Multi-turn gap analysis

Target was 40% (4,000 records). Achieved 31.4% (3,144 records). Gap causes:
1. **After merge**: many conversations collapse — consecutive user/asst messages merged
   → 992 conversations become <4 messages after merge (single-burst DMs)
2. **Strict alternation filter**: only strictly alternating u→a→u→a windows accepted
   → `[a,u,a,u]` conversations lose their first window
3. **BUG-13 filter**: conversations with long assistant responses discarded

31.4% is above the 25% minimum. Achieving 40% would require:
- Synthetic augmentation (out of scope W2)
- OR scraping more conversations from other creators
- OR relaxing the alternation requirement (risk: training on non-chat format)

## Known limitations

1. **Instagram media placeholders**: some user messages contain `[Media/Attachment]`,
   `Sent a photo`, `Mentioned you in their story` (Instagram metadata). These pass
   through the media filter since they're not in the `[audio|video]` pattern.
   Impact: model may learn to respond to "Sent a photo" messages, which is realistic.

2. **Long conversations**: conversations with 100-4828 messages are sampled with a
   higher cap (2x base) but not fully exhausted. Rebalancing is not needed for v4.

3. **V2 system variant**: doc_d_v1 (full, 47K chars) extraction failed this run.
   Current 2-variant rotation is sufficient for BUG-14 fix.

## Script

`scripts/finetuning/build_sft_v4.py`

```bash
# Regenerate
cd ~/Clonnect/backend
set -a && source .env && set +a
.venv/bin/python3.11 scripts/finetuning/build_sft_v4.py

# Dry run
.venv/bin/python3.11 scripts/finetuning/build_sft_v4.py --dry-run

# Different target
.venv/bin/python3.11 scripts/finetuning/build_sft_v4.py --target 15000
```

## Validation

All validation checks passed:
- ✓ BUG-13: 0 asst >200 chars violations
- ✓ BUG-12: 31.4% multi-turn (>25% minimum)
- ✓ BUG-14: 2 system variants, balanced ~50/50
- ✓ Smoke tests: 10/10

## Branch

`sprint10/w2-sft-multiturn`
