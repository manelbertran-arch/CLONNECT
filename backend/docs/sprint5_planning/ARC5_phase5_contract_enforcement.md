# ARC5 Phase 5 — Contract Enforcement CI

**Sprint:** 5 / ARC5 Phase 5  
**Status:** Implemented  
**Script:** `scripts/ci/contract_enforcement.py`  
**GitHub Action:** `.github/workflows/contract_enforcement.yml`

---

## Why CI Checks (Zero Hardcoding Principle)

The ARC5 design established that metadata is a "vertedero" without contract: anyone can write
`metadata["x"] = ...` anywhere in the pipeline without schema, reader, or metric. Over 6 months
this grew from 49 used fields to 114 total (65 orphans at peak, 35 post-QW1).

The CI contract enforcement script ensures that going forward:
- **No new orphan fields** can be introduced silently.
- **No direct prometheus_client metric classes** are created outside the central registry.
- **No magic numbers** creep into pipeline hot paths.

This enforces the contracts defined in ARC5 Phases 1–3 at the code boundary, before merge.

---

## What the Script Checks

### CHECK 1 — Direct metadata assignment (BLOCKING in --strict)

**Pattern detected:**
```python
msg.metadata["detection_ts"] = "..."   # ❌ direct dict write
message.metadata.update({"key": val}) # ❌ direct dict update
```

**Required fix:**
```python
from core.metadata.serdes import write_metadata
from core.metadata.helpers import update_detection_metadata
from core.metadata.models import DetectionMetadata

await update_detection_metadata(session, msg.id, DetectionMetadata(...))  # ✅
```

**Exclusions:** `tests/`, `scripts/`, `alembic/`, `ops/`

---

### CHECK 2 — Counter/Gauge/Histogram without emit_metric (WARNING only)

**Pattern detected:**
```python
from prometheus_client import Counter

MY_COUNTER = Counter("my_metric", "desc", ["creator_id"])  # ❌ direct instantiation
MY_COUNTER.labels(creator_id="iris").inc()
```

**Required fix:**
```python
# 1. Add to core/observability/metrics.py _METRIC_SPECS
("my_metric", Counter, "desc", ["creator_id"], {})

# 2. Use emit_metric everywhere
from core.observability.metrics import emit_metric
emit_metric("my_metric", creator_id="iris")  # ✅
```

**Exempt:** `core/observability/metrics.py` (the registry itself)

---

### CHECK 3 — Define-but-never-read metadata fields (BLOCKING in --strict)

**Detected when:** A field is declared in `DetectionMetadata`, `ScoringMetadata`,
`GenerationMetadata`, or `PostGenMetadata` but no reader, `emit_metric` call, or
`deprecated:` annotation exists anywhere in the codebase.

**Fix options:**

| Action | When to use |
|--------|-------------|
| Add a reader (`.field_name` access) | Field has downstream consumers |
| `emit_metric("field_name", ...)` | Field drives a Prometheus metric |
| `# deprecated: field_name` in models.py | Field is legacy, schedule for removal |
| Delete the field | Field is truly orphaned |

---

### CHECK 4 — Magic numbers in pipeline code (WARNING only)

**Pattern detected:**
```python
if len(msg.content) > 4096:       # ❌ magic number
    truncate(msg)
```

**Whitelist** (never flagged): `0, 1, -1, 100, 1000, 0.0, 1.0, 0.5, 2, 3, 4, 5`

**Required fix:**
```python
MAX_CONTENT_CHARS = 4096  # or read from config

if len(msg.content) > MAX_CONTENT_CHARS:  # ✅
    truncate(msg)
```

**Scan dirs:** `core/dm/`, `core/generation/`, `core/metadata/`, `core/observability/`

---

## How to Skip a Legitimate Case

Add `# noqa: contract` at the end of the line:

```python
msg.metadata["foo"] = legacy_value  # noqa: contract
```

Use sparingly — only for migration shims and truly exceptional cases. Document _why_
in a comment before the line.

---

## CI Behaviour

| Mode | CHECK 1 | CHECK 2 | CHECK 3 | CHECK 4 |
|------|---------|---------|---------|---------|
| `--strict` (CI PR gate) | ❌ FAIL | ⚠️ WARN | ❌ FAIL | ⚠️ WARN |
| informative (default) | ⚠️ WARN | ⚠️ WARN | ⚠️ WARN | ⚠️ WARN |

The GitHub Action runs `--strict` on every PR touching `core/**`, `services/**`, or `api/**`.

---

## Running Locally

```bash
# Informative mode (reports all violations, always exits 0)
python scripts/ci/contract_enforcement.py

# Strict mode (exits 1 if CHECK 1 or CHECK 3 has errors)
python scripts/ci/contract_enforcement.py --strict

# Run tests
.venv/bin/python3.11 -m pytest tests/ci/ -xvs
```
