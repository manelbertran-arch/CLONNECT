# ARC3 Phase 1 — CCEE Validation BLOCKED

**Date:** 2026-04-19  
**Branch:** feature/arc3-phase1-distill-validation  
**Commit checked:** e5e718d2 (HEAD on main after ARC4 merge, ARC3 Phase 1 at c88edc4f)  
**Status:** BLOCKED — validation cannot proceed

---

## Resumen

La validación CCEE de ARC3 Phase 1 (distill prompt v1) fue lanzada pero no puede ejecutarse. El flag `USE_DISTILLED_DOC_D` existe y se lee correctamente, pero **no está conectado al loader de Doc D**. Cualquier comparación OFF vs ON produciría resultados idénticos.

---

## Causa raíz

### `core/dm/agent.py` líneas 189–195:

```python
# ARC3 Phase 1 shadow hook — USE_DISTILLED_DOC_D default OFF.
# Full distilled-content substitution wired in Phase 3.
if style_prompt and _flags.use_distilled_doc_d:
    from services.style_distill_service import StyleDistillService  # noqa: F401
    # Phase 3 will inject distilled Doc D here once DB session
    # is available in this context. For now, read is a no-op.
    pass
```

El bloque detecta el flag activado pero ejecuta `pass`. El `style_prompt` (Doc D) que llega a `core/dm/phases/context.py` **nunca es sustituido** por la versión destilada.

### `core/dm/phases/context.py`:

Cero referencias a `USE_DISTILLED_DOC_D`. El `style_prompt` se pasa directamente al constructor de contexto sin ningún condicional de distillado.

---

## Lo que falta

Para que la validación sea posible, alguien debe conectar el flag al loader real. Pseudocódigo de lo que Phase 3 debe implementar:

```python
# core/dm/agent.py — donde se carga style_prompt
if style_prompt and _flags.use_distilled_doc_d:
    distilled = await StyleDistillService(db_session).get_or_generate(creator_id, style_prompt)
    if distilled:
        style_prompt = distilled
        logger.info(f"USE_DISTILLED_DOC_D: substituted Doc D with distill ({len(distilled)} chars)")
```

**Bloqueante:** `db_session` no está disponible en ese punto del agente — resolverlo es responsabilidad de ARC3 Phase 3.

---

## Próximos pasos

| Paso | Descripción | Prerequisito |
|------|-------------|--------------|
| a | Worker A (ARC3 Phase 2 Compactor Shadow) termina y mergea a main | En curso — otra rama |
| b | Worker separado conecta `USE_DISTILLED_DOC_D` al loader en `agent.py` | Worker A mergeado (evitar conflicto en `context.py`) |
| c | Re-lanzar esta validación (`feature/arc3-phase1-distill-validation`) | Paso b completado |

**No lanzar paso b mientras Worker A esté activo:** ambos modifican `core/dm/agent.py` / `core/dm/phases/context.py`.

---

## Recomendación para ARC3 Phase 3

La **primera tarea de Phase 3** debe ser la conexión del flag antes de cualquier live rollout:

1. Resolver disponibilidad de `db_session` en `agent.py` en el punto de carga de `style_prompt`
2. Inyectar la sustitución real (no `pass`)
3. Re-ejecutar esta validación CCEE (20 casos, OFF vs ON, iris_bertran)
4. Solo si Δ composite ≥ −3 y Δ S1 ≥ −5 → activar flag en prod

---

## Archivos relevantes

| Archivo | Estado |
|---------|--------|
| `core/feature_flags.py:113` | Flag definido, default OFF ✅ |
| `core/dm/agent.py:189-195` | Detecta flag pero no-op (`pass`) ❌ |
| `core/dm/phases/context.py` | Sin referencia a distill ❌ |
| `services/style_distill_service.py` | Servicio completo y funcional ✅ |
| `scripts/distill_style_prompts.py` | Script batch listo ✅ |
| `alembic/versions/` | Migración `creator_style_distill` mergeada ✅ |
