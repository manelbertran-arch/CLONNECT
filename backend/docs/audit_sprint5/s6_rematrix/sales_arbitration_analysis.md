# Sales Arbitration — Fase 1: Análisis Forense

**Fecha:** 2026-04-21 | **Branch:** `feat/s6-sell-arbitration`

---

## Los 4 Sistemas: Mapa Completo

### Sistema #1: DNA Engine — "NUNCA vender"

| Campo | Valor |
|-------|-------|
| **Input** | `relationship_dna` table → `relationship_type` field (persistent, updated by triggers) |
| **Output** | Text hint: `"Relación: FAMILIA (Familiar directo — trato cariñoso, personal, NUNCA vender)"` |
| **Injection** | `_build_recalling_block(dna=dna_context)` → recalling position 2 |
| **When** | Phase 2-3: DNA loaded in parallel IO (context.py:~860), formatted via `_format_dna_for_prompt()` |
| **Sell-relevant values** | FAMILIA → "NUNCA vender", INTIMA → "muy cercana" (no explicit sell ban), rest → neutral |

**Source code:**
- Hint map: `dm_agent_context_integration.py:172-182`
- FAMILIA hint: `dm_agent_context_integration.py:173` — literal "NUNCA vender"
- Injected at: `context.py:1508` (`dna=dna_context`)

**Key detail:** Only FAMILIA has an explicit sell prohibition. INTIMA, AMISTAD_CERCANA etc. have tone guidance but no sell directive. The sell signal is binary: FAMILIA = "NUNCA", everything else = silent.

---

### Sistema #2: Conversation State — "Menciona el producto"

| Campo | Valor |
|-------|-------|
| **Input** | `ConversationState.phase` enum (per-lead persistent state) |
| **Output** | Text instruction block with explicit sell actions |
| **Injection** | `_build_recalling_block(state=state_context)` → recalling position 3 |
| **When** | Phase 2-3: retrieved from StateManager (context.py:839-842) |
| **Sell-relevant phases** | PROPUESTA → "Menciona el producto", CIERRE → "Da el link de compra" |

**Source code:**
- PROPUESTA: `conversation_state.py:104-110` — "Menciona el producto que encaja con SU situacion"
- CIERRE: `conversation_state.py:118-124` — "Da el link de compra"
- Injected at: `context.py:1509` (`state=state_context`)

**Key detail:** Conv State transitions are driven by message count + intent only (`conversation_state.py:375-422`). No check for `relationship_type`, `frustration_level`, or `is_friend`. It advances to PROPUESTA/CIERRE regardless of relationship or emotional state.

**Non-sell phases:** INICIO → "NO menciones productos ni precios todavía", CUALIFICACION/DESCUBRIMIENTO → neutral, OBJECIONES → "NO seas pushy", ESCALAR → no sell.

---

### Sistema #3: Frustration Detection — "No vendas ahora"

| Campo | Valor |
|-------|-------|
| **Input** | Current message + conversation history → frustration score (0-1) → level (0-3) |
| **Output** | Text note: `"Nota: el lead parece frustrado ({reasons}). No vendas ahora."` |
| **Injection** | `_build_recalling_block(frustration_note=_frustration_note)` → recalling position 5 |
| **When** | Phase 1: detection.py:252-265. Result carried forward to Phase 3. |
| **Sell-relevant levels** | Level 0-1 → no sell signal. Level 2 → "No vendas ahora". Level 3 → "Prioriza resolver" (implicit no-sell). |

**Source code:**
- Level thresholds: `frustration_detector.py:390-398` (0→<0.30, 1→<0.40, 2→<0.80, 3→≥0.80)
- Level 1 note: `context.py:1370` — "puede estar algo molesto" (no sell directive)
- Level 2 note: `context.py:1373-1375` — "No vendas ahora" (explicit)
- Level 3 note: `context.py:1378-1381` — "Prioriza resolver su problema" (implicit)
- Injected at: `context.py:1510` (`frustration_note=_frustration_note`)

**Key detail:** Level 1 does NOT suppress selling. Only level ≥ 2 has "No vendas ahora". Level 3 escalates to "resolver o escalar" without explicit no-sell, but the implication is clear.

---

### Sistema #4: Relationship Scorer — Product Suppression (boolean)

| Campo | Valor |
|-------|-------|
| **Input** | User messages + lead_facts (ARC2 memory) + days_span + leads.status |
| **Output** | Boolean `suppress_products` (score > 0.8) → `is_friend=True` |
| **Injection** | Products stripped from prompt: `prompt_products = [] if inp.is_friend` |
| **When** | Phase 2-3: computed at context.py:1200-1221 after all data loaded |
| **Sell-relevant thresholds** | score > 0.8 → PERSONAL → `suppress_products=True`. 0.6-0.8 → CLOSE → `soft_suppress=True` (metadata only, products kept). |

**Source code:**
- Score computation: `relationship_scorer.py:113-128`
- suppress_products: `relationship_scorer.py:135` — `(total > 0.8)`
- is_friend extraction: `context.py:1221` — `is_friend = _rel_score.suppress_products`
- Product removal: `context.py:469` and `context.py:592` — `prompt_products = [] if inp.is_friend`
- Passed to assembly: `context.py:1529` (`is_friend=is_friend`)

**Key detail:** This is the ONLY system that operates on DATA availability (removes products from prompt), not on TEXT instructions. The other 3 produce text hints that the LLM may or may not follow. This one physically removes product data.

---

## Punto de Convergencia: `_build_recalling_block()`

**Location:** `context.py:1335-1360`

```python
parts = [p for p in [relational, dna, state, episodic, frustration_note, context_notes, memory] if p]
```

**Orden de inyección (context.py:1353):**
1. `relational` — RelationshipAdapter (ECHO data-only when has_doc_d)
2. **`dna`** ← Sistema #1 — "NUNCA vender" si FAMILIA
3. **`state`** ← Sistema #2 — "Menciona el producto" si PROPUESTA/CIERRE
4. `episodic` — (OFF)
5. **`frustration_note`** ← Sistema #3 — "No vendas ahora" si level ≥ 2
6. `context_notes` — Context Detection
7. `memory` — ARC2

**Attention positions (Liu et al. 2023):** Pos 2 (DNA) y 3 (State) → alta atención. Pos 5 (Frustration) → valle de atención medio. Pos 7 (Memory) → alta atención final.

**Sistema #4 opera fuera del recalling block** — actúa sobre `prompt_products` en la función `_assemble_context()` (context.py:469, 592), no dentro del bloque de texto.

---

## Los 3 Tipo 1 Confirmados

### R.4: DNA FAMILIA + Conv State PROPUESTA

**Escenario:** Lead es familiar del creator (madre, hermano) → DNA dice FAMILIA. Pero lleva suficientes mensajes o mostró interés → Conv State avanza a PROPUESTA.

**En el prompt:**
```
Pos 2: "Relación: FAMILIA (Familiar directo — trato cariñoso, personal, NUNCA vender)"
Pos 3: "FASE: PROPUESTA - Menciona el producto que encaja con SU situacion"
```

**Contradicción:** "NUNCA vender" vs "Menciona el producto". Directa, sin ambigüedad.

**Por qué ocurre:** Conv State no lee `relationship_type`. Sus transiciones (`conversation_state.py:375-422`) solo usan message_count e intent. Avanza a PROPUESTA sin saber que el lead es FAMILIA.

---

### R.5: Conv State CIERRE + Frustration Level 2+

**Escenario:** Lead en fase CIERRE (quiere comprar), pero envía mensaje frustrado ("LLEVO 3 DÍAS ESPERANDO!!") → Frustration detecta level 2-3.

**En el prompt:**
```
Pos 3: "FASE: CIERRE - Da el link de compra"
Pos 5: "Nota: el lead parece frustrado (service_delay). No vendas ahora."
```

**Contradicción:** "Da el link de compra" vs "No vendas ahora". Directa.

**Por qué ocurre:** Frustration no modifica Conv State phase. No hay transición de CIERRE → ESCALAR por frustration. Las transiciones de Conv State son independientes de estado emocional.

---

### C.8: Conv State PROPUESTA + Scorer PERSONAL

**Escenario:** Lead tiene relación muy cercana (score > 0.8, muchos mensajes, personal markers en memoria) → Scorer dice `is_friend=True`. Pero Conv State en PROPUESTA.

**En el prompt:**
```
Pos 3: "FASE: PROPUESTA - Menciona el producto que encaja con SU situacion"
Pero: prompt_products = [] (products physically removed)
```

**Contradicción:** El modelo recibe instrucción de "mencionar producto" pero NO tiene productos disponibles en su contexto. Riesgo de alucinación: el modelo inventa productos para seguir la instrucción.

**Por qué ocurre:** Conv State no chequea `is_friend`. Scorer no modifica Conv State instructions.

---

## Escenarios Adicionales No Documentados

### R.4b: DNA FAMILIA + Scorer NOT PERSONAL

**Escenario:** DNA dice FAMILIA pero Scorer computa score < 0.8 (e.g., familiar con pocos mensajes, sin personal markers en ARC2 memory).

**En el prompt:** DNA dice "NUNCA vender" pero productos ESTÁN en el prompt (no suppressed).

**Impacto:** Menor que R.4 — el modelo tiene la instrucción "NUNCA vender" y puede seguirla sin conflicto. Pero si Conv State está en PROPUESTA, tenemos R.4 con productos disponibles → el modelo podría mencionar uno.

### R.5b: Frustration Level 3 + CIERRE

**Escenario:** Igual que R.5 pero frustration level 3.

**En el prompt:**
```
Pos 3: "FASE: CIERRE - Da el link de compra"
Pos 5: "Nota: el lead está muy frustrado. Prioriza resolver su problema o escalar a creator_id."
```

**Impacto:** Similar a R.5 pero level 3 no dice explícitamente "No vendas" — dice "Prioriza resolver". Menos directa la contradicción pero más peligroso el escenario (lead en escalation y recibiendo link de compra).

### C.8b: DNA FAMILIA + Scorer PERSONAL

**Escenario:** Doble supresión — DNA dice "NUNCA vender" Y products removed.

**En el prompt:** Alineados (ambos suprimen). Sin contradicción. Este caso funciona correctamente.

---

## Tabla de Decisión Completa (Combinaciones Relevantes)

| DNA type | Conv Phase | Frust Level | Scorer | Contradicción | ID |
|----------|-----------|-------------|--------|---------------|-----|
| FAMILIA | PROPUESTA | 0-1 | <0.8 | **SÍ — R.4** | NUNCA vender + Menciona producto + products available |
| FAMILIA | PROPUESTA | 0-1 | >0.8 | **Parcial** | NUNCA vender + Menciona producto + NO products |
| FAMILIA | CIERRE | 0-1 | <0.8 | **SÍ — R.4 variant** | NUNCA vender + Da link + products available |
| ANY | PROPUESTA | 2 | <0.8 | **SÍ — R.5** | Menciona producto + No vendas ahora |
| ANY | CIERRE | 2+ | <0.8 | **SÍ — R.5** | Da link + No vendas ahora |
| ANY | PROPUESTA | 0-1 | >0.8 | **SÍ — C.8** | Menciona producto + no products in prompt |
| ANY | CIERRE | 0-1 | >0.8 | **SÍ — C.8 variant** | Da link + no products in prompt |
| FAMILIA | PROPUESTA | 2+ | >0.8 | **Triple** | NUNCA + Menciona + No vendas + no products |
| non-FAM | non-SELL | 0-1 | <0.8 | **No** | Sin conflicto — no sell signals active |
| FAMILIA | non-SELL | 0-1 | any | **No** | NUNCA vender + no sell phase → aligned |
| non-FAM | PROPUESTA | 0-1 | <0.8 | **No** | Sell phase + products available → clean sell |

---

## Signal Timing Summary

```
Phase 1 (detection.py)     Phase 2-3 (context.py)              Assembly
─────────────────────     ──────────────────────────           ──────────
[Frustration detected]     [DNA loaded from DB]                 ┌─────────────────────┐
  level: 0/1/2/3          [Conv State retrieved]               │ _build_recalling_block│
                           [Memory loaded (ARC2)]               │  pos 2: DNA hint     │
                           [Scorer computed: is_friend]          │  pos 3: State instr  │
                                                                │  pos 5: Frust note   │
                                                                └─────────────────────┘
                                                                        +
                                                                is_friend → products stripped
```

**Key architectural insight:** All 4 outputs converge at a SINGLE point — the call to `_build_recalling_block()` at context.py:1504-1513 + the `is_friend` flag at context.py:1529. This is where an arbitrator must be inserted.

---

## Propuesta de Punto de Inserción del Árbitro

**ANTES de** context.py:1504 (recalling block assembly), **DESPUÉS de** context.py:1221 (scorer computed).

En este punto disponemos de:
- `dna_context` (ya formateado, contiene relationship_type text)
- `state_context` (ya formateado, contiene phase instructions text)
- `_frustration_note` (ya formateado, contiene "No vendas ahora" o vacío)
- `is_friend` (boolean del Scorer)

El árbitro puede:
1. Leer los 4 outputs
2. Decidir la directiva canónica
3. Modificar/eliminar las instrucciones de sell contradictorias antes de pasar a `_build_recalling_block()`
4. Decidir si `is_friend` debe forzarse a True/False

---

*Fase 1 análisis forense completado. Los 4 sistemas verificados con file:line citations. 3 Tipo 1 confirmados + 3 escenarios adicionales documentados. Punto de inserción del árbitro identificado: context.py entre lines 1221 y 1504.*

**STOP — awaiting proceed for Fase 2 (diseño arquitectónico).**
