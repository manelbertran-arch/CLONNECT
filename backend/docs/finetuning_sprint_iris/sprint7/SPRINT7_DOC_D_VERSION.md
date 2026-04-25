# Sprint 7 — Doc D Version Freeze (D11)

**Fecha freeze:** 2026-04-25T17:45:00+02:00  
**Branch:** `setup/sprint7-d11`  
**Estado:** ✅ Snapshot creado | ⏳ Scheduler pausa — requiere acción manual Railway

---

## 1. Doc D frozen

| Campo | Valor |
|---|---|
| **Frozen hash (SHA256)** | `25ed0a528ed04cab01730d51f6089580e59abe9d796566019b86ca26a8eea153` |
| Frozen hash path | `scripts/finetuning/.sprint7_frozen_hash` |
| Local doc_d path | `data/personality_extractions/iris_bertran/doc_d_bot_configuration.md` |
| Local doc_d bytes | 7504 |
| Snapshot local path | `data/personality_extractions/iris_bertran/doc_d_bot_configuration_sprint7_freeze.md` (disk, gitignored) |
| **DB Snapshot ID** | `fdd14e56-70f1-47f0-a34f-4eee946b4bc4` |
| DB Doc D chars | 36142 (personality_docs.content) |
| DB snapshot tag | `sprint7_freeze_pre` |
| Snapshot timestamp | 2026-04-25 ~17:45 UTC+2 |

**Nota sobre dos versiones:** La tabla `doc_d_versions` almacena el Doc D completo (36142c). El `verify_doc_d_unchanged.py` vigila el archivo local de disco (7504 bytes, versión compressed estructurada). Para training lo relevante es el DB snapshot `fdd14e56`.

---

## 2. Scheduler weekly_compilation — Pausa requerida

### Trigger identificado

`compile_persona()` se activa vía `run_weekly_recalibration()` cuando:
```python
# services/persona_compiler.py:641
if recommendations and ENABLE_PERSONA_COMPILER:
    asyncio.create_task(compile_persona(creator_id, creator_db_id))
```

También puede activarse vía JOB 19 (pattern_analyzer, cada 12h):
```python
# api/startup/handlers.py:499
enable = os.getenv("ENABLE_PATTERN_ANALYZER", "false").lower() == "true"
```

### Evidencia de drift S11

```
4 compilaciones en 24h durante Sprint 6:
  6c51ddb0 → 2026-04-23 18:05
  618280fd → 2026-04-24 13:53
  3e3c40ca → 2026-04-24 17:34
  942f850a → 2026-04-24 20:10
  c0bcbd73 → 2026-04-25 12:57  ← durante S11
```

### ⚠️ ACCIÓN MANUAL REQUERIDA (Manel)

Antes de iniciar training Sprint 7, setear en Railway:

```bash
railway variables set ENABLE_PERSONA_COMPILER=false
railway variables set ENABLE_PATTERN_ANALYZER=false
railway variables set ENABLE_COPILOT_RECAL=false
```

O equivalente vía Railway dashboard → Variables → añadir/modificar las 3 variables.

**Verificación post-pausa:**
```bash
railway logs --tail 200 | grep "PERSONA_COMPILER\|PATTERN_ANALYZER\|weekly_compilation"
# Esperado: ninguna línea con "weekly_compilation" durante 12h
```

**Estado actual:** ⏳ NO PAUSADO — pendiente ejecución manual

---

## 3. Hook pre-training

| Campo | Valor |
|---|---|
| **Script** | `scripts/finetuning/verify_doc_d_unchanged.py` |
| **Frozen hash file** | `scripts/finetuning/.sprint7_frozen_hash` |
| Test ejecutado | ✅ OK exit 0 |
| Output test | `OK: Doc D version unchanged (25ed0a528ed0...)` |

### Uso

```bash
# Ejecutar antes de lanzar training Modal:
python3 scripts/finetuning/verify_doc_d_unchanged.py

# Esperado: "OK: Doc D version unchanged (25ed0a528ed0...)"
# Exit code 0 = continuar training
# Exit code 1 = ABORT — Doc D drifted, investigar antes de entrenar
```

### Integración en workflow training

Añadir como primer paso en `scripts/finetuning/train_modal.py` o en el script de lanzamiento:

```bash
# Pre-flight Sprint 7
python3 scripts/finetuning/verify_doc_d_unchanged.py || exit 1
# Continúa solo si exit 0
bash scripts/finetuning/03_ccee_measurement.sh ...
```

---

## 4. Re-activación post-Sprint 7

Una vez completado el training y la medición FT, reactivar el scheduler:

```bash
# Reactivar en Railway (Manel ejecuta):
railway variables set ENABLE_PERSONA_COMPILER=true
railway variables set ENABLE_PATTERN_ANALYZER=true
railway variables set ENABLE_COPILOT_RECAL=true
```

Post-reactivación:
1. Verificar logs: `railway logs --tail 50 | grep PERSONA_COMPILER`
2. Snapshot nuevo Doc D post-Sprint 7: `python3 scripts/doc_d_snapshot.py --creator iris_bertran --tag sprint7_post`
3. Actualizar `.sprint7_frozen_hash` si se inicia Sprint 8 con nuevo Doc D freeze

---

## 5. Contexto D11 — Decisión integration log

**Decision ID:** D11 (presprint7/00_INTEGRATION_LOG.md)  
**Origen:** S11 baseline re-medición detectó confound −1.8 pts por Doc D drift de 4 compilaciones en 24h.  
**Rationale:** `compile_persona()` (weekly_compilation) actualiza Doc D continuamente. Sin freeze, BL y FT measurements son inconmensurables.  
**Gate Sprint 7:** `doc_d_version_id(BL_measurement) == doc_d_version_id(FT_measurement)` — obligatorio.
