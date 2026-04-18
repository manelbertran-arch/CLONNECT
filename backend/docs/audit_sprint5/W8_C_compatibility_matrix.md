# W8 Fase C — Matriz de Compatibilidad Cruzada

**Fecha:** 2026-04-18
**Auditor:** Opus 4.6
**Branch:** `audit/W8-C-crossmatrix`
**Scope:** 57 sistemas (23 WL + 15 T1-OPT + 11 T1-CONS + 8 T2-ACT)

---

## Resumen ejecutivo

| Métrica | Valor |
|---------|-------|
| Pares evaluados (no-triviales) | 52 |
| Interacciones detectadas | 52 |
| **Tipo 1 — Competencias directas** | **5** (requieren resolución antes de activar T2) |
| **Tipo 2 — Redundancias** | **12** (candidatos a fusionar/eliminar) |
| **Tipo 3 — Acoplamientos implícitos** | **16** (documentar y hacer explícitos) |
| **Tipo 4 — Context pollution** | **8** (candidato a budget/jerarquía ARC1) |
| **Tipo 5 — Problemas de orden** | **7** (fix inmediato posible) |
| **Tipo 6 — Complementariedades** | **9** (documentar para guías) |
| **Issues CRITICAL** | **5** |
| **Issues HIGH** | **9** |
| **Issues MEDIUM** | **15** |
| **Issues LOW** | **14** |
| **Bugs de producción descubiertos** | **3** (no vistos en audits B.2a/B.2b) |

---

## Interacciones por tipo

### Tipo 1 — Competencias directas (bloqueantes)

#### 1.1 DNA Context ↔ Relationship Adapter — Tone modulation conflict

- **Sistemas:** WL#6 DNA Engine (`dm_agent_context_integration.py`) ↔ WL#19 ECHO Relationship Adapter (`relationship_adapter.py`)
- **Evidencia:** Ambos inyectan instrucciones de tono/warmth en el mismo Recalling block (context.py:974). DNA: "lead prefers formal Spanish, vocabulary: [lista]". Adapter: "be professional but warm, tone=0.5". Instrucciones contradictorias sobre cómo tratar al lead.
- **Estado actual:** Adapter OFF (`ENABLE_RELATIONSHIP_ADAPTER=false`). **No hay conflicto en prod ahora.**
- **Impacto si se reactiva:** LLM recibe doble instrucción de tono — Doc D+DNA dice una cosa, Adapter dice otra.
- **Recomendación:** Si se reactiva Adapter, fusionar su output DENTRO del bloque DNA (un solo bloque de instrucciones de tono), no inyectar por separado.

#### 1.2 Best-of-N Confidence ↔ Question Remover — Scoring distorsionado

- **Sistemas:** T2#15 Best-of-N (`best_of_n.py:121`) ↔ WL#13 Question Remover (`postprocessing.py:238`)
- **Evidencia:** `calculate_confidence()` NO penaliza respuestas con BANNED_QUESTIONS. Best-of-N elige un candidato con "¿Qué te llamó la atención?" (alta confianza), pero Question Remover lo elimina post-selección. Un candidato sin pregunta (menor confianza raw) habría sido mejor post-procesado.
- **Impacto:** Ranking de Best-of-N distorsionado — elige winner que luego se degrada.
- **Recomendación:** **BLOQUEANTE para activar #15.** Añadir penalización en Confidence Scorer para respuestas con BANNED_QUESTIONS patterns ANTES de scoring.

#### 1.3 Best-of-N Scoring ciego a postprocessing — Winner sub-óptimo

- **Sistemas:** T2#15 Best-of-N (`best_of_n.py:69`) ↔ cadena postprocessing completa
- **Evidencia:** Best-of-N genera 3 candidatos y elige el mejor por confidence. Pero postprocessing mutará al winner (emoji stripping, length truncation, question removal). El candidato con score más alto RAW puede convertirse en el peor DESPUÉS de postprocessing.
- **Impacto:** CRITICAL — el propósito de Best-of-N (diversity + selection) se invalida si la selección ignora mutaciones post.
- **Recomendación:** **BLOQUEANTE para activar #15.** Ejecutar un subset de postprocessing (Question Remover + Style Normalizer) sobre cada candidato ANTES del scoring. O: scoring post-postprocessing.

#### 1.4 Bot Orchestrator ↔ Copilot — Dual response generation

- **Sistemas:** T1#58 Bot Orchestrator (`bot_orchestrator.py:68-255`) ↔ T1#93 Copilot (`copilot/service.py:20-393`)
- **Evidencia:** Ambos generan respuestas del mismo lead message. Bot Orchestrator vía `process_dm()`, Copilot vía `get_dm_agent().process_dm()` en `copilot/messaging.py:297`. No se verifican mutuamente.
- **Estado actual:** Bot Orchestrator efectivamente orphan en runtime (solo tests lo importan — audit B.2a confirmó). No hay conflicto en prod.
- **Impacto si Bot Orchestrator se reactivara:** Respuestas duplicadas al mismo lead.
- **Recomendación:** Confirmar Bot Orchestrator como HIBERNAR (B.2a recommendation). Si se reactiva, mutual exclusion con Copilot obligatoria.

#### 1.5 Debounce Regeneration ↔ Creator Reply — Race condition

- **Sistemas:** T1#93 Copilot debounce (`copilot/messaging.py:249-365`) ↔ Creator manual reply
- **Evidencia:** Debounce espera `DEBOUNCE_SECONDS` (20s) y luego regenera. Check `has_creator_reply_after()` solo verifica DESPUÉS del sleep. Si creator responde a T+19s (durante sleep), a T+20s el debounce regenera y sobrescribe la sugerencia que ya fue respondida.
- **Impacto:** **BUG EN PROD** — la regeneración puede sobrescribir una sugerencia que el creator ya respondió manualmente. El frontend muestra la regenerada, pero el creator ya envió otra cosa.
- **Recomendación:** 🔴 **FIX INMEDIATO.** Verificar `has_creator_reply_after(timestamp_start_of_debounce)` no `timestamp_end_of_debounce`.

---

### Tipo 2 — Redundancias

| # | Par | Grupo | Evidencia | Acción propuesta |
|---|-----|-------|-----------|-----------------|
| 2.1 | Few-Shot ↔ Episodic Memory | PROMPT | Ambos proveen ejemplos de comportamiento. Few-shot: abstracto (RoleLLM). Episodic: raw snippets. Mismo Recalling block. | Aceptable si gating correcto (episodic gate: ≥15 chars + ≥3 words). Monitorizar token waste. |
| 2.2 | Memory Engine ↔ Episodic Memory | PROMPT | ME inyecta facts extraídos; Episodic inyecta snippets raw del mismo historial. Ambos en POS 4 Recalling. context.py:193-199 ya deduplica episodic vs history. | LOW risk — dedup gate activo. |
| 2.3 | Memory Engine ↔ Hierarchical Memory | PROMPT | HierMem L2 = semantic (duplica ME facts). HierMem L1 = episodic (duplica Episodic). Ambos OFF por defecto. | Mutual exclusion: solo uno de {ME, HierarchicalMemory} ON a la vez. |
| 2.4 | RAG ↔ Knowledge Base | PROMPT | RAG: pgvector semantic search sobre content_chunks (product_catalog, faq, knowledge_base). KB: keyword lookup in-memory del mismo source. Sin dedup. | Fusionar KB INTO RAG como fallback keyword. |
| 2.5 | Length Hints ↔ Question Hints | PROMPT | Ambos appended a context_notes (lines 892, 907). Pueden contradecirse: "NO pregunta" + "responde brevemente" cuando el contexto requiere pregunta. | LOW — contradicción real es rara. Documentar como design intent. |
| 2.6 | Gold Examples ↔ Calibration Few-Shot | PROMPT | Dual few-shot injection si Gold flag ON. Calibration: SYSTEM prompt POS 2. Gold: USER message USR 2. No mutual exclusion guard. CROSS_SYSTEM Issue #1 ya documentado. | **BLOQUEANTE para activar #37.** Añadir guard mutual exclusion. |
| 2.7 | Style Anchor ↔ Length Hint | PROMPT×POST | Style Anchor (generation.py:139): "mensajes ~180 chars". Length Hint (context.py:892): "Responde ~50 chars". Targets contradictorios. Anchor en USER message = mayor atención. | **Resolver ANTES de activar #26.** Unificar fuente de length target. |
| 2.8 | Question Hints ↔ Question Remover | POST | Generación: "NO incluyas pregunta" (pre-LLM). Postprocessing: elimina preguntas (post-LLM). Doble supresión. | COMPLEMENTARIEDAD aceptable — dual layer safety. Pero ambos flags deben ser independientes. |
| 2.9 | Loop Detectors A2/A2b/A2c | POST | Tres detectores secuenciales: A2 exact, A2b intra-char, A2c sentence-level. Granularidades distintas. | NO conflict — layered defense correcto. |
| 2.10 | CT ↔ ME commitments | MEMORIA | CT: `commitments` table con due_date. ME: puede extraer misma commitment como fact. Prompt duplicación posible. | Filtrar ME facts con fact_type="commitment" si commitment_text ya inyectado. |
| 2.11 | Task Scheduler ↔ Nurturing Scheduler | INFRA | Dos scheduling systems: TaskScheduler (30+ jobs) + Nurturing loop separado (5m ciclo). Delay 30s insuficiente. | Integrar Nurturing como job dentro de TaskScheduler. |
| 2.12 | ME fire-and-forget ↔ Copilot Actions memory | INFRA | Bot Orchestrator lanza async memory extraction (sin await). Copilot TAMBIÉN actualiza memory sync (actions.py:179-191). Race: memory escrita 2x o en orden incorrecto. | Unificar punto de extracción de memory. |

---

### Tipo 3 — Acoplamientos implícitos

| # | Par | Dependencia | Riesgo | Hacer explícito |
|---|-----|------------|--------|----------------|
| 3.1 | Doc D ↔ Few-Shot | Few-shot filtrado por Doc D blacklist. Si blacklist cambia, few-shot degrada sin regeneración. | MEDIO | Añadir cache invalidation cuando blacklist cambia. |
| 3.2 | Doc D ↔ Response Variator | Variator lee Doc D vocabulary para pool. Cache no invalida on Doc D update. | BAJO | Documentar; invalidar cache on Doc D update. |
| 3.3 | RAG ↔ Relationship Scorer | RAG runs BEFORE scorer finishes. RAG retrieves products even if scorer will suppress them → token waste. | MEDIO | Pasar is_friend a RAG gate para skip product retrieval. |
| 3.4 | Length Hints ↔ Length Controller | Pre-LLM soft guidance vs post-LLM hard truncation. Controller wins (ejecuta último), wasting LLM effort. | ALTO | Unificar config de length: hints + controller deben leer mismo target. |
| 3.5 | Echo Detector ↔ Calibration pools | A3 usa `short_response_pool` de calibration para reemplazar echoes. Si pool vacío, A3 degrada a log-only. | BAJO | Garantizar pool population durante calibration. |
| 3.6 | Payment Link ↔ Length Controller | Payment Link Inject (step 15) appends link DESPUÉS de Length Controller (step 12). Viola soft/hard_max. | ALTO | Reservar budget para payment link en Length Controller. |
| 3.7 | Pool Matching ↔ Response Variator | Variator filtra silenciosamente vía soft_max, TF-IDF reranking, dedup reset. Pool Matching no ve estos filtros. | ALTO | Exponer dedup state en PoolMatch result. |
| 3.8 | Few-Shot ↔ Pool Matching | Intent override (media_share) ignorado por Intent classifier. Few-Shot carga examples para Intent.OTHER en vez de media_share. | MEDIO | Propagate intent_override a IntentClassifier. |
| 3.9 | Conv Boundary ↔ Context Detector | Conv Boundary NO llamado en Phase 1. Context Detector busca en historial cross-session. | BAJO | Integrar Conv Boundary en Phase 1 para limitar context a sesión actual. |
| 3.10 | Copilot ↔ Best-of-N | Best-of-N metadata acoplada a Copilot. Si BoN falla, Copilot suggestions stale. Edit diff depende de BoN. | ALTO | Hacer acoplamiento explícito; fallback si BoN unavailable. |
| 3.11 | Persona Compiler ↔ Copilot Eval | PC triggered por weekly recalibration que analiza daily evals. Si eval skip, PC recibe señales stale. | MEDIO | Documentar cadena; marcar signals con timestamp + TTL. |
| 3.12 | Pattern Analyzer ↔ Persona Compiler | Ambos leen/escriben PreferencePair. batch_analyzed_at race posible. | MEDIO | Añadir locking o ordering explícito. |
| 3.13 | DNA Auto Create ↔ DNA Auto Analyze | Auto Analyze reads DNA created by Auto Create. Si Auto Analyze fires antes de seed write, returns early → lead sin DNA. | ALTO | Make Auto Create synchronous (await) before Auto Analyze check. |
| 3.14 | Memory Engine ↔ Consolidator | ME checks is_consolidation_locked() pero continúa anyway. Consolidator deactivates facts while ME mid-read → dedup leak. | ALTO | Wrap ME.add() en transaction; o defer to consolidation phase. |
| 3.15 | Ghost Reactivation ↔ Score Decay | Ambos iteran creators (limit 200). Ghost activa lead justo cuando Score Decay recalcula → score pre-reactivación persiste. | MEDIO | Documentar; no fix urgente. |
| 3.16 | Copilot Mode Cache ↔ DB | 60s TTL. Creator toggling copilot_mode no propagado hasta cache expires. | MEDIO | Add explicit invalidation on mode toggle. |

---

### Tipo 4 — Context pollution

| # | Par | Tokens redundantes est. | Budget impact | Acción |
|---|-----|------------------------|---------------|--------|
| 4.1 | ME + Episodic + HierMem (triple memory injection) | ~2500 chars (~625 tokens) | 31% de MAX_CONTEXT_CHARS=8000 | Mutual exclusion o budget cap por grupo. |
| 4.2 | CT + ME commitments duplicados | ~200 chars (~50 tokens) | 2.5% | Filtrar ME fact_type="commitment" si CT activo. |
| 4.3 | DNA recurring_topics + ME topic facts | ~100 chars (~25 tokens) | Negligible | No acción — abstraction levels distintos. |
| 4.4 | Conv Boundary stale turn_index ↔ Pool question weighting | N/A (gating, no injection) | Calidad de pool selection | Integrar Conv Boundary en Phase 1. |
| 4.5 | Media Placeholder intent_override ignorado | N/A (classification error) | Wrong few-shot examples | Propagate override. |
| 4.6 | Score Decay ↔ Clone Eval timing | N/A (evaluation accuracy) | Non-deterministic scores | Documentar; aceptable. |
| 4.7 | Copilot Mode Cache stale | N/A (UX delay) | 60s latency | Add invalidation. |
| 4.8 | Clone Eval nested DB sessions | N/A (resource contention) | Pool stress | Refactor to single session per creator. |

---

### Tipo 5 — Problemas de orden

| # | Par | Orden actual | Orden correcto | Impacto |
|---|-----|-------------|---------------|---------|
| 5.1 | Strategy ↔ Question Hint ↔ Preference Profile (user msg) | Pref[USR1] → Gold[USR2] → Strategy[USR3] → QHint[USR4] → Msg[USR5] | Correcto conceptualmente pero Pref = menor atención (primero). | LOW — Pref OFF por defecto. |
| 5.2 | Style Anchor ↔ Length Hint | Length Hint en SYSTEM prompt, Style Anchor appended último en USER message (mayor atención). | Si Style Anchor dice "~180 chars" y Length Hint dice "~50 chars", Anchor gana → LLM genera largo. | **Resolver ANTES de activar #26.** |
| 5.3 | Intent Service ↔ Context Detector (phase inversion) | Context Signals (Phase 1) → Intent (Phase 2-3) → Few-Shot (Phase 2-3). | Intent ANTES de Few-Shot ✓. Pero Context Signals shapes intent retrospectively. | MEDIUM — wrong intent → wrong examples. |
| 5.4 | DNA Triggers ↔ DNA Auto Analyze (race) | Ambos fires on same message sin mutex. Inline check context.py:498 + DNAUpdateTriggers class. | Solo uno debe evaluar per lead per message interval. | **FIX — ya reportado en B.2a.** |
| 5.5 | Memory Decay ↔ Memory access counter | Decay reads last_accessed_at + times_accessed. Recall() incrementa counter. Race: decay usa counter stale → deactiva fact "fresh". | Añadir lock o snapshot isolation para decay. | MEDIUM. |
| 5.6 | Commitment detection lag (1 msg delay) | detect_and_store() async fire-and-forget → commitment visible msg N+1. | Make detect_and_store() sync (await). +10-50ms. | LOW-MEDIUM. |
| 5.7 | Timing Service ↔ Nurturing follow-ups | Timing blocks 23h-8h. Nurturing envía follow-ups 24h window sin check active hours. | Follow-ups queued off-hours → burst a las 8am. | MEDIUM — **Resolver ANTES de activar #115.** |

---

### Tipo 6 — Complementariedades positivas

| # | Par | Sinergia | Valor |
|---|-----|---------|-------|
| 6.1 | Doc D ↔ ECHO Style Analyzer | Analyzer appends quantitative metrics a Doc D. Declarativo + cuantitativo. | ALTO — by design. |
| 6.2 | Loop Detectors + Echo Detector | A2 (exact) + A2b (char) + A2c (sentence) + A3 (Jaccard). Capas complementarias. | ALTO — layered defense. |
| 6.3 | Question Hints + Question Remover | Pre-LLM suppression + post-LLM removal. Dual safety layer. | ALTO — belt + suspenders. |
| 6.4 | Length Controller + Message Splitter | Controller enforces per-msg limit. Splitter crea multi-bubble cuando excede. Compatible. | ALTO. |
| 6.5 | Memory Engine ↔ Consolidator | ME: fast insert (fire-and-forget). Consolidator: batch dedup (periodic). Complementary pattern. | ALTO — matches CC autoDream. |
| 6.6 | DNA Engine ↔ Relationship Analyzer | Analyzer: data producer (compute relationship). Engine: data consumer (format + inject). Pipeline claro. | ALTO. |
| 6.7 | Sensitive Detector ↔ Prompt Injection | Sensitive: fail-closed (escalate). Injection: observational (flag). Patrones distintos, acciones distintas. | MEDIO. |
| 6.8 | Bot Orchestrator ↔ Timing Service | Timing gates bot responses vía is_active_hours(). Pure composition. | BAJO — correcto. |
| 6.9 | DNA Auto Create ↔ DNA Auto Analyze | Seed (msg 2) → Full analysis (msg 5). Progressive enrichment. | MEDIO — timing OK si race resuelto. |

---

## Impacto sobre decisiones pendientes

### Candidatos T2 ACTIVAR-MEDIR — reclasificación por competencia

| # | Sistema T2 | Tipo 1 con WL/T1? | Tipo 5? | Otros bloqueantes | Veredicto |
|---|-----------|-------------------|---------|-------------------|-----------|
| **#15** | Best-of-N | **SÍ** — 1.2 (Confidence ↔ Question Remover), 1.3 (scoring ciego a postprocessing) | — | 3.10 (Copilot acoplamiento) | 🔴 **BLOQUEADO.** Resolver 1.2 + 1.3 antes de activar. Estimado: 4-6h refactor confidence scorer. |
| **#21** | History Compactor | NO | NO | — | 🟢 **DESBLOQUEADO.** Sin competencia detectada. Activar con ENABLE_HISTORY_COMPACTION=true only (sin summary). |
| **#24** | Length Hints | NO | 5.2 (Style Anchor conflict) | 3.4 (Length Controller acoplamiento) | 🟡 **DESBLOQUEADO con precaución.** Activar solo si #26 Style Anchor NO se activa simultáneamente. Si ambos, resolver 5.2 primero. |
| **#25** | Question Hints | NO | NO | — | 🟢 **DESBLOQUEADO.** Complementario con Question Remover (6.3). Sin competencia. |
| **#26** | Style Anchor | NO | **SÍ** — 5.2 (↔ Length Hint) | 2.7 (redundancia con Length Hint) | 🟡 **DESBLOQUEADO con condición.** Resolver 5.2: Style Anchor length target debe leer MISMA fuente que Length Hints (length_by_intent.json). Fix: 2h. |
| **#37** | Gold Examples | NO | NO | **2.6** (dual few-shot ↔ Calibration) | 🔴 **BLOQUEADO.** Añadir mutual exclusion guard con Calibration Few-Shot ANTES de activar. Fix: 1h. |
| **#40** | Persona Compiler | NO | NO | 3.11 (↔ Copilot Eval), 3.12 (↔ Pattern Analyzer) | 🟢 **DESBLOQUEADO.** Acoplamientos documentados pero no bloqueantes — PC es batch offline. |
| **#115** | Nurturing | NO | **SÍ** — 5.7 (Timing ↔ Nurturing off-hours burst) | 2.11 (dual scheduler) | 🟡 **DESBLOQUEADO con condición.** Coordinar with Timing Service active hours check. Fix: 2h. |

**Resumen: 5 de 8 desbloqueados (3 🟢, 2 🟡). 2 bloqueados (🔴). 1 bloqueado con condición fácil (🟡→🟢 tras 1h fix).**

**Orden de activación recomendado post-matrix:**
1. **#25 Question Hints** (🟢, 1h, zero risk)
2. **#21 History Compactor** (🟢, 3-4h, low risk)
3. **#24 Length Hints** (🟢 si solo, 1h)
4. **#40 Persona Compiler** (🟢, 6-8h, batch)
5. **#26 Style Anchor** (🟡, 2h fix + 2h activar = 4h total)
6. **#37 Gold Examples** (🔴→🟢, 1h fix + 3h activar = 4h total)
7. **#115 Nurturing** (🟡, 2h fix + 8h activar = 10h total)
8. **#15 Best-of-N** (🔴, 4-6h fix + 2h activar = 8h total, copilot only)

---

### Sistemas T1 con interacciones en prod descubiertos

Estos problemas están EN PRODUCCIÓN AHORA y NO fueron vistos en los audits individuales B.2a/B.2b:

| # | Issue | Sistemas | Evidencia | Impacto prod |
|---|-------|---------|-----------|-------------|
| **P1** | 🔴 Debounce race condition | #93 Copilot debounce | copilot/messaging.py:249-365. Creator reply at T+19s, debounce regenera at T+20s, sobrescribe sugerencia ya respondida. | **Corrupción de sugerencias Copilot** cuando creator responde rápido. |
| **P2** | Payment Link viola length bounds | WL#9 Length Controller ↔ WL postprocessing | postprocessing.py:358,378-393. Payment link appended DESPUÉS de length enforcement. Viola soft/hard_max. | Mensajes de precio más largos de lo esperado. Cosmético. |
| **P3** | Intent override leakage (media_share) | T1#31 Media Placeholder ↔ T1#64 Intent Service | detection.py:143 sets intent_override. IntentService ignores it. Wrong few-shot examples para media messages. | Few-shot examples irrelevantes cuando lead envía media. Quality hit menor. |

---

## Propuestas para ARC1 (budget orchestrator)

### Decisiones arquitectónicas requeridas

1. **Jerarquía de sistemas prompt-injection (quién gana si contradicen)**
   - **Propuesta:** Doc D > Style Anchor > Length Hints > DNA > Relationship Adapter
   - **Razón:** Doc D es la fuente de verdad del creator. Los demás son data-driven reinforcement. Si contradicen, Doc D prevalece.
   - **Implementación:** En caso de conflicto length (Style Anchor vs Length Hint), usar valor de Doc D baseline_metrics como tiebreaker.

2. **Budget por sección del prompt**
   - **Propuesta:** MAX_CONTEXT_CHARS=8000 distribuido:
     - Style (Doc D + ECHO): 2000 chars (25%)
     - Recalling block: 2500 chars (31%) — incluye DNA, state, episodic, memory, CT
     - Few-shot: 1000 chars (12.5%)
     - RAG + KB: 1500 chars (19%)
     - Extras (audio, citation, override): 1000 chars (12.5%)
   - **Razón:** Recalling es el bloque más variable (crece con lead history). Caparlo previene que squeeze a RAG.

3. **Orden de precedencia para context injection**
   - **Actual:** Correcto (Doc D primero → mayor prioridad). Confirmado en audit.
   - **Pendiente:** Definir qué pasa cuando recalling_block excede budget → qué sub-blocks se truncan primero.
   - **Propuesta:** Truncar en orden inverso de valor: citation → advanced → hier_memory → episodic → context_notes → frustration → state → memory → dna (último en truncar).

4. **Mutual exclusion guards**
   - Gold Examples ↔ Calibration Few-Shot: añadir `if not gold_examples_section: inject calibration`
   - Hierarchical Memory ↔ Memory Engine: añadir `if ENABLE_HIERARCHICAL_MEMORY: skip memory_engine recall()`
   - Style Anchor length ↔ Length Hints: leer misma fuente (`length_by_intent.json`)

5. **Estrategia de fusión para outputs de misma dimensión**
   - **Style dimension:** Doc D (declarative) + ECHO Analyzer (quantitative) + Style Anchor (numerical reminder) → fusionar en un solo bloque de estilo con prioridad Doc D.
   - **Memory dimension:** ME facts + Episodic snippets → dedup activo (ya implementado context.py:193). CT commitments → filtrar de ME si ya en CT.
   - **Tone dimension:** DNA + Relationship Adapter → fusionar en un solo bloque si ambos activos.

---

## Matriz visual (condensada por grupo funcional)

Leyenda: `1`=competencia, `2`=redundancia, `3`=acoplamiento, `4`=pollution, `5`=orden, `6`=complementario, `·`=no interacción, `—`=mismo sistema.

### PROMPT-INJECTION (filas) × PROMPT-INJECTION (columnas)

```
              DocD  CalFew  MemEng  DNA   ConvSt  CtxDet  FrustD  SensD  RelSc  ECHO   RAG    KB    EpisMem  SemMem  CitSvc  BM25  StylAn  HistCp  LenH  QuesH  StylAnc  GoldEx  PersCp
DocD           —     3,2     ·       ·      ·       ·       ·       ·      ·     6       ·      ·       ·        ·       ·      ·     ·        ·     ·      ·       ·       ·       3
CalFew        3,2    —       ·       ·      ·       ·       ·       ·      ·     ·       ·      ·       2        ·       ·      ·     ·        ·     ·      ·       ·      2,3      ·
MemEng         ·     ·       —       ·      ·       ·       ·       ·      ·     ·       ·      ·       2,4      2       ·      ·     ·        ·     ·      ·       ·       ·       ·
DNA            ·     ·       ·       —      ·       ·       ·       ·      ·     1       ·      ·       ·        ·       ·      ·     ·        ·     ·      ·       ·       ·       ·
RAG            ·     ·       ·       ·      ·       ·       ·       ·      3     ·       —      2       ·        ·       ·      ·     ·        ·     ·      ·       ·       ·       ·
LenH           ·     ·       ·       ·      ·       ·       ·       ·      ·     ·       ·      ·       ·        ·       ·      ·     ·        ·     —      2       2,5      ·       ·
QuesH          ·     ·       ·       ·      ·       ·       ·       ·      ·     ·       ·      ·       ·        ·       ·      ·     ·        ·     2      —       ·       ·       ·
StylAnc        ·     ·       ·       ·      ·       ·       ·       ·      ·     ·       ·      ·       ·        ·       ·      ·     ·        ·    2,5     ·       —       ·       ·
GoldEx         ·    2,3      ·       ·      ·       ·       ·       ·      ·     ·       ·      ·       ·        ·       ·      ·     ·        ·     ·      ·       ·       —       ·
```

### POSTPROCESSING (filas) × PROMPT-INJECTION (columnas) — cross-grupo

```
              LenH   QuesH  StylAnc  GoldEx  BestN
LenCtrl       3,5     ·       ·        ·       ·
StylNorm       ·      ·       ·        ·       ·
QuesRem        ·      6       ·        ·       1
PayLink       3       ·       ·        ·       ·
BestN          ·      ·       ·        ·       —
```

### MEMORIA/STATE (filas) × MEMORIA/STATE (columnas) — intra-grupo

```
              MemEng  DNA   ConvSt  EpisMem  Consol  LLMCon  RelAn  DNATrig  AutoCr  AutoAn  CreaPrf  CommTr  PersCp
MemEng          —      ·      ·       2,4     3,5      3       ·       ·        ·       ·        ·      2       ·
DNA             ·      —      ·       ·        ·       ·       6       ·        ·       ·        ·      ·       ·
EpisMem        2,4     ·      ·       —        ·       ·       ·       ·        ·       ·        ·      ·       ·
Consol         3,5     ·      ·       ·        —       3       ·       ·        ·       ·        ·      ·       ·
DNATrig         ·      ·      ·       ·        ·       ·       3       —        ·       5        ·      ·       ·
AutoCr          ·      ·      ·       ·        ·       ·       ·       ·        —       3        ·      ·       ·
CommTr          2      ·      ·       ·        ·       ·       ·       ·        ·       ·        ·      —       ·
PersCp          ·      ·      ·       ·        ·       ·       ·       ·        ·       ·        3      ·       —
```

---

## Resumen final

### Distribución por tipo

```
TIPO 1 COMPETENCIA   █████               5   (10%)
TIPO 2 REDUNDANCIA   ████████████        12  (23%)
TIPO 3 ACOPLAMIENTO  ████████████████    16  (31%)
TIPO 4 POLLUTION     ████████            8   (15%)
TIPO 5 ORDEN         ███████             7   (13%)
TIPO 6 COMPLEMENTAR  █████████           9   (17%)  [no-issue, documentar]
```

### Top 5 issues bloqueantes para ARC1

1. 🔴 **Best-of-N scoring ciego a postprocessing** (1.3) — invalida el propósito del sistema si se activa sin fix
2. 🔴 **Gold Examples ↔ Few-Shot dual injection** (2.6) — sin mutual exclusion, dos sets de examples compiten
3. 🔴 **Debounce race condition** (1.5) — bug EN PROD que corrompe sugerencias Copilot
4. 🟠 **Length Hints ↔ Style Anchor ↔ Length Controller** (2.7 + 3.4 + 5.2) — tres sistemas con targets contradictorios
5. 🟠 **Triple memory injection** (4.1) — ME + Episodic + HierMem consumen 31% del budget sin dedup cross-system

### Sistemas T2 desbloqueados para ACTIVAR-MEDIR

| Sistema | Status | Prerequisito |
|---------|--------|-------------|
| #25 Question Hints | 🟢 GO | Ninguno |
| #21 History Compactor | 🟢 GO | Solo ENABLE_HISTORY_COMPACTION (sin summary) |
| #24 Length Hints | 🟢 GO | Solo si #26 Style Anchor NO se activa a la vez |
| #40 Persona Compiler | 🟢 GO | Batch offline, sin conflicto runtime |
| #26 Style Anchor | 🟡 FIX FIRST | Unificar length target con Length Hints (2h) |
| #115 Nurturing | 🟡 FIX FIRST | Coordinar con Timing Service active hours (2h) |
| #37 Gold Examples | 🔴 FIX FIRST | Mutual exclusion con Few-Shot (1h) |
| #15 Best-of-N | 🔴 FIX FIRST | Refactor confidence scorer para postprocessing-aware (4-6h) |

### Sistemas T1 con problemas en prod descubiertos

1. 🔴 **Copilot debounce race** — sugerencias sobrescritas si creator responde durante debounce window
2. 🟡 **Payment Link viola length bounds** — cosmético pero incorrecto
3. 🟡 **Intent override media_share ignorado** — wrong few-shot examples para media messages
