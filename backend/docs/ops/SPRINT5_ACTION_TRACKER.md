# Sprint 5 — Action Tracker (post-cierre 19-abr-2026)

**Sprint 5 cerrado al ~99%** con 19+ merges a main. Items restantes son gates de calendario/validación empírica, NO trabajo pendiente.

---

## 📅 Items bloqueados por calendario

### [ ] Item 1 — ARC2 A2.6: Legacy memory systems removal

**Unblock date:** ~2026-04-26 (7 días desde ENABLE_NIGHTLY_EXTRACT_DEEP=true el 19-abr 18:30)

**Gate check command:**
```bash
cd ~/Clonnect/backend
# Verificar que scheduler ha corrido 7 noches sin error
railway logs --tail 5000 | grep -iE "nightly_extract_deep|extract_deep_scheduler" | tail -50
# Esperado: al menos 7 runs con "status=completed" y 0 con "status=failed"
```

**Criterio GO:**
- 7 ejecuciones nightly completadas
- 0 excepciones bloqueantes en logs
- `SELECT COUNT(*) FROM arc2_lead_memories WHERE memory_type IN ('objection', 'interest', 'intent_signal', 'relationship_state')` > 200

**Tareas cuando desbloquee:**
1. Eliminar `core/memory/store.py` (MemoryStore JSON)
2. Eliminar `services/conversation_memory_service.py`
3. Eliminar `core/memory/engine.py` (MemoryEngine)
4. Eliminar imports y referencias obsoletas
5. CCEE regression 50×3 + MT (confirmar composite ≥ 72.6)
6. Update DECISIONS.md

**Rollback plan:** `git revert <commit>`. Datos en arc2_lead_memories no se tocan.

---

### [ ] Item 2 — ARC3 Phase 3: Live rollout compactor + distill

**Unblock gate:**
- Bot reactivado (Stefano + Iris)
- ≥ 1,000 turnos shadow data acumulados en context_compactor_shadow_log
- Worker I APPROVE ya confirmado ✅

**Gate check command:**
```bash
.venv/bin/python3.11 << 'EOF'
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
load_dotenv()
db_url = os.getenv('DATABASE_URL')
if db_url:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        r = conn.execute(text("SELECT COUNT(*), AVG(compaction_applied::int) FROM context_compactor_shadow_log"))
        row = r.fetchone()
        print(f"Turnos shadow: {row[0]} (gate: 1000+)")
        print(f"Compaction rate: {row[1]:.2%} (gate: <15%)")
EOF
```

**Criterio GO:**
- Turnos ≥ 1,000
- Compaction rate < 15%
- Worker I APPROVE confirmado ✅

**Tareas cuando desbloquee (rollout 10→25→50→100%):**
1. Activar `USE_DISTILLED_DOC_D=true` en Railway
2. Activar `USE_COMPACTION=true` para 10% traffic primero
3. Monitor 24h: latencia, error rate, composite canary
4. Si verde → 25% → 50% → 100%
5. Documentar en DECISIONS.md

**Rollback:** desactivar flags en Railway (instantáneo).

---

## 🔓 Items bloqueados por decisión externa

### [ ] Item 3 — Grafana Cloud live setup

**Blocker:** requiere trabajo manual de Manel en UI web (30-60 min)

**Tareas:**
1. Crear cuenta en https://grafana.com/auth/sign-up (free tier)
2. Crear Prometheus data source conectando a Railway metrics endpoint
3. Importar 5 dashboards desde `ops/grafana/dashboards/*.json`:
   - `clonnect_pipeline_overview.json`
   - `clonnect_arc2_memory.json`
   - `clonnect_arc3_compactor.json`
   - `clonnect_arc1_budget.json`
   - `clonnect_business.json`
4. Importar alertas desde `ops/grafana/alerts.yaml`
5. Configurar canal notificación (email/Slack)
6. Test alerta E2E

**Runbook completo:** `docs/runbooks/grafana_cloud_setup.md`

**Cuándo hacer:** antes de reactivar bots Iris/Stefano (para tener observability desde el minuto 1).

---

### [ ] Item 4 — Reactivar bot Stefano (piloto)

**Blocker:** decisión de Manel cuándo abrir tráfico real

**Pre-check:**
- ✅ Prod healthy
- ✅ Sprint 5 code mergeado
- ✅ Distill cache populated (2266→1242 chars, 55%)
- ⚠️ Grafana Cloud live recomendado (Item 3)

**Proceso:**
1. `UPDATE creators SET autopilot_enabled = true WHERE username = 'stefanobonanno'`
2. Monitor 48-72h: error rate, latencia P95, primeros turnos reales
3. Si estable → Item 5

---

### [ ] Item 5 — Reactivar bot Iris

**Blocker:** 48-72h Stefano estable

**Proceso:** análogo a Item 4.

---

## 🟡 Items decisión estratégica

### [ ] Item 6 — ARC4 Phase 3-5 post-fine-tuning

**Decisión documentada:** commit `aaf54f46` DECISIONS.md — aplazada hasta post-FT.

**Cuándo revisitar:** cuando modelo fine-tuned esté serving (Sprint 6+).

**Razón:** 6/7 mutations PROTECTIVE con Gemma-4-31B base (Δ K1 hasta -43). FT probablemente las haga innecesarias.

**Tareas cuando FT listo:**
1. Re-medir las 7 mutations con modelo FT (shadow runs análogos a Worker B)
2. Clasificar: PROTECTIVE/NEUTRAL/HARMFUL en modelo FT
3. Eliminar las que sean NEUTRAL o HARMFUL
4. Actualizar DECISIONS.md

---

## 💰 Tech debt acumulado (no bloquea Sprint 5)

1. **SQLAlchemy ORDER BY bug:** "for SELECT DISTINCT, ORDER BY expressions must appear in select list" en admin/stats queries. Logs prod 19-abr.
2. **sentence_transformers** falta en requirements-lite.txt → FRUSTRATION-ML fallback heurístico en CCEE.
3. **distill_style_prompts.py** usa campo `source_length_chars` que no existe en schema real (columna real: `doc_d_chars`). Arreglado en Worker I commit 6084c25a pero confirmar en staging.

---

## 📊 Métricas Sprint 5 finales

| Métrica | Valor | Referencia |
|---|---|---|
| v5 composite | **72.6** | A2.5 POST-hotfix, ARC1+ARC2 activos |
| K1 Context Retention | **94.6** | +29.7 vs baseline |
| ARC3 distill validation | **APPROVE** | Δ composite -0.9, Δ S1 -0.8 |
| ARC3 distill compression | **54-55%** | iris=1368/2557, stefano=1242/2266 |
| ARC4 Phase 2 shadow | **6/7 PROTECTIVE** | solo M10 NEUTRAL (+0.3) |

---

## 🎯 Next phase: Fine-tuning

Ver `docs/sprint5_planning/SPRINT5_MASTERDOC.md` §9 para roadmap FT.

**Flags Railway al cierre Sprint 5:**

| Flag | Valor | Descripción |
|---|---|---|
| `ENABLE_BUDGET_ORCHESTRATOR` | `true` ✅ | ARC1 token budget activo |
| `ENABLE_DUAL_WRITE_LEAD_MEMORIES` | `true` ✅ | ARC2 dual-write activo |
| `ENABLE_LEAD_MEMORIES_READ` | `true` ✅ | ARC2 read cutover activo |
| `ENABLE_NIGHTLY_EXTRACT_DEEP` | `true` ✅ | ARC2 scheduler activado 19-abr |
| `ENABLE_COMPACTOR_SHADOW` | `true` ✅ | ARC3 Phase 2 shadow activo |
| `ENABLE_CIRCUIT_BREAKER` | `true` ✅ | ARC3 Phase 4 safety net activo |
| `USE_DISTILLED_DOC_D` | `false` ⏳ | APPROVE obtenido, pendiente decisión activación |
| `USE_COMPACTION` | `false` ⏳ | Esperando Phase 3 live (1k turnos shadow) |

---

### Update 20-abr-2026: Distill A/B P1 completado

Worker P1 ejecutado. Composite OFF baseline: 66.4 (v5, mean 3 runs, 50 cases × 3 + MT, protocolo estándar)

Dimensiones: S1=72.3 S3=64.6 H=72.0 K=72.5 L=68.2 B=57.8 S2=47.0 S4=66.9
MT composite: 73.09 (5 conv × 10 turns; individual: 65.0/77.3/70.0/74.2/78.9)

Siguiente: Worker P2 con USE_DISTILLED_DOC_D=true.
