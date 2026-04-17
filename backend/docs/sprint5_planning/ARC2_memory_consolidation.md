# ARC2 — Memory Consolidation

**Sprint arquitectónico:** ARC2 (de 5 del plan W7 §9 Track 2).
**Duración estimada:** 6 semanas (2 schema+migration, 2 dual-write+backfill, 1 cutover lectura, 1 legacy removal).
**Fuentes input:** W7 §4 S1 + §5.D6 + §7.B18 + §8.D + §9.ARC2, W4 completo (CC memory deep-dive), GRAPH_REPORT Dual Memory Storage Conflict.
**Dependencias:** ARC2 puede correr en paralelo con ARC1 (no hay dependencia técnica, pero sí compite por atención humana — ver §7 cronograma).
**Estado del doc:** self-contained.

---

## 0 · TL;DR ejecutivo

**Problema:** 3 sistemas independientes gestionan "qué dijo este lead / qué sé de él":

1. `services/memory_store.py::MemoryStore` — JSON files en disco, `FollowerMemory` dataclass (W4 §4.2, legacy).
2. `services/conversation_memory_service.py::ConversationMemoryService` — DB + regex español hardcoded (W4 §4.1-4.5, patrón `ya te (lo )?dije`, no portable).
3. `core/memory/engine.py::MemoryEngine` — pgvector + Ebbinghaus decay, gated `ENABLE_MEMORY_ENGINE=false` en producción.

**Sin source of truth, sin schema unificado, sin single-writer.** Los 3 están OFF por defecto en producción (W7 D6). CC evita esto con **scope separation por artefacto** (memdir/ vs SessionMemory/) + **single-writer enforcement por tool sandboxing** (W4 §1.6, §3.1).

**Solución:** consolidar en un **único memory subsystem** inspirado en CC 4-types (`user/feedback/project/reference`) pero adaptado a Clonnect (multi-tenant per-lead):

- Taxonomía cerrada de 5 tipos (identity/interest/objection/intent_signal/relationship_state).
- Schema unificado con body_structure mandatory (fact + Why + How to apply).
- Storage en pgvector + metadata relacional.
- Single-writer cursor `lead_memories.last_writer`.
- Migration data path: 4 fases con dual-write.

**Impacto esperado CCEE:** +10-15 puntos en K1 Context Retention, estable o mejora B2 Persona Consistency, elimina el Dual Memory Conflict confirmado en GRAPH_REPORT.

**Riesgo alto:** data migration (±500 leads activos × 3 memory stores). Backfill incremental + snapshots obligatorios.

---

## 1 · Problema que resuelve (evidencia)

### 1.1 Los 3 sistemas solapados (W7 §4.S1)

**MemoryStore (legacy, JSON-based)**

- File: `services/memory_store.py`
- Storage: `.json` files por `(creator_id, follower_id)` (W4 §4.2 línea 187-193).
- Schema: `FollowerMemory` dataclass con fields ad-hoc (no types enforced).
- Consumers: phases/context.py path legacy (OFF por defecto, pero imports siguen).
- Cache: `BoundedTTLCache(max_size=500, ttl=600s)` (W4 §4.2 línea 180).

**ConversationMemoryService (DB-based, i18n-roto)**

- File: `services/conversation_memory_service.py`
- Storage: tabla `conversation_memory` en Postgres.
- Schema: incluye regex hardcoded en español `ya te (lo )?dije`, `como te comenté` (W4 §4.2 líneas 331-346).
- **Ruptura de portabilidad:** no funciona para creators catalanes, italianos, ingleses.
- Consumers: phases/context.py (usado en producción para algunos flujos).

**MemoryEngine (pgvector + decay, dormant)**

- File: `core/memory/engine.py`
- Storage: pgvector embeddings + relational metadata.
- Features: Ebbinghaus decay (`ENABLE_MEMORY_DECAY`), facts vectoriales.
- Flag: `ENABLE_MEMORY_ENGINE=false` default (context.py:294 — OFF).

### 1.2 Evidencia de conflicto

- **GRAPH_REPORT** lista "Dual Memory Storage Conflict" como hiperedge con `EXTRACTED confianza=1.0`.
- **Clonnect_Backend_Graph.md §Conexiones Sorprendentes #2** confirma literalmente.
- **W4 §4.5 (Clonnect gaps):** "los 3 sistemas almacenan fragmentos de memoria conversacional, con schemas distintos y sin sincronización. Consumidores cross-wired: algunos phases leen de MemoryStore, otros de MemoryEngine, otros de ConversationMemoryService."

### 1.3 Evidencia de que CC evita este problema

**W4 §4.5 explícito:** CC evita dual-storage con 2 mecanismos combinados:

1. **Scope separation por artefacto** (W4 §3.1):
   - `memdir/` = conocimiento cross-sesión, N archivos `.md` tipados.
   - `SessionMemory/` = continuidad intra-sesión, 1 archivo template-driven.
   - `autoDream` = distilación periódica, output en memdir.
   - Cada uno con **tool permission scope distinto** (ver W4 §3.1 tabla).

2. **Single-writer por tool sandboxing** (W4 §1.6):
   - `createAutoMemCanUseTool` → solo FileEdit/Write si `isAutoMemPath(file_path)`.
   - `createMemoryFileCanUseTool` de SessionMemory → solo Edit sobre el **path exacto**.
   - Cualquier violación del path → `deny` explícito.

3. **Mutex main-agent / fork-agent** (W4 §1.7):
   - `hasMemoryWritesSince(messages)` escanea por tool_use Write/Edit a memdir.
   - Si el main agent ya escribió → fork skipea la ventana y avanza cursor.

### 1.4 Impacto actual cuantificado

**Context Retention degradado (K1):**

CCEE Iris 26b Sprint 31 final muestra K1 ~69. Causa documentada en QW2/QW5 reports: información que un lead dijo hace 5 turnos no se recupera porque está en `MemoryStore` pero el flujo actual lee de `ConversationMemoryService`.

**Ejemplo real (W1 §sys07 nota):**
> "Lead dice en turn 3 'tengo 32 años'. En turn 7 pregunta por producto. El bot responde como si nunca hubiera compartido edad. Logs muestran fact 'age=32' en MemoryStore JSON pero no en conversation_memory table."

**Persona Consistency estable pero frágil (B2):**

B2 está en ~74. El riesgo es que cualquier activación de `ENABLE_MEMORY_ENGINE=true` sin consolidar primero genera doble extracción y contradicciones (M4 extrae `relationship_state=customer`, CMS mantiene `relationship_state=lead`).

---

## 2 · Diseño técnico

### 2.1 Taxonomía: 5 tipos cerrados

Adaptación de CC 4-types (`user/feedback/project/reference`) al dominio Clonnect DM. Cada tipo tiene contrato XML-like inspirado en `memoryTypes.ts` (W4 §2.2):

| Tipo | Descripción | `when_to_save` | `how_to_use` | `body_structure` |
|------|-------------|----------------|---------------|------------------|
| `identity` | Datos durables del lead (nombre, ubicación, edad, profesión, situación personal) | Cuando el lead revela dato factual verificable | Saludo + personalización + no-repetir-pregunta | Free-form (opcional Why) |
| `interest` | Producto/tema que el lead menciona explícita o implícitamente | Lead pregunta/menciona producto/método/tema | Priorizar productos alineados al interés detectado | Fact + Why (por qué sabemos que le interesa) |
| `objection` | Bloqueo o duda (precio, tiempo, dudas sobre producto) | Lead expresa reticencia explícita o implícita | Proactivamente abordar la objeción en siguiente mensaje | Fact + **Why** + **How to apply** (obligatorio) |
| `intent_signal` | Señal de compra o abandono (ej: "me lo pienso", "¿precio?", "quiero empezar hoy") | Lead revela intención de acción | Escalar a template (checkout, booking, nurturing) | Fact + signal_strength (weak/medium/strong) + Why |
| `relationship_state` | Status lead/customer/warm/cold + timestamp transición | Transición de estado detectada (primera compra, ghost, reactivación) | Template específico por estado | Fact + **Why** + transition_date |

### 2.2 Schema unificado

```sql
-- Migration: alembic/versions/XXX_arc2_lead_memories.py
CREATE TABLE lead_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL REFERENCES creators(id),
    lead_id UUID NOT NULL REFERENCES leads(id),
    memory_type TEXT NOT NULL CHECK (memory_type IN (
        'identity', 'interest', 'objection', 'intent_signal', 'relationship_state'
    )),
    content TEXT NOT NULL,                         -- fact literal
    why TEXT,                                       -- motivación (obligatorio para feedback/objection/relationship)
    how_to_apply TEXT,                              -- cómo usar (obligatorio para objection/relationship)
    body_extras JSONB DEFAULT '{}',                 -- campos específicos por tipo (signal_strength, etc.)
    embedding vector(1536),                         -- pgvector para recall semántico
    source_message_id UUID REFERENCES messages(id), -- mensaje que originó el fact
    confidence FLOAT DEFAULT 1.0,                   -- 0-1, derivado del extractor
    last_writer TEXT NOT NULL,                      -- 'dm_extractor' | 'copilot' | 'onboarding' | 'migration'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,                         -- soft delete
    superseded_by UUID REFERENCES lead_memories(id), -- para correcciones explícitas
    UNIQUE (creator_id, lead_id, memory_type, content)  -- dedup natural
);

CREATE INDEX idx_lead_memories_lead ON lead_memories(creator_id, lead_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_lead_memories_type ON lead_memories(creator_id, lead_id, memory_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_lead_memories_embedding ON lead_memories USING ivfflat (embedding vector_cosine_ops);

-- Validación a nivel CHECK
ALTER TABLE lead_memories ADD CONSTRAINT chk_objection_body_structure
    CHECK (memory_type != 'objection' OR (why IS NOT NULL AND how_to_apply IS NOT NULL));
ALTER TABLE lead_memories ADD CONSTRAINT chk_relationship_state_transition
    CHECK (memory_type != 'relationship_state' OR (why IS NOT NULL AND how_to_apply IS NOT NULL));
```

**Justificación del schema:**

- **Single table vs multi-table:** un schema simple permite queries simples por `(lead_id)`. Alternativa (una tabla por type) es sobre-ingeniería.
- **pgvector integrado:** recall semántico en la misma tabla, sin join cross-schema.
- **Soft delete + `superseded_by`:** CC `MEMORY_DRIFT_CAVEAT` enseña que una memoria obsoleta se actualiza, no se borra (W4 §2.7). El campo permite trazar "memoria A dijo X, memoria B la corrigió a Y".
- **CHECK constraints:** enforzar `body_structure` mandatory para los tipos que lo exigen (objection, relationship_state) a nivel DB, no solo capa aplicación.

### 2.3 Single-writer enforcement

CC usa tool sandboxing (`createAutoMemCanUseTool`). Clonnect no tiene tool system → alternativa: **single-writer cursor** por lead.

```python
# services/lead_memory_service.py (nuevo)
from dataclasses import dataclass
from typing import Literal

WriterName = Literal['dm_extractor', 'copilot', 'onboarding', 'migration']

@dataclass
class LeadMemoryWriter:
    creator_id: UUID
    lead_id: UUID
    writer_name: WriterName

    async def write(self, memory: LeadMemoryInput) -> LeadMemory:
        # Lock pessimista breve para garantizar single-writer
        async with acquire_lead_memory_lock(self.lead_id, timeout=500):
            # Dedup natural por unique constraint (creator_id, lead_id, type, content)
            # Si ya existe → UPDATE updated_at y body_extras
            # Si no → INSERT
            return await upsert_memory(memory, last_writer=self.writer_name)

    async def supersede(self, old_id: UUID, new_memory: LeadMemoryInput) -> LeadMemory:
        # Correction path: marcar old como superseded, insertar new
        ...
```

**Lock mechanism:**

Opción A — PostgreSQL advisory lock:
```python
async def acquire_lead_memory_lock(lead_id: UUID, timeout: int) -> AsyncContextManager:
    lock_key = hash(lead_id) & 0x7FFFFFFFFFFFFFFF  # bigint positivo
    await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_key)
    # se libera al commit/rollback
```

Opción B — Redis mutex:
```python
async with redis_client.lock(f"lead_mem:{lead_id}", timeout=0.5, blocking_timeout=0.5):
    ...
```

**Recomendación:** A (advisory lock). Evita dependencia nueva (Redis), performante, session-scoped natural.

### 2.4 API pública

```python
# services/lead_memory_service.py

class LeadMemoryService:
    """Único interface para leer/escribir memorias del lead."""
    
    # Escritura
    async def write_memory(
        self, creator_id: UUID, lead_id: UUID, memory_type: MemoryType,
        content: str, writer: WriterName, *, why: str = None, how_to_apply: str = None,
        body_extras: dict = None, source_message_id: UUID = None, confidence: float = 1.0
    ) -> LeadMemory: ...
    
    async def supersede_memory(self, old_id: UUID, new_content: str, writer: WriterName) -> LeadMemory: ...
    
    async def soft_delete(self, memory_id: UUID, writer: WriterName) -> None: ...

    # Lectura
    async def get_all(self, creator_id: UUID, lead_id: UUID) -> list[LeadMemory]: ...
    
    async def get_by_type(self, creator_id: UUID, lead_id: UUID, types: list[MemoryType]) -> list[LeadMemory]: ...
    
    async def recall_semantic(
        self, creator_id: UUID, lead_id: UUID, query_embedding: list[float], top_k: int = 5
    ) -> list[LeadMemory]:
        """pgvector ANN search."""
    
    async def get_current_state(
        self, creator_id: UUID, lead_id: UUID
    ) -> LeadMemorySnapshot:
        """Devuelve snapshot consolidado: identity + active objections + current relationship_state + recent intents."""
```

### 2.5 Extractor unificado (reemplaza 3 extractors actuales)

```python
# services/memory_extractor.py (refactored)
# Fusiona: memory_extraction.py + memory_engine.py extractor + conversation_memory_service.py extract

class MemoryExtractor:
    """
    Post-turn hook: analiza la conversación reciente y extrae 0-N memorias tipadas.
    Inspirado en CC extractMemories forked agent (W4 §1.1-1.3), adaptado a Clonnect
    (DM single-shot, no forked LLM call — usa el mismo provider del reply).
    """

    async def extract(
        self,
        creator_id: UUID,
        lead_id: UUID,
        new_messages: list[Message],
        already_known: list[LeadMemory],
    ) -> list[LeadMemoryInput]:
        """
        1. Envía contexto + new_messages al LLM con prompt estructurado
           (inspirado en memoryTypes.ts TYPES_SECTION_INDIVIDUAL).
        2. LLM devuelve JSON: [{type, content, why?, how_to_apply?, body_extras?}, ...]
        3. Dedup contra `already_known` por similitud semántica (pgvector).
        4. Retorna lista para que LeadMemoryWriter persista.
        """
```

**Decisión:** un LLM call extra por turn es caro (~200-500ms, +$0.0005). Alternativas:

- **Opción A — LLM per-turn (CC style):** extracción post-reply, fire-and-forget async. No bloquea UX.
- **Opción B — Batch nightly:** acumular conversaciones, extraer en job programado.
- **Opción C — Híbrido:** per-turn ligero (regex + heurística para identity/intent_signal) + nightly deep extract.

**Recomendación:** C. El cost-benefit favorable (identity/intent son frecuentes y necesarios en tiempo real; objection/relationship_state son caros y pueden esperar).

### 2.6 Migración de datos (backfill)

**Datos a migrar:**

| Fuente | Tabla/Archivo | Estimación records |
|--------|---------------|---------------------|
| `conversation_memory` table | DB | ~15,000 rows |
| `FollowerMemory` JSONs | Disco `data/memory/{creator}/{follower}.json` | ~500 archivos |
| `memory_engine_facts` (si existe) | pgvector table | 0 (flag OFF) |

**Mapping `conversation_memory` → `lead_memories`:**

```python
# scripts/migrate_conversation_memory.py
for row in conversation_memory:
    # Heurística: inferir type desde content
    if 'nombre' in row.content.lower() or 'me llamo' in row.content.lower():
        mem_type = 'identity'
    elif any(word in row.content.lower() for word in ['caro', 'precio', 'no tengo']):
        mem_type = 'objection'
    elif any(word in row.content.lower() for word in ['quiero', 'empezar', 'me lo pienso']):
        mem_type = 'intent_signal'
    elif any(word in row.content.lower() for word in ['producto', 'plan', 'método']):
        mem_type = 'interest'
    else:
        mem_type = 'identity'  # default seguro
    
    # Migrar con writer='migration'
    await writer.write(LeadMemoryInput(
        creator_id=row.creator_id,
        lead_id=row.lead_id,
        memory_type=mem_type,
        content=row.content,
        confidence=0.5,  # baja — es heurística, no extraída por LLM
        last_writer='migration',
        created_at=row.created_at,  # preservar timestamp original
    ))
```

**Caveat:** la clasificación heurística es ruidosa. Plan B: en Fase 3 (post-cutover), re-extraer con LLM las memorias marcadas `last_writer=migration, confidence<0.7`, actualizar a `confidence=1.0`.

**Mapping `FollowerMemory` JSONs:**

Schema actual de `FollowerMemory`:
```python
@dataclass
class FollowerMemory:
    name: str | None
    age: int | None
    location: str | None
    interests: list[str]
    objections: list[str]
    # ... otros fields ad-hoc
```

Migración:
```python
for file in glob('data/memory/**/*.json'):
    follower = FollowerMemory(**json.load(file))
    lead_id = resolve_lead_from_follower(creator, follower)  # join por platform_user_id
    
    if follower.name:
        await writer.write(
            memory_type='identity',
            content=f'Nombre: {follower.name}',
            last_writer='migration', confidence=0.8
        )
    if follower.age:
        await writer.write(
            memory_type='identity',
            content=f'Edad: {follower.age}',
            last_writer='migration', confidence=0.8
        )
    for interest in follower.interests:
        await writer.write(
            memory_type='interest',
            content=interest,
            why='Migrado de FollowerMemory legacy',
            last_writer='migration', confidence=0.7
        )
    # etc.
```

---

## 3 · Plan de migración (5 fases)

### Fase 1 — Schema + Migration one-shot (Week 1-2)

**Objetivo:** tabla `lead_memories` creada, migration scripts listos, NO producción aún.

**Tareas:**
1. Alembic migration `XXX_arc2_lead_memories.py` — crear tabla con constraints.
2. Verificar en staging: `alembic upgrade head` verde.
3. Script `scripts/migrate_conversation_memory.py` + `scripts/migrate_follower_jsons.py`.
4. Correr ambos en **copia de prod DB** (snapshot) y medir:
   - Records totales migrados.
   - Records con `confidence<0.7` (re-extraction candidates).
   - Tiempo de ejecución.
5. Unit tests del extractor + service.

**Deliverable:** PR con migration + scripts + tests.

**Verificación:**
```bash
# En staging:
alembic upgrade head
python3 scripts/migrate_conversation_memory.py --dry-run
python3 scripts/migrate_follower_jsons.py --dry-run
pytest tests/memory/ -xvs
```

### Fase 2 — Escritura dual (Week 3)

**Objetivo:** todo write va a `lead_memories` **y** al sistema legacy correspondiente. Lecturas siguen legacy.

**Tareas:**
1. Modificar `services/memory_extraction.py` para dual-write.
2. Modificar `services/conversation_memory_service.py::save` para dual-write.
3. Modificar `services/memory_service.py::FollowerMemory.save` para dual-write.
4. Flag `ENABLE_DUAL_WRITE_LEAD_MEMORIES=true` (default ON a staging, OFF a prod).
5. Deploy a prod con flag OFF, verificar boot.

**Deliverable:** PR dual-write + flag.

**Verificación:**
- Staging: observar que `lead_memories` recibe writes.
- Prod con flag ON para 1 creator piloto (Iris): 48h de writes + 0 errors.
- Diff tool: script que compara `conversation_memory` vs `lead_memories` y reporta drift.

### Fase 3 — Backfill histórico (Week 4)

**Objetivo:** importar todos los datos históricos a `lead_memories`.

**Tareas:**
1. Ejecutar `scripts/migrate_conversation_memory.py` en prod (incremental, 1000 rows/batch, sleep 2s).
2. Ejecutar `scripts/migrate_follower_jsons.py` en prod (1 creator a la vez).
3. **Post-backfill re-extraction:** job que recorre `lead_memories WHERE last_writer='migration' AND confidence<0.7` y llama LLM extractor para re-clasificar con confidence=1.0.

**Deliverable:** report `docs/audit_phase2/ARC2_backfill_report.md`:
- Total migrated.
- Re-classified.
- Orphans (FollowerMemory sin lead match).

**Verificación:**
- Query: `SELECT COUNT(*), memory_type FROM lead_memories GROUP BY memory_type`.
- Query: `SELECT lead_id, array_agg(memory_type) FROM lead_memories GROUP BY lead_id HAVING array_length(array_agg(memory_type), 1) > 3` (leads con memoria rica).

### Fase 4 — Switch lectura (Week 5)

**Objetivo:** toda lectura usa `lead_memories`. Writes siguen dual (por si hay que rollback).

**Tareas:**
1. Modificar `core/dm/phases/context.py:263-330` (recalling_block) para leer vía `LeadMemoryService`.
2. Modificar copilot `/actions` para leer vía `LeadMemoryService`.
3. Feature flag `ENABLE_LEAD_MEMORIES_READ=true` (A/B 10%→50%→100%).
4. CCEE measurement por ventana (esperamos +10-15 K1).

**Deliverable:** `docs/audit_phase2/ARC2_read_cutover_ccee.md`.

**Verificación:**
- CCEE K1 ≥ baseline + 8 puntos en 10% sample.
- No regresión B2 o L1.
- Prod logs sin errors de missing data.

### Fase 5 — Legacy removal (Week 6)

**Objetivo:** eliminar los 3 sistemas legacy.

**Tareas:**
1. Eliminar `ConversationMemoryService` (código + table dropping con backup).
2. Eliminar `FollowerMemory` JSON storage (archivar a cold storage).
3. Eliminar `MemoryEngine` si no hay consumers (verificar con grep).
4. Eliminar flag `ENABLE_DUAL_WRITE_LEAD_MEMORIES` y `ENABLE_LEAD_MEMORIES_READ`.
5. Actualizar `docs/CROSS_SYSTEM_ARCHITECTURE.md`.

**Deliverable:** PR "refactor(memory): ARC2 complete — remove 3 legacy systems".

**Verificación:**
- Grep por `MemoryStore`, `ConversationMemoryService`, `MemoryEngine`: 0 hits en `core/`, `services/`, `api/`.
- CI + smoke tests verde.
- 72h prod stable.

---

## 4 · Métricas de éxito

### 4.1 CCEE quantitative

| Métrica | Baseline | Target post-ARC2 | Kill-switch |
|---------|----------|------------------|-------------|
| K1 Context Retention | ~69 | ≥ 79 (+10) | < 66 |
| B2 Persona Consistency | ~74 | ≥ 74 estable | < 72 |
| L3 Context awareness | ~70 | ≥ 72 | < 68 |
| S7 intimate no rag | ~63 | ≥ 68 (memoria ayuda) | — |
| Composite Iris | ~70 | ≥ 74 | < 68 |
| Composite Stefano | ~72 | ≥ 74 | < 70 |

### 4.2 Data quality

| Métrica | Target |
|---------|--------|
| Leads con ≥1 memoria tipada | ≥ 60% (vs ~15% actual) |
| Memorias con `why` no-null (objection + relationship) | 100% (CHECK constraint) |
| Drift post-cutover (legacy vs lead_memories) | 0% |
| Re-extracted memories (confidence bumped to 1.0) | ≥ 50% de migration cohort |

### 4.3 Performance

| Métrica | Target |
|---------|--------|
| `lead_memory_service.recall_semantic` p95 | <50ms |
| `lead_memory_service.write` p95 | <100ms (incluyendo advisory lock) |
| DB storage `lead_memories` tras backfill | <500MB |

---

## 5 · Riesgos y mitigaciones

### R1 — Data loss durante migration

**Escenario:** script de migration falla a mid-batch, estado inconsistente.

**Probabilidad:** media.

**Impacto:** alto.

**Mitigación:**
- Snapshot pre-migration de `conversation_memory` table (`pg_dump --table=conversation_memory`).
- Archivar JSONs pre-migration a S3/disco permanente.
- Migration idempotente: check por unique constraint `(creator_id, lead_id, type, content)` antes de insert.
- Incremental en batches con checkpoint `last_migrated_id`.

### R2 — Divergencia entre sistemas durante dual-write

**Escenario:** `ConversationMemoryService.save` escribe exitosamente pero `LeadMemoryService.write` falla → drift.

**Probabilidad:** media (DB hiccups).

**Impacto:** medio.

**Mitigación:**
- Dual-write envuelto en try/except: si new falla, log + metric `dual_write_drift` + emit alert.
- Daily cron: script diff `conversation_memory` vs `lead_memories` → reporte drift.
- Durante Fase 2: tolerar drift <1%, abortar si >5%.

### R3 — Comportamiento diferente entre sistemas afecta CCEE durante transición

**Escenario:** algunos requests leen de legacy (escenario antiguo), otros de `lead_memories` (via A/B). Inconsistencia de personalización.

**Probabilidad:** alta durante Fase 4.

**Impacto:** medio (A/B ruido).

**Mitigación:**
- Sticky A/B por `lead_id` hash (mismo lead ve siempre el mismo path durante rollout).
- Monitoreo per-bucket de CCEE.
- Rollout rápido de 10%→100% (no dejar meses).

### R4 — CHECK constraints rechazan inserts legacy sin `why`

**Escenario:** migration trae objections legacy sin `why` → INSERT falla.

**Probabilidad:** alta.

**Impacto:** medio (migración parcial).

**Mitigación:**
- Migration script añade `why='Migrado de sistema legacy'` y `how_to_apply='Revisar en re-extraction'` para records sin ellos.
- Post-migration job re-extrae estos records con LLM para obtener `why` real.

### R5 — Single-writer lock contention

**Escenario:** múltiples webhooks paralelos para el mismo lead → lock starvation.

**Probabilidad:** baja (webhooks por lead son secuenciales en IG).

**Impacto:** bajo-medio.

**Mitigación:**
- Advisory lock con timeout 500ms. Si expira, log + skip write (no-op seguro, el fact se re-extraerá en siguiente turn).
- Monitor metric `lead_memory_lock_timeout.count`.

### R6 — pgvector index rebuild tiempo largo

**Escenario:** `ivfflat` index en 15k rows + growing → REINDEX lento.

**Probabilidad:** media.

**Impacto:** bajo (solo durante maintenance windows).

**Mitigación:**
- Usar `ivfflat` con `lists = sqrt(rows)` inicial.
- Plan de upgrade a `hnsw` cuando pgvector >= 0.5.
- REINDEX CONCURRENTLY para no bloquear writes.

### R7 — Re-extraction LLM costs explode

**Escenario:** Fase 3 re-extraction de 5,000 memorias × $0.0005 = $2.50. Bajo, pero si hay bugs que re-hagan el loop, escala.

**Probabilidad:** baja.

**Impacto:** bajo.

**Mitigación:**
- Guard: `confidence < 0.7 AND last_writer = 'migration'` → solo se re-extrae una vez, se marca con `last_writer='re_extraction'`.
- Budget cap: circuit breaker si >$10 en 24h → halt.

---

## 6 · Dependencias

### 6.1 Inputs

- **Ninguno bloqueante.** Puede iniciar en paralelo con ARC1.
- **Preferible:** QW4 completo (metadata orphans, reduce ruido).

### 6.2 Outputs

- **ARC1 budget orchestrator:** la sección `recalling` (memory) ahora consume `LeadMemoryService`. El cap 400 tokens se aplica sobre el output consolidado.
- **ARC3 compaction:** para distillation de memoria histórica (análogo a autoDream).
- **ARC5 observability:** nuevas métricas de memoria.
- **Futuras features:** learning pipeline, DPO pair construction, cross-lead insights.

### 6.3 Paralelismo con ARC1

ARC1 y ARC2 pueden correr en paralelo con las siguientes precauciones:
- ARC1 Fase 3 CCEE no debe coincidir con ARC2 Fase 4 (scenarios confundidos).
- Si ARC1 llega a Fase 5 antes que ARC2 termine Fase 4, coordinar orden de gates en `core/dm/budget/gates/memory.py` con la API de `LeadMemoryService`.

---

## 7 · Cronograma detallado (6 semanas)

### Week 1 — Schema design + prototype

- D1-D2: Diseñar schema definitivo, escribir alembic migration.
- D3-D4: Implementar `LeadMemoryService` + unit tests.
- D5: Prototipar `MemoryExtractor` con LLM call.

### Week 2 — Migration scripts + staging

- D1-D2: Scripts de migration `conversation_memory` + `FollowerMemory` JSONs.
- D3: Correr migration en copia staging, medir.
- D4-D5: Fix issues, rerun, documentar.

### Week 3 — Dual write

- D1-D2: Refactor `memory_extraction.py` + `conversation_memory_service.py` para dual-write.
- D3: Deploy staging con flag ON.
- D4-D5: Observar 48h, monitorear drift.

### Week 4 — Backfill

- D1: Ejecutar migration en prod (incremental).
- D2-D3: Post-migration re-extraction job.
- D4-D5: Report + validation.

### Week 5 — Cutover lectura

- D1: Rollout A/B 10%.
- D2-D3: Monitor CCEE + drift.
- D4: Rollout 50%.
- D5: Rollout 100% si green.

### Week 6 — Legacy removal

- D1-D2: PR remove ConversationMemoryService + dead code.
- D3: Deploy.
- D4-D5: 72h monitoring + final report.

---

## 8 · Prompts de workers ejecutores

### Worker A2.1 — Schema + migration (Sonnet, 2 días)

```xml
<instructions>
<objetivo>
Diseñar e implementar tabla `lead_memories` con schema unificado, inspirado en
CC 4-types y adaptado a 5 tipos Clonnect.
</objetivo>

<input_obligatorio>
1. docs/sprint5_planning/ARC2_memory_consolidation.md §2.1-§2.3
2. alembic/versions/ (patrón de migrations existentes)
3. api/database.py (connect_args, pool config NO TOCAR)
</input_obligatorio>

<tareas>
1. Crear alembic migration XXX_arc2_lead_memories.py con:
   - Tabla lead_memories completa (schema §2.2)
   - Indexes (lead, type, embedding)
   - CHECK constraints (body_structure)
   - pgvector extension si no existe
2. Crear services/lead_memory_service.py con API §2.4
3. Tests unitarios tests/memory/test_lead_memory_service.py
4. Downgrade migration reversible (rollback path)
</tareas>

<reglas>
- NO modificar connect_args
- Migration idempotente
- CHECK constraints obligatorios
- 4-phase workflow OBLIGATORIO
</reglas>

<verificacion>
- alembic upgrade head en staging → verde
- pytest tests/memory/ -xvs → verde
- alembic downgrade -1 → verde (reversible)
</verificacion>
</instructions>
```

### Worker A2.2 — Extractor unificado (Sonnet + Opus evaluation, 3 días)

```xml
<instructions>
<objetivo>
Fusionar los 3 extractors actuales en un único `MemoryExtractor` con 5 tipos tipados.
</objetivo>

<input_obligatorio>
1. services/memory_extraction.py actual (legacy)
2. services/memory_engine.py extractor
3. services/conversation_memory_service.py extract
4. docs/sprint5_planning/ARC2_memory_consolidation.md §2.5
5. core/personality_loader.py (patrón de prompts)
</input_obligatorio>

<tareas>
1. Diseñar prompt de extracción con contratos XML (inspirado en memoryTypes.ts TYPES_SECTION)
2. Implementar services/memory_extractor.py (nuevo, reemplaza los 3)
3. Opción híbrida: regex ligero per-turn (identity, intent_signal) + nightly LLM deep-extract (objection, relationship_state)
4. Tests con fixtures de conversaciones reales anonimizadas
5. Evaluación: ¿qué % de memorias extraídas son redundantes con sistema legacy?
</tareas>

<reglas>
- El extractor NO debe bloquear el webhook reply (max 200ms síncrono)
- Deep-extract nightly como job separado
- NO mezclar código con los 3 legacy (se eliminarán en Fase 5)
- 4-phase workflow OBLIGATORIO
</reglas>
</instructions>
```

### Worker A2.3 — Migration scripts (Sonnet, 2 días)

```xml
<instructions>
<objetivo>
Scripts de migración de conversation_memory + FollowerMemory JSONs → lead_memories.
</objetivo>

<input_obligatorio>
1. docs/sprint5_planning/ARC2_memory_consolidation.md §2.6
2. services/memory_store.py (schema FollowerMemory)
3. Migration creada por Worker A2.1 debe existir
</input_obligatorio>

<tareas>
1. scripts/migrate_conversation_memory.py:
   - Argparse: --dry-run, --batch-size, --creator-id (opcional filtro)
   - Heurística de type classification
   - Idempotente (dedup por UNIQUE constraint)
   - Batch size default 1000, sleep 2s entre batches
2. scripts/migrate_follower_jsons.py:
   - Glob data/memory/**/*.json
   - Resolve lead_id by platform_user_id (both formats)
   - One creator at a time
3. scripts/reextract_low_confidence.py:
   - Query: WHERE last_writer='migration' AND confidence<0.7
   - Llama LLM extractor
   - UPDATE confidence + why/how_to_apply
4. Tests: correr en DB de test con fixtures
</tareas>

<reglas>
- Snapshots pre-migration obligatorios (pg_dump)
- Idempotent (no duplicar on re-run)
- Log progress cada 100 batches
- 4-phase workflow OBLIGATORIO
</reglas>
</instructions>
```

### Worker A2.4 — Dual-write integration (Sonnet, 2 días)

```xml
<instructions>
<objetivo>
Modificar los 3 points of write (memory_extraction, conversation_memory_service.save,
FollowerMemory.save) para dual-write a lead_memories.
</objetivo>

<input_obligatorio>
1. services/memory_extraction.py
2. services/conversation_memory_service.py
3. services/memory_service.py (FollowerMemory)
4. services/lead_memory_service.py (de Worker A2.1)
</input_obligatorio>

<tareas>
1. Añadir ENABLE_DUAL_WRITE_LEAD_MEMORIES flag
2. En cada save path: si flag ON, también llamar LeadMemoryService.write
3. Try/except: legacy write primero, new write en try (no debe romper legacy path)
4. Emit metric dual_write_drift si una falla y otra no
5. Tests: mock legacy + verify new write
6. Daily cron script: diff legacy tables vs lead_memories, reporte
</tareas>

<reglas>
- Legacy path NUNCA debe romperse
- New path failure → log + metric, no exception propagation
- 4-phase workflow OBLIGATORIO
</reglas>
</instructions>
```

### Worker A2.5 — Read cutover + CCEE (Opus, 2 días)

```xml
<instructions>
<objetivo>
Cambiar lectura de contexto a lead_memories, medir CCEE, rollout A/B.
</objetivo>

<input_obligatorio>
1. core/dm/phases/context.py:263-330 (recalling_block)
2. services/lead_memory_service.py
3. Tests CCEE baselines Sprint 31 final
</input_obligatorio>

<tareas>
1. Modificar context.py para leer via LeadMemoryService cuando flag ON
2. ENABLE_LEAD_MEMORIES_READ A/B:
   - Sticky por lead_id hash
   - 10% → 50% → 100% en 5 días
3. Por ventana:
   - CCEE sample 10 scenarios Iris + 10 Stefano
   - Monitor K1, B2, L3, L1
   - Drift logs
4. Reporte docs/audit_phase2/ARC2_read_cutover_ccee.md
</tareas>

<reglas>
- Kill-switch ENABLE_LEAD_MEMORIES_READ_PCT=0 si K1 <66 o B2<72
- Coordinar con user antes de 100%
- 4-phase workflow OBLIGATORIO
</reglas>
</instructions>
```

### Worker A2.6 — Legacy removal (Sonnet, 1 día)

```xml
<instructions>
<objetivo>
Eliminar ConversationMemoryService, MemoryStore, MemoryEngine.
</objetivo>

<input_obligatorio>
1. ARC2_read_cutover_ccee.md debe mostrar 72h estable a 100%
2. Grep por uses de cada sistema
</input_obligatorio>

<tareas>
1. Grep de uses:
   - grep -rn "ConversationMemoryService" core/ services/ api/
   - grep -rn "MemoryStore" core/ services/ api/
   - grep -rn "MemoryEngine" core/ services/ api/
2. Eliminar imports, classes, archivos
3. Alembic migration para DROP conversation_memory table (con backup previo)
4. Archivar JSON FollowerMemory a cold storage antes de rm
5. Eliminar flags (ENABLE_DUAL_WRITE, ENABLE_LEAD_MEMORIES_READ)
6. Smoke tests green
</tareas>

<reglas>
- Backup conversation_memory table antes de DROP
- Archivar JSONs antes de rm
- 4-phase workflow OBLIGATORIO
- Coordinar con user antes de DROP table
</reglas>
</instructions>
```

---

## 9 · Open questions

### Q1 — ¿5 tipos es el número correcto?

Argumentos 5: simetría con CC 4+1 (identity como "user" de CC). Cada tipo tiene semántica clara.

Argumentos 4: eliminar `intent_signal` (es efímero, puede ser metadata en message no memoria).

Argumentos 6: separar `identity_durable` (nombre) de `identity_volatile` (situación actual).

**Recomendación:** 5 initial. Observar métricas después de backfill — si `intent_signal` es ≥80% del volumen, considerar mover a message metadata y quedarse con 4.

### Q2 — ¿pgvector 1536 dims o más eficiente 768?

1536: compatible con OpenAI `text-embedding-3-small`, precisión alta.

768: más rápido, menos storage, pero requiere modelo distinto.

**Recomendación:** 1536 (default OpenAI). Storage es bajo incluso a 500MB.

### Q3 — ¿Per-turn LLM extraction vs nightly-only?

Per-turn: fresh memoria en cada reply, pero +200-500ms latency.

Nightly: cheap y batch, pero memorias llegan con 24h delay.

Híbrido (recomendado): regex per-turn + LLM nightly.

### Q4 — ¿Qué hacer con memorias contradictorias? (ej: "tengo 25" turn 3, "tengo 26" turn 30)

Opción A: superseded_by chain (preservar ambas, marcar obsoleta).

Opción B: UPDATE in-place (perder historia).

Opción C: LLM-arbitered (llamar LLM para decidir cuál es cierta).

**Recomendación:** A. Matches CC `memoryDrift` caveat (W4 §2.7).

---

**Fin ARC2_memory_consolidation.md**
