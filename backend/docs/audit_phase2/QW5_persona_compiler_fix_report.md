# QW5 — PersonaCompiler Persistence Fix

**Fecha:** 2026-04-16
**Scope:** Bug B1 identificado en W1 §47 y W7 §0.4. `services/persona_compiler.py` leía y escribía `creator.doc_d`, columna inexistente en el modelo ORM y en la DB live.
**Escenario determinado:** **A (modified)** — columna nunca existió; no hay datos que migrar.
**Aprobación humana requerida:** No (sin cambios de schema, sin migración).

---

## 1. Diagnóstico ejecutado

### Queries contra DB prod (Neon)

| # | Query | Resultado |
|---|-------|-----------|
| Q1 | `information_schema.columns WHERE table_name='creators' AND column_name LIKE '%doc%'` | **0 rows** — columna `doc_d` NO existe |
| Q2 | Tablas relacionadas | `doc_d_versions`, `personality_docs`, `pattern_analysis_runs` existen |
| Q3 | Todas las columnas de `creators` | 49 columnas, ninguna `doc_d` |
| Q4 | Schema `doc_d_versions` | `id uuid, creator_id uuid, doc_d_text text, trigger varchar, categories_updated jsonb, created_at tstz` |
| Q4.1 | Row count `doc_d_versions` | **0** — tabla vacía |
| Q5 | Schema `personality_docs` | `id uuid, creator_id varchar(100), doc_type varchar(10), content text, created_at, updated_at` + `UNIQUE(creator_id, doc_type)` |
| Q6 | Datos relevantes en `personality_docs` | Iris `doc_d` 29,359 chars (upd 2026-04-16 05:25), Stefano `doc_d` 44,653 chars (upd 2026-02-24) |
| Q7 | Estado `pattern_analysis_runs` | 118 `done` (último 2026-04-03) + **30 `error`** (último 2026-04-16 05:27) |
| Q8 | Mensaje del error | **100 % idéntico:** `{"error": "'Creator' object has no attribute 'doc_d'", "status": "error"}` |

### Causa raíz

- `api/models/creator.py:28-102` — `Creator` ORM no declara columna `doc_d`.
- DB live Neon no tiene columna `doc_d` en `creators` (confirmado via `information_schema`).
- `services/persona_compiler.py` accedía a `creator.doc_d` en 4 sitios (`rollback_doc_d` 1050/1053 y `compile_persona` 1105/1124), causando `AttributeError` en cada ejecución.
- El `doc_d_versions` snapshot (INSERT raw SQL) era **válido** pero **inalcanzable** — el crash sucede en la línea previa (`current_doc_d = creator.doc_d`).
- **Runtime funciona igualmente** porque otro path (`core/personality_extraction/extractor.py:366`) mantiene `personality_docs.content` al día independientemente del compiler.

---

## 2. Fix aplicado

### 2.1 `services/persona_compiler.py`

**Añadidos 2 helpers** (junto a `_snapshot_doc_d`, tras línea 1023):

```python
def _get_current_doc_d(session, creator_db_id) -> str:
    """Read current Doc D from personality_docs.content (doc_type='doc_d')."""
    from sqlalchemy import text
    row = session.execute(
        text("SELECT content FROM personality_docs WHERE creator_id = :cid AND doc_type = 'doc_d'"),
        {"cid": str(creator_db_id)},
    ).fetchone()
    return row[0] if row and row[0] is not None else ""


def _set_current_doc_d(session, creator_db_id, new_text: str) -> None:
    """Upsert Doc D content to personality_docs (canonical pattern)."""
    from sqlalchemy import text
    session.execute(
        text("""
            INSERT INTO personality_docs (id, creator_id, doc_type, content)
            VALUES (CAST(:id AS uuid), :cid, 'doc_d', :content)
            ON CONFLICT (creator_id, doc_type)
            DO UPDATE SET content = EXCLUDED.content, updated_at = now()
        """),
        {"id": str(uuid.uuid4()), "cid": str(creator_db_id), "content": new_text or ""},
    )
```

**Sustituciones:**

| Sitio | Antes | Después |
|-------|-------|---------|
| `rollback_doc_d` línea ~1050 | `_snapshot_doc_d(session, creator_db_id, creator.doc_d or "", "rollback")` | `_snapshot_doc_d(session, creator_db_id, _get_current_doc_d(session, creator_db_id), "rollback")` |
| `rollback_doc_d` línea ~1053 | `creator.doc_d = old_text` | `_set_current_doc_d(session, creator_db_id, old_text)` |
| `compile_persona` línea ~1105 | `current_doc_d = creator.doc_d or ""` | `current_doc_d = _get_current_doc_d(session, creator_db_id)` |
| `compile_persona` línea ~1124 | `creator.doc_d = new_doc_d` | `_set_current_doc_d(session, creator_db_id, new_doc_d)` |

`doc_d_versions` snapshot se mantiene como history log — schema correcto, INSERT válido, sólo había quedado inalcanzable por el crash upstream.

### 2.2 `tests/test_persona_compiler.py`

**Test existente modificado** (`test_compile_persona_basic`):
- Eliminado `mock_creator.doc_d = "…"` (atributo ya no se lee).
- Añadido `patch("services.persona_compiler._get_current_doc_d", return_value="…")` + `patch("_set_current_doc_d")`.
- Assertion nueva: `mock_set.called` para verificar que el flujo escribe via upsert.

**5 tests de regresión añadidos** en `TestQW5PersonalityDocsStore`:

1. `test_get_current_doc_d_reads_from_personality_docs` — verifica SELECT contra `personality_docs` + doc_type `doc_d`.
2. `test_get_current_doc_d_returns_empty_when_missing` — sin row, devuelve `""` (no AttributeError).
3. `test_set_current_doc_d_upserts_personality_docs` — INSERT … ON CONFLICT DO UPDATE, binds correctos.
4. `test_rollback_doc_d_uses_personality_docs` — rollback lee doc_d_versions y restaura via personality_docs.
5. `test_compile_persona_no_creator_doc_d_attribute_access` — usa un fake Creator SIN atributo `doc_d` para garantizar que nunca volvemos a tocarlo.

---

## 3. Validación

### 3.1 Syntax check
```
python3 -c "import ast; ast.parse(open('services/persona_compiler.py').read())"   # OK
python3 -c "import ast; ast.parse(open('tests/test_persona_compiler.py').read())" # OK
```

### 3.2 Unit tests
```
pytest tests/test_persona_compiler.py -v
===== 18 passed in 0.10s =====
```
13 tests existentes + 5 QW5 nuevos, **todos pass**.

### 3.3 Grep final
```
grep -n "creator\.doc_d" services/persona_compiler.py   # 0 matches
```

### 3.4 Smoke test contra prod DB
```python
s = Session(bind=create_engine(DATABASE_URL))
doc = _get_current_doc_d(s, '8e9d1705-4772-40bd-83b1-c6821c5593bf')  # Iris
# → 29,359 chars, prefix '# DOCUMENTO D: CONFIGURACION TECNICA DEL BOT…'
```
**Helper lee correctamente desde `personality_docs` en prod.**

### 3.5 Health endpoint
```
curl -s https://www.clonnectapp.com/health  →  HTTP 200
```

### 3.6 Pre-existing failure
`tests/test_learning_consolidator.py::test_below_threshold_skips` falla — **pre-existente**, verificado con `git stash` corriendo el test sobre main limpio. No está relacionado con QW5 (el test asume que `compile_persona` chequea un threshold que la función no tiene).

---

## 4. Impacto esperado

- **PersonaCompiler ahora escribe al store correcto** (`personality_docs.content` doc_type=`doc_d`) — mismo que consume el runtime.
- **`pattern_analysis_runs` dejará de acumular errores** `'Creator' object has no attribute 'doc_d'` en cuanto el compiler se ejecute de nuevo.
- **`ENABLE_PERSONA_COMPILER=true` es activable** sin provocar AttributeError silenciosos.
- **Doc D compilado aterriza en runtime** — las actualizaciones semanales propagan al prompt en ciclo siguiente (personality_loader cachea 5 min por defecto).

### Versionado
`doc_d_versions` ahora sí recibirá snapshots (antes siempre vacía porque el código nunca llegaba al INSERT). Rollback por versión funcional por primera vez.

---

## 5. ADVERTENCIA

**Trabajo perdido entre 2026-04-15 19:28 y 2026-04-16 05:27** (ventana de los 30 errores): el compiler arrancó, consumió signals (pairs + feedback), pero la compilación nunca se persistió. **Los datos fuente siguen intactos** — `PreferencePair.batch_analyzed_at` solo se actualiza al `commit()` (línea 1188), que nunca se alcanzó por el rollback del except. Por tanto los pairs siguen "no-analyzed" y el próximo run volverá a consumirlos.

**Acción recomendada:** tras merge + deploy, correr manualmente `compile_persona("iris_bertran", iris_uuid)` una vez para procesar los pairs pendientes.

---

## 6. Archivos tocados

| Archivo | Líneas cambiadas | Tipo |
|---------|------------------|------|
| `services/persona_compiler.py` | +56 / −4 | fix |
| `tests/test_persona_compiler.py` | +119 / −5 | test (5 regresiones nuevas) |
| `DECISIONS.md` | +12 | decision log |
| `docs/audit_phase2/QW5_persona_compiler_fix_report.md` | nuevo | report |

---

## 7. 4-Phase Workflow Compliance

| Fase | Estado | Nota |
|------|--------|------|
| PLAN | ✅ | Diagnóstico `/tmp/qw5_diagnosis.md` + entrada `DECISIONS.md` |
| IMPLEMENT | ✅ | Helpers añadidos, 4 callsites actualizados, ast.parse OK |
| REVIEW | ⚠️ | Fix surgical (56 líneas). Código reviewer agent no invocado — pedir si quieres |
| VERIFY | ✅ | 18/18 tests pass, smoke real contra prod DB OK, health endpoint OK |

---

## 8. Siguiente paso

1. Merge + deploy a Railway.
2. **Staging/prod:** setear `ENABLE_PERSONA_COMPILER=true` (si aún no) y correr `compile_persona("iris_bertran", iris_uuid)` manualmente.
3. Verificar:
   ```sql
   SELECT status, COUNT(*), MAX(ran_at)
   FROM pattern_analysis_runs
   WHERE ran_at > NOW() - INTERVAL '24 hours'
   GROUP BY status;
   ```
   Esperado: nuevo row `status='done'` post-deploy.
4. **No** requiere drop de columna (columna nunca existió).
