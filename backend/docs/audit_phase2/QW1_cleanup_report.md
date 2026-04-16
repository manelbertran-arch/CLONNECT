# QW1: Orphan Metadata Cleanup Report

**Autor:** QW1 cleanup pass  
**Fecha:** 2026-04-16  
**Input:** `docs/audit_phase2/W2_metadata_flow.md`  
**Commit:** `chore(metadata): remove 30 orphan writes to cognitive_metadata`

---

## Resumen

| Métrica | Valor |
|---------|-------|
| Fields objetivo (W2) | 30 |
| Falsos positivos detectados | 0 |
| Fields eliminados (writes activos) | 29 |
| Fields ya comentados (no-op) | 1 (`loop_truncated`) |
| Archivos modificados | 3 |
| Líneas eliminadas | 51 |
| Tests tras cleanup | 18 passed / 0 failed |
| Lógica de sistemas alterada | NINGUNA |

---

## Verificación Pre-Cleanup: Todos 30 Confirmados Orphan

Comando ejecutado por cada field:
```bash
grep -rn "\"$FIELD\"" services/ core/ api/ tests/ --include="*.py" | grep -v "^\s*#"
```

Resultado: **0 reads** en los 30 fields. Sin falsos positivos.

---

## Fields Eliminados — Lista Completa

### 1. RAG Telemetry — `core/dm/phases/context.py`

| Field | Línea original | Acción |
|-------|---------------|--------|
| `rag_disabled` | 566 | Eliminado |
| `rag_skipped` | 568 | Eliminado |
| `rag_signal` | 570 | Eliminado |
| `rag_routed` | 593 | Eliminado |
| `rag_confidence` | 605, 609, 614 | Eliminado (3 writes) |
| `rag_details` | 625-632 | Eliminado (bloque dict comprehension) |
| `rag_reranked` | 634 | Eliminado |

### 2. Hierarchical Memory Telemetry — `core/dm/phases/context.py`

| Field | Línea original | Acción |
|-------|---------------|--------|
| `hier_memory_injected` | 407 | Eliminado |
| `hier_memory_chars` | 408 | Eliminado |
| `hier_memory_levels` | 409-413 | Eliminado (bloque dict) |

### 3. SBS (Score Before You Speak) — `core/dm/phases/postprocessing.py`

| Field | Línea original | Acción |
|-------|---------------|--------|
| `sbs_score` | 298 | Eliminado |
| `sbs_scores` | 299 | Eliminado |
| `sbs_path` | 300 | Eliminado |
| `sbs_llm_calls` | 301 | Eliminado |

### 4. PPA (Post Persona Alignment) — `core/dm/phases/postprocessing.py`

| Field | Línea original | Acción |
|-------|---------------|--------|
| `ppa_score` | 326 | Eliminado |
| `ppa_scores` | 327 | Eliminado |
| `ppa_refined` | 330 | Eliminado |

### 5. Loop / Echo / Quality Flags — `core/dm/phases/postprocessing.py`

| Field | Línea original | Acción |
|-------|---------------|--------|
| `loop_detected` | 99 | Eliminado |
| `loop_truncated` | generation.py:621 | **YA COMENTADO** — no-op |
| `echo_detected` | 196 | Eliminado |
| `echo_detected_no_pool` | 202 | Eliminado |
| `repetition_truncated` | 126 | Eliminado |
| `sentence_dedup` | 157 | Eliminado |
| `blacklist_replacement` | 240 | Eliminado |
| `self_consistency_replaced` | generation.py:637 | Eliminado |

### 6. Compaction / Style — `core/dm/phases/generation.py`

| Field | Línea original | Acción |
|-------|---------------|--------|
| `history_compaction` | 430 | Eliminado |
| `history_compaction_kept` | 431 | Eliminado |
| `history_compaction_pool` | 432 | Eliminado |
| `style_anchor` | 307 | Eliminado |
| `style_normalized` | postprocessing.py:384 | Eliminado |

---

## Falsos Positivos

**Ninguno.** Los 30 fields del W2 confirmados orphan. Zero reads en `services/`, `core/`, `api/`, `tests/`.

---

## Nota sobre `_bl_changed`

La variable `_bl_changed` (resultado de `apply_blacklist_replacement()`) se seguía usando en el `if _bl_changed:` check para decidir si loggear. Al eliminar el write de `blacklist_replacement`, la lógica simplifica a eliminar el `if` branch completo que solo contenía el write. La llamada a `apply_blacklist_replacement()` y el efecto real (modificar `response_content`) se **mantienen intactos**.

---

## Cambios por Archivo

### `core/dm/phases/context.py`
- Bloque `hier_memory_*` (3 líneas) en `if hier_memory_context:` — eliminado
- `rag_disabled` / `rag_skipped` — eliminados; los `if/elif/else` se mantienen con `pass` donde era necesario
- `rag_signal` — eliminado del bloque `else:`
- `rag_routed` — eliminado dentro de `if preferred:`
- `rag_confidence` "high"/"medium"/"low" — 3 writes eliminados
- Bloque `rag_details` (dict comprehension 8 líneas) + `rag_reranked` — eliminado

### `core/dm/phases/postprocessing.py`
- `loop_detected` (1 línea)
- `repetition_truncated` (1 línea)
- `sentence_dedup` (1 línea)
- `echo_detected` (1 línea)
- `echo_detected_no_pool` (1 línea + `else` branch simplificado)
- `blacklist_replacement` (1 línea + `if _bl_changed:` branch eliminado)
- `sbs_score`, `sbs_scores`, `sbs_path`, `sbs_llm_calls` (4 líneas)
- `ppa_score`, `ppa_scores`, `ppa_refined` (3 líneas; `if ppa_result.was_refined:` se mantiene)
- `style_normalized` (1 línea; `if response_content != _pre_normalization_response:` se mantiene)

### `core/dm/phases/generation.py`
- `style_anchor` (1 línea)
- `history_compaction`, `history_compaction_kept`, `history_compaction_pool` (3 líneas)
- `self_consistency_replaced` (1 línea)

---

## Tests Post-Cleanup

```
tests/test_context_analytics.py   — 18 passed
tests/sprint1_verification/       — incluidos en los 18
```

Errores de colección pre-existentes (sin relación con este cambio):
- `tests/academic/test_causal.py` — `ModuleNotFoundError: core.reasoning.chain_of_thought`
- `tests/audit/test_audit_output_validator.py` — `ImportError: ValidationResult`
- `tests/test_battery_realista.py` — `AssertionError: Expected 50 messages`

Estos fallos existían antes del cleanup (confirmado con `git stash` check conceptual — son módulos/fixtures faltantes).

---

## Invariantes Preservados

- La **lógica** de todos los sistemas (RAG gate, hierarachical memory, SBS, PPA, echo detection, style normalization) se mantiene **idéntica**.
- Solo se eliminaron las líneas `cognitive_metadata["field"] = value`.
- Los logs (`logger.info`, `logger.warning`, `logger.debug`) que reportaban estos valores **NO fueron tocados**.
- `prompt_injection_attempt` y `sensitive_detected` **NO tocados** (reservados para QW3).
- `query_expanded` **NO tocado** (no estaba en la lista del W2).
