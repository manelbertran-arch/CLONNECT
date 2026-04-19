# ARC5 Phase 2 — Typed Metadata Rollout Guide

## What was shipped

Three DM pipeline phases now emit Pydantic-typed metadata when `USE_TYPED_METADATA=true`:

| Phase | Key written | Model |
|-------|-------------|-------|
| Detection (phase_detection) | `cognitive_metadata["_arc5_detection_meta"]` | `DetectionMetadata` |
| Generation (phase_llm_generation) | `cognitive_metadata["_arc5_generation_meta"]` | `GenerationMetadata` |
| Post-gen (phase_postprocessing) | `cognitive_metadata["_arc5_postgen_meta"]` | `PostGenMetadata` |

Postprocessing assembles all three into `MessageMetadata` and writes to `msg_metadata["_arc5_typed_metadata"]` (JSONB column).

## Flag

```
USE_TYPED_METADATA=true   # activate typed writes (default: false)
```

Add to Railway env vars. Safe to add/remove without deploy — evaluated at startup from `FeatureFlags`.

## Activation checklist

- [ ] Verify `USE_TYPED_METADATA=false` baseline in prod (no typed data in `msg_metadata`)
- [ ] Enable `USE_TYPED_METADATA=true` on one creator (Railway env override)
- [ ] Monitor Railway logs for `[ARC5] * metadata failed` warnings
- [ ] Query a sample of messages: `SELECT msg_metadata->'_arc5_typed_metadata' FROM messages WHERE creator_id = '<uuid>' LIMIT 10;`
- [ ] Verify `schema_version: 1` in all rows
- [ ] Verify `post_gen.safety_status` is one of `OK / BLOCK / REGEN`
- [ ] Soak 24h → enable globally

## Rollback

Set `USE_TYPED_METADATA=false` (or remove the env var). No migration needed — typed data is additive inside the existing JSONB column. Legacy rows without `_arc5_typed_metadata` key remain valid.

## Known limitations (Phase 2)

- `detected_intent` is always `"other"` — intent resolved in context phase, not detection. Will be wired in Phase 3.
- `lang_detected` is `"unknown"` until context phase runs (same reason).
- `ScoringMetadata` is absent — score values not accessible at postprocessing time. Requires scoring pipeline refactor.
- `prompt_tokens` / `completion_tokens` are `0` — Gemini provider doesn't return token breakdown per-call.

## Files changed

- `core/feature_flags.py` — added `typed_metadata: bool` flag (`USE_TYPED_METADATA`)
- `core/dm/phases/detection.py` — timing, security tracking, `_emit_arc5_detection_meta()` closure
- `core/dm/phases/generation.py` — retry counter, `_arc5_context_budget_pct`, `GenerationMetadata` build
- `core/dm/phases/postprocessing.py` — safety status tracking, `PostGenMetadata`, `_dm_metadata` enrichment
- `tests/metadata/test_phase_integration.py` — 9 integration tests (flag off/on, security flags, carry-through)
