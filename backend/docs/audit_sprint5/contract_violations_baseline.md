# ARC5 Phase 5 — Contract Violations Baseline

**Date:** 2026-04-19  
**Script:** `python scripts/ci/contract_enforcement.py` (non-strict)  
**Status:** Tech debt documented for gradual cleanup post-ARC5

---

## Summary

| Check | Type | Count | Blocking in --strict |
|-------|------|-------|----------------------|
| CHECK 1: Direct metadata assignment | ERROR | 44 | YES |
| CHECK 2: prometheus_client without emit_metric | - | 0 | WARNING |
| CHECK 3: Define-but-never-read fields | ERROR | 12 | YES |
| CHECK 4: Magic numbers in pipeline | WARNING | 262 | NO |
| **TOTAL errors** | | **56** | |
| **TOTAL warnings** | | **262** | |

---

## CHECK 1 — Direct metadata assignment (44 violations)

**Policy:** CI blocks new violations in --strict mode. Existing ones are tech debt to clean up gradually.

### Core pipeline (priority: HIGH — migrate to typed metadata Phase 2)

| File | Lines |
|------|-------|
| `core/dm/phases/detection.py` | 119, 170 |
| `core/dm/phases/context.py` | 946, 1537 |

### Non-pipeline (priority: LOW — different metadata domain)

| File | Lines | Notes |
|------|-------|-------|
| `ingestion/deterministic_scraper.py` | 501, 505, 509 | HTML scraper metadata — different domain |
| `ingestion/playwright_scraper.py` | 189 | HTML scraper metadata — different domain |
| `core/nurturing/manager.py` | 323 | Follow-up metadata — not message pipeline |
| `core/message_reconciliation/core.py` | 449, 451, 473 | Reconciliation metadata — low priority |
| `api/routers/admin/sync_dm/test_operations.py` | multiple | Admin test harness — exempt candidate |
| `api/routers/admin/sync_dm/media_operations.py` | 157, 159 | Admin operations |
| `services/llm_service.py` | 465, 466 | LLM response metadata |

**Action plan:**
1. Add `api/routers/admin/sync_dm/` to CHECK1_EXCLUDE_DIRS (admin harness, not pipeline)
2. Migrate `core/dm/phases/detection.py` + `core/dm/phases/context.py` to typed setters (ARC5 Phase 2)
3. Evaluate ingestion/* — separate metadata domain, may use `# noqa: contract`
4. Fix services/llm_service.py, core/nurturing/manager.py, core/message_reconciliation/core.py

---

## CHECK 2 — prometheus_client without emit_metric (0 violations)

**Status:** PASS — ARC5 Phase 3 successfully centralized all Prometheus metrics.

---

## CHECK 3 — Define-but-never-read metadata fields (12 violations)

These are fields declared in the Pydantic models (ARC5 Phase 1) that have no reader or metric yet.
This is expected for Phase 1 — the readers are added in Phase 2 (integration) and Phase 4 (dashboards).

| Model | Field | Action |
|-------|-------|--------|
| `DetectionMetadata` | `lang_detected` | Add reader in detection phase integration |
| `ScoringMetadata` | `scoring_ts` | Add to Grafana scoring dashboard |
| `ScoringMetadata` | `scoring_model` | Add reader in scoring integration |
| `ScoringMetadata` | `score_delta` | Add emit_metric for dashboard |
| `ScoringMetadata` | `interest_score` | Add reader in scoring integration |
| `ScoringMetadata` | `objection_score` | Add reader in scoring integration |
| `GenerationMetadata` | `generation_ts` | Add to Grafana generation dashboard |
| `PostGenMetadata` | `post_gen_ts` | Add to Grafana post-gen dashboard |
| `PostGenMetadata` | `safety_reason` | Add reader in safety filter integration |
| `PostGenMetadata` | `pii_redacted_types` | Add emit_metric for PII tracking |
| `PostGenMetadata` | `rule_violations` | `emit_metric("rule_violation_total")` — ARC4 integration |
| `PostGenMetadata` | `length_regen_triggered` | Add emit_metric for regen tracking |

**Action plan:** These will be resolved by ARC5 Phase 2 (per-phase integration) and Phase 4 (dashboards).
CI `--strict` will remain disabled for CHECK 3 until Phase 2 is complete.

---

## CHECK 4 — Magic numbers (262 warnings)

These are informational warnings. The most common categories:

- **Budget math constants** (`80`, `10`, `600`) in `core/dm/` context assembly
- **Prompt sizing constants** (token counts, character limits) in context/compaction
- **Threshold values** (similarity scores, confidence levels)

**Action plan:** No immediate action required. Extract to named constants opportunistically
when touching those files. Not a blocking issue.

---

## CI Configuration Note

The GitHub Action (`.github/workflows/contract_enforcement.yml`) runs in `--strict` mode.
With the current baseline of 56 errors, any new PR touching the pipeline that introduces
NEW violations will be blocked. Existing violations do NOT block CI.

**Recommended next steps before enabling full strict enforcement:**
1. Add admin router path to CHECK1 exclusion list
2. Complete ARC5 Phase 2 (migrate detection + generation phases to typed metadata)
3. Complete ARC5 Phase 4 (dashboards create readers for the 12 CHECK 3 fields)
4. Re-run audit: expected 0 new violations, ~20 remaining legacy ones
