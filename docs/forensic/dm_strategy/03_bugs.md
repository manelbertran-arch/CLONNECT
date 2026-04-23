# Fase 3 — Bugs detectados en `dm_strategy`

**Alcance:** `backend/core/dm/strategy.py` (117 LOC) + callsite `backend/core/dm/phases/generation.py:194-206,292-293`.
**Método:** inspección línea a línea + git blame + reproducción sobre dataset `iris_bertran/test_set_v2_stratified.json` + cross-check con `sell_arbitration/arbitration_layer.py`.
**Total:** 14 bugs identificados.

---

## 1. Criterios de severidad

| Nivel | Definición | Acción |
|-------|------------|--------|
| **CRÍTICA** | Bloquea onboarding de un creator nuevo, O introduce regresión medible en prod, O hace sistema inutilizable fuera del creator actual. | Fix obligatorio en Fase 5, bloqueante para PR. |
| **ALTA** | Viola "zero hardcoding" del proyecto, O causa contradicciones sistémicas ya mapeadas entre componentes, O desactiva funcionalidad sin medición. | Fix en Fase 5 dentro del scope. |
| **MEDIA** | Tech debt con impacto acotado y no bloqueante. | Fix en Fase 5 si cabe, sino documentar en `DECISIONS.md` como deuda. |
| **BAJA** | Observabilidad, consistencia interna, naming, o complementos no-funcionales. | Fix oportunista; no bloquea. |

### 1.1 Principio arquitectural aplicable — separación datos lingüísticos vs identidad

Decisión CEO (consistente con Worker 6 Bot Question Analyzer y sistemas data-derived ya vivos: vocab_meta DB marzo 2026, negation reducer, pool auto-extraction, code-switching universal, intent-stratified few-shot):

> **Todo dato lingüístico se DESCUBRE del content mining del creator, NUNCA se preasigna en JSON estático o calibrations por idioma.**

Categorización canónica:

| Categoría | Storage | Origen | Ejemplos |
|-----------|---------|--------|----------|
| **Datos lingüísticos** (mined) | `vocab_meta` DB `(creator_id, vocab_type, value, meta)` | Content mining (posts + DMs históricos) | apelativos, openers a evitar, help_signals, anti-bugs verbales, code-switching triggers |
| **Identidad / config** (preasignada) | `calibrations/{creator}.json` | Setup manual | `creator_display_name`, `product_catalog`, `contact_info`, `languages` (lista de idiomas soportados, no el vocabulario de cada idioma) |

**Implicación para bugs 001, 002, 005:** los 3 fixes iniciales escritos en esta Fase 3 decían "parametrizar desde calibrations/{creator}.json" — **incorrecto** según el principio. Corrigidos abajo hacia `vocab_meta` DB con fallbacks universales sin defaults de Iris. Ver sección 3.

---

## 2. Tabla resumen

| ID | Severidad | Archivo:Línea | Título |
|----|-----------|---------------|--------|
| BUG-DM-STRAT-001 | **CRÍTICA** | `strategy.py:89-90` | Apelativos "nena, tia, flor, cuca, reina" + "personalidad de Iris" hardcoded en P4 RECURRENTE |
| BUG-DM-STRAT-002 | **CRÍTICA** | `strategy.py:86` | Openers prohibidos ES/CA hardcoded en P4 RECURRENTE |
| BUG-DM-STRAT-003 | **ALTA** | `strategy.py:102` × `arbitration_layer.py:25` | Overlap P6 VENTA vs resolver S6 NO_SELL (casos A/B/D) |
| BUG-DM-STRAT-004 | **ALTA** | `generation.py:197,199` + `context.py:1222` | Doble hardcoding `relationship_type=""` + `is_friend=False` desactiva P1/P2 sin CCEE (27d) |
| BUG-DM-STRAT-005 | **ALTA** | `strategy.py:57-61` | `help_signals` 14 strings ES hardcoded inline (sin soporte CA/IT/EN/PT) |
| BUG-DM-STRAT-006 | **ALTA** | `generation.py:194` | Sistema sin flag `ENABLE_DM_STRATEGY_HINT` (impossible de A/B-testar sin cambio de código) |
| BUG-DM-STRAT-007 | **MEDIA** | `strategy.py:82` | Threshold `history_len >= 4` hardcoded, no data-derived del creator baseline |
| BUG-DM-STRAT-008 | **MEDIA** | `strategy.py:45` | Char limit "5-30 chars" en P1 texto libre, no data-derived |
| BUG-DM-STRAT-009 | **MEDIA** | `strategy.py:102` | Duplicación semántica intents (`purchase`/`purchase_intent`, `product_info`/`product_question`) |
| BUG-DM-STRAT-010 | **MEDIA** | `generation.py:205` | Metadata solo guarda primer fragmento (`split(".")[0]`) — imposible A/B testar wording |
| BUG-DM-STRAT-011 | **BAJA** | `strategy.py:19` + `generation.py:200` | `follower_interests` dead param (nunca leído dentro de la función) |
| BUG-DM-STRAT-012 | **BAJA** | `strategy.py` global | Sin métricas Prometheus (`dm_strategy_branch_total{branch}`) |
| BUG-DM-STRAT-013 | **BAJA** | `generation.py:206` | Log f-string no estructurado (no-keyed, no apto para Datadog/OTel) |
| BUG-DM-STRAT-014 | **BAJA** | `dm_agent_v2.py:28` + 3 test files | Re-export con `noqa: F401` + tests distribuidos en 3 archivos |

---

## 3. Detalle por bug

### BUG-DM-STRAT-001 — CRÍTICA — Apelativos + name leak Iris en P4 RECURRENTE

- **Archivo:** `backend/core/dm/strategy.py:89-90`
- **Commit introductor:** `f561819c4` (Manel Bertran, 2026-03-29 10:47:12, "fix(dm): RECURRENTE strategy + pool product guard removal")
- **Código ofensor:**
  ```python
  89      "4) Muestra energía y personalidad de Iris: reacciona con entusiasmo o curiosidad según el contexto, "
  90      "usa apelativos (nena, tia, flor, cuca, reina) — NUNCA la palabra 'flower'."
  ```
- **Problemas embebidos:**
  1. **Name leak** `"Iris"` literal → a Stefano u otro creator futuro se le dirá que muestre personalidad de Iris.
  2. **Vocab ES/CA específico** `"nena, tia, flor, cuca, reina"` → es el vocab del calibrations de Iris. Stefano (IT) usaría otros ("tesoro, amore, bella, cara, piccola"). Otros creadores tendrán sus propios apelativos.
  3. **Anti-bug Iris-específico** `"NUNCA la palabra 'flower'"` → bug observado únicamente en Iris (modelo calcaba inglés→español). No aplica a otros.
- **Reproducción:**
  - Input: cualquier mensaje con `history_len >= 4 ∧ ¬is_first_message` para creator ≠ Iris.
  - Esperado: hint genérico o parametrizado al creador.
  - Actual: hint con "Iris" + apelativos ES/CA → LLM confunde identidad.
  - Distribución medida Fase 2: **P4 dispara en 90% de casos** del eval de Iris → para Stefano el impacto sería catastrófico.
- **Fix propuesto (Fase 5, decisión B + principio vocab_meta §1.1):**
  - **Identidad** (calibrations legítimo):
    - `creator_display_name: str` desde `calibrations/{creator}.json` → sustituir literal `"Iris"` por `agent.creator.display_name`.
  - **Datos lingüísticos** (vocab_meta DB, mined):
    - `vocab_meta(creator_id, vocab_type='apelativos')` → lookup lazy en runtime; poblado por content mining de posts + DMs históricos del creator.
    - `vocab_meta(creator_id, vocab_type='anti_bugs_verbales')` → poblado por análisis adversarial post-first-deploy o durante calibración inicial (detecta calcos como "flower" → ES, "honey" → IT, etc.).
  - **Fallback (vocab_meta vacío / creator desconocido):** hint genérico **sin apelativos, sin anti-bugs, sin name-injection específica**. NO usar defaults de Iris como fallback global.
  - **Runtime en strategy.py:** `_determine_response_strategy` recibe `creator_id: str | None` como 8º parámetro (tras eliminar dead `follower_interests`, ver BUG-011 → 7 params netos + 1 nuevo = 7 params). Lookup a `vocab_meta` es lazy y cacheable por request.
  - **Métrica Prometheus nueva (común a BUG-001/002/005):** `dm_strategy_vocab_source{vocab_type, source=mined|fallback}` → permite observar en runtime si los hints están personalizados o son genéricos.
- **Dependencia externa:** el mining automático de `apelativos` y `anti_bugs_verbales` depende de otro worker (mining pipeline). Alternativa **bootstrap manual** para no bloquear E1: 1-time migration que pobla `vocab_meta` de Iris con los valores actualmente hardcoded (`["nena","tia","flor","cuca","reina"]` y `["flower"]`). Mining automático queda documentado como deuda Q2 2026 en `DECISIONS.md`.
- **Test regression a añadir:** `test_p4_recurrente_uses_vocab_meta_when_available` + `test_p4_recurrente_fallback_generic_when_vocab_empty` + `test_p4_recurrente_no_iris_leak_for_other_creator`.

### BUG-DM-STRAT-002 — CRÍTICA — Openers prohibidos ES/CA hardcoded

- **Archivo:** `backend/core/dm/strategy.py:86`
- **Commit introductor:** `f561819c4`
- **Código ofensor:**
  ```python
  86      "1) NO preguntes '¿Que te llamó la atención?' ni '¿Que t'ha cridat l'atenció?' ni variantes — NUNCA. "
  ```
- **Problema:** solo prohíbe openers en español (`"¿Que te llamó la atención?"`) y catalán (`"Que t'ha cridat l'atenció?"`). Para un creator IT no se prohíbe `"Che ti ha colpito?"`, para EN `"What caught your attention?"`, para PT `"O que te chamou a atenção?"`, etc. Modelos base Gemini/Claude **reproducen estos patrones genéricos en el idioma del creador** si no se prohíben explícitamente.
- **Reproducción:**
  - Creator IT, lead con `history_len≥4`, mensaje cualquiera.
  - Esperado: LLM evita opener de cold-lead en IT.
  - Actual: no hay restricción → modelo puede abrir con "Che ti ha colpito dei miei post?"
- **Fix propuesto (Fase 5, principio vocab_meta §1.1):**
  - **Datos lingüísticos** (vocab_meta DB, mined):
    - `vocab_meta(creator_id, vocab_type='openers_to_avoid')` → poblado por mining de aperturas repetitivas que el modelo calcó incorrectamente en historiales conversacionales previos del creator (o inyectadas manualmente durante calibración inicial).
    - Auto-detección de idioma del corpus del creator para saber contra qué idioma aplicar las reglas — **no hay listas por idioma hardcodeadas**, solo patrones detectados en los DMs reales.
  - **Fallback (vocab_meta vacío):** rama P4 neutra, sin restricciones específicas de opener. El hint RECURRENTE conserva las reglas 2-3 ("no saludes como primera vez", "responde con naturalidad") pero omite la regla 1 si no hay patrones mined.
  - **Métrica:** reutiliza `dm_strategy_vocab_source{vocab_type='openers_to_avoid', source}` del BUG-001.
- **Dependencia externa:** mining pipeline de openers calcados requiere detector adversarial offline que compare output del bot contra respuestas reales del creator. Bootstrap manual para Iris: inyectar `["¿Que te llamó la atención?", "Que t'ha cridat l'atenció?"]` con idioma detectado `["es", "ca"]` en una 1-time migration. Mining automático queda documentado Q2 2026.
- **Test regression:** `test_p4_uses_mined_openers_to_avoid` + `test_p4_fallback_no_opener_restrictions_when_vocab_empty` + `test_p4_no_spanish_openers_for_italian_creator`.

### BUG-DM-STRAT-003 — ALTA — Overlap P6 VENTA vs resolver S6 NO_SELL

- **Archivos:** `backend/core/dm/strategy.py:102` (dispara P6 VENTA) y `backend/core/dm/sell_arbitration/arbitration_layer.py:25` (resolver P3 NO_SELL para `DNA ∈ {FAMILIA, INTIMA, COLABORADOR}`) + `veto_layer.evaluate_vetos` (Layer 1 NO_SELL por frustración/sensitive_action).
- **Commit introductor:** overlap creado cuando aterrizó Fase 3 S6 (`c826e673`, 2026-04-23) sin coordinarse con P6 VENTA preexistente (SHA `7d49b663b`, 2026-03-01).
- **Código ofensor (strategy.py:102-107):**
  ```python
  if intent_value in ("purchase", "pricing", "product_info", "purchase_intent", "product_question"):
      return (
          "ESTRATEGIA: VENTA. El usuario muestra interés en productos/servicios. "
          "Da la información concreta que pide (precio, contenido, duración). "
          "Añade un CTA suave al final."
      )
  ```
- **Casos concretos mapeados (Fase 2):**
  - **Caso A** — Familia pregunta precio: resolver devuelve `NO_SELL`, strategy NO emite anti-venta (P1 muerta) → hueco.
  - **Caso B** — Familia first-message + pricing: resolver `NO_SELL`, strategy emite P6 VENTA con "añade CTA" → **contradicción explícita**.
  - **Caso D** — Lead frustration=3 + pricing: resolver Layer 1 `NO_SELL`, strategy P5 AYUDA o P4 RECURRENTE no contradicen pero tampoco refuerzan → gap.
- **Fix propuesto (Fase 5, decisión C — Opción 1):** gate mínimo en `generation.py` tras computar `strategy_hint` y antes de `prompt_parts.append(strategy_hint)`:
  ```python
  # Skip VENTA hint when resolver forbids selling
  if strategy_hint and "ESTRATEGIA: VENTA" in strategy_hint:
      _sell_directive = cognitive_metadata.get("sell_directive")  # set by P4 LIVE adapter
      if _sell_directive == "NO_SELL":
          strategy_hint = ""
          cognitive_metadata["strategy_hint_gated"] = "no_sell"
  ```
- **Nota:** la signatura de `_determine_response_strategy` se mantiene estable (decisión C explícita). Casos C (overlap benigno SOFT_MENTION) y E (CIERRE sin intent) se documentan como known gaps en `DECISIONS.md`, iteración posterior.
- **Test regression:** `test_strategy_hint_gated_when_directive_no_sell_and_venta`.

### BUG-DM-STRAT-004 — ALTA — Doble hardcoding P1/P2 desactivadas 27 días sin CCEE

- **Archivos:**
  - `backend/core/dm/phases/generation.py:197` `relationship_type=""`
  - `backend/core/dm/phases/generation.py:199` `is_friend=False`
  - `backend/core/dm/phases/context.py:1222` `_rel_type = ""`
- **Commit crítico:** `9752df768` (Manel Bertran, 2026-03-27 20:13:28, "fix: relationship scorer — zero prompt injection, only silent product suppression for PERSONAL (score > 0.8)"). Co-autor: Claude Sonnet 4.6.
- **Problema:** desactiva P1 PERSONAL-FAMILIA y P2 PERSONAL-AMIGO de forma permanente aunque `context.py` sí calcula los valores correctos upstream. Justificación: "elimina conflicto con Context Detection". **Nunca medido en CCEE pre/post.** 27 días de deuda.
- **Reproducción:**
  - Lead con `_rel_score.category == "PERSONAL" ∧ score > 0.8` (FAMILIA/INTIMA real).
  - Esperado: strategy devuelve hint P1 con reglas de estilo (ultra-breve, compartir detalles, directness).
  - Actual: strategy devuelve `""` → LLM no recibe guidance de familia → riesgo de saludos formales u oferta de productos a familia.
- **Fix propuesto (Fase 5, decisión CEO + C):** **NO restaurar el hardcoding del callsite**. Portar las 4 guidelines de estilo (brevedad, concreción, directness, compartir detalles) al **resolver S6 ArbitrationLayer** como bloque `aux_text` cuando `directive == NO_SELL ∧ dna_relationship_type ∈ {FAMILIA, INTIMA, AMISTAD_CERCANA}`. La regla "no vendas" ya está cubierta por `NO_SELL` del resolver.
- **Gap de medición (decisión A):** el dataset baseline actual tiene 0 casos etiquetados `dna_relationship_type ∈ {FAMILIA, INTIMA, AMISTAD_CERCANA}` → cambio **invisible en CCEE E1**. Documentar como **E2 diferido Q2 2026** en `DECISIONS.md`, bloqueante por bucket ampliado con casos FAMILIA/AMIGO etiquetados.
- **Test regression:** `test_p1_p2_remain_inactive_in_strategy_py` (garantía defensive) + `test_resolver_injects_style_block_for_family_no_sell` (en `sell_arbitration/`).

### BUG-DM-STRAT-005 — ALTA — `help_signals` 14 strings ES hardcoded inline

- **Archivo:** `backend/core/dm/strategy.py:57-61`
- **Commit introductor:** `81467a92e` (creación inicial). Modificado por `7d49b663b` en BUG-12 fix pero sin ampliar idiomas.
- **Código ofensor:**
  ```python
  57  help_signals = [
  58      "ayuda", "problema", "no funciona", "no puedo", "error",
  59      "cómo", "como hago", "necesito", "urgente", "no me deja",
  60      "no entiendo", "explícame", "explicame", "qué hago", "que hago",
  61  ]
  ```
- **Problemas:**
  1. Lista ES-only → Stefano (IT: `aiuto, problema, non funziona, non riesco, errore, come, ho bisogno, urgente, non mi lascia, non capisco, spiegami`) queda sin cobertura.
  2. Duplicados manuales accent-stripping (`explícame`/`explicame`, `qué hago`/`que hago`, `cómo`/-) revelan intento ad-hoc → debería normalizar acentos en `msg_lower` con `unicodedata.normalize` + `str.translate`.
  3. Definido **dentro de la función** (L57-61) → se re-crea la lista en cada llamada (coste trivial pero denso).
- **Reproducción:** Stefano envía `"non riesco ad accedere"` → strategy.py no detecta help → P5 AYUDA no dispara → LLM responde con saludo genérico en vez de ayuda directa.
- **Fix propuesto (Fase 5, principio vocab_meta §1.1):**
  - **Datos lingüísticos** (vocab_meta DB, mined):
    - `vocab_meta(creator_id, vocab_type='help_signals')` → poblado por clustering de mensajes lead que precedieron respuestas tipo "ayuda/soporte" en historiales conversacionales del creator (signal: lead message → creator response con patrones de resolución de problema).
  - **Fallback UNIVERSAL multilingual** (cuando vocab_meta vacío):
    - Clasificador semántico ligero basado en **embeddings** contra un set de seed examples de `intent ∈ {complaint, help, technical_support}` (compartido cross-creator, no por idioma).
    - Threshold cosine similarity ≥ τ (τ data-derived del seed set).
    - NO listas por idioma hardcodeadas.
  - **Runtime:** `_determine_response_strategy` delega la detección a helper `_detect_help_signal(message, creator_id)` que:
    1. Si `vocab_meta[creator_id, 'help_signals']` existe → substring match sobre los patrones mined.
    2. Si vacío → embedding similarity contra seed examples universales.
    3. Retorna `bool`.
  - **Métrica:** `dm_strategy_vocab_source{vocab_type='help_signals', source=mined|semantic_fallback}`.
- **Dependencia externa:** clustering de help patterns + seed examples universales requiere worker separado. Bootstrap manual para Iris: inyectar los 14 strings actuales como `vocab_type='help_signals'`. Fallback semántico requiere seed set mínimo (~30-50 ejemplos multilingual) + embeddings infra (ya existe en `services/embeddings_service.py`).
- **Test regression:** `test_help_signals_mined_vocab_detects_italian_via_fallback` + `test_help_signals_semantic_fallback_when_vocab_empty` + `test_help_signals_mined_takes_precedence_over_fallback`.

### BUG-DM-STRAT-006 — ALTA — Sistema sin flag `ENABLE_DM_STRATEGY_HINT`

- **Archivo:** `backend/core/dm/phases/generation.py:194`
- **Análisis:** `grep "ENABLE_" strategy.py` → 0 hits. `feature_flags.py` define 20+ flags para otros componentes (L29-48) pero no para dm_strategy. El sistema está **ON incondicionalmente** desde `cd33367cf` (2026-02-25).
- **Problema:** imposible A/B-testar el hint on/off sin cambio de código + deploy. Imposible apagar selectivamente si se detecta regresión.
- **Reproducción:** no hay forma de desactivar `strategy_hint` en Railway sin modificar código.
- **Fix propuesto (Fase 5):** añadir flag en `feature_flags.py`:
  ```python
  dm_strategy_hint: bool = field(default_factory=lambda: _flag("ENABLE_DM_STRATEGY_HINT", True))
  ```
  Default `True` preserva comportamiento prod actual. Envolver callsite con `if flags().dm_strategy_hint:`. Esto habilita E1 en Fase 6.
- **Test:** `test_strategy_hint_disabled_when_flag_off`.

### BUG-DM-STRAT-007 — MEDIA — Threshold `history_len >= 4` hardcoded

- **Archivo:** `backend/core/dm/strategy.py:82`
- **Commit introductor:** `f561819c4`.
- **Código:**
  ```python
  82  if history_len >= 4 and not is_first_message:
  ```
- **Problema:** `4` es un número mágico sin derivación de baseline. Para creadores con conversaciones más largas (p.ej. support-heavy), el trigger RECURRENTE podría activarse demasiado tarde; para conversaciones cortas tipo flash-sales, demasiado pronto.
- **Fix propuesto (Fase 5):** leer de `calibrations/{creator}.json` → `conversation_profile.recurrent_threshold` con fallback a `4` si falta. Valor ideal data-derived: `p25` de `history_len` cuando lead lleva ≥2 exchanges → marca la mediana de "recurrencia confirmada".
- **Alternativa aceptable:** variable de entorno `DM_STRATEGY_RECURRENT_THRESHOLD=4` (default), si data-derivation complica el PR.
- **Test:** `test_recurrente_threshold_from_creator_config`.

### BUG-DM-STRAT-008 — MEDIA — Char limit "5-30" en P1 texto libre

- **Archivo:** `backend/core/dm/strategy.py:45`
- **Commit introductor:** `5b1a2fbe1` (2026-03-21, "fix: improve personal/family conversation quality").
- **Código:**
  ```python
  45      "4) Ultra-breve: 5-30 chars máximo. "
  ```
- **Problema:** `5-30` son números literales en el prompt del LLM, no derivados del perfil del creador. Para Iris (cuyo `length.char_median` según baseline ~22-26 chars en mensajes familiares) aplica razonablemente; para Stefano (mensajes más largos en IT) no.
- **Fix propuesto (Fase 5, si P1 se reactiva vía portado al resolver):** derivar del `calibrations[creator].length.char_p25` y `char_p75` restringidos a mensajes con `dna_relationship_type ∈ {FAMILIA, INTIMA, AMISTAD_CERCANA}`. Formato del hint: `f"Ultra-breve: ~{char_p25}-{char_p75} chars."`.
- **Nota:** este bug solo aplica si se reactiva P1 o se porta al resolver. En el bloque portado al ArbitrationLayer (Fase 5), usar valores data-derived desde el inicio.

### BUG-DM-STRAT-009 — MEDIA — Duplicación semántica intents VENTA

- **Archivo:** `backend/core/dm/strategy.py:102`
- **Commit:** `7d49b663b` (2026-03-01, BUG-07).
- **Código:**
  ```python
  102  if intent_value in ("purchase", "pricing", "product_info", "purchase_intent", "product_question"):
  ```
- **Problema:** `purchase` y `purchase_intent` coexisten; `product_info` y `product_question` coexisten. Revelan dos eras del IntentClassifier sin unificar nomenclatura.
- **Verificación necesaria (fuera scope):** `grep IntentValue.\|IntentType.\|INTENT_` en `core/intent/` para ver cuál set está vivo y cuál es legacy.
- **Fix propuesto (Fase 5):** si verificación confirma legacy, consolidar a la nomenclatura actual del IntentClassifier. Mantener alias temporal documentado en DECISIONS.md si hay dudas.
- **Nota:** bajo impacto porque ambos sets se aceptan — el overlap solo es deuda de naming.

### BUG-DM-STRAT-010 — MEDIA — Metadata solo graba primer fragmento

- **Archivo:** `backend/core/dm/phases/generation.py:205`
- **Código:**
  ```python
  205  cognitive_metadata["response_strategy"] = strategy_hint.split(".")[0]
  ```
- **Problema:** solo guarda `"ESTRATEGIA: RECURRENTE"` como metadata; las reglas completas (el texto inyectado al LLM) no se persisten. Imposible auditar qué wording específico recibió el LLM sin re-correr con mismo input.
- **Fix propuesto (Fase 5):** preservar hint completo en `cognitive_metadata["strategy_hint_full"]` (campo nuevo) además del token en `response_strategy`. Permite auditoría A/B de wording.
  ```python
  cognitive_metadata["response_strategy"] = strategy_hint.split(".")[0]
  cognitive_metadata["strategy_hint_full"] = strategy_hint  # new
  ```
- **Tamaño:** hint completo ≤ 500 chars → impacto trivial en JSONB storage.

### BUG-DM-STRAT-011 — BAJA — `follower_interests` dead param

- **Archivos:** `backend/core/dm/strategy.py:19` (signature) + `backend/core/dm/phases/generation.py:200` (callsite)
- **Commit introductor:** `81467a92e` (creación inicial).
- **Problema:** parámetro recibido y nunca leído dentro de la función (grep `follower_interests` en `strategy.py` → solo aparece en la signature L19). Desde la creación (2026-02-25) nunca se ha implementado uso.
- **Fix propuesto (Fase 5, decisión C explícita):** eliminar el parámetro de la signatura y del callsite. 8 params netos → **7 params**. Actualizar 3 tests que llaman la función.
- **Tests a actualizar:** `test_dm_agent_v2.py:531,546,...`, `test_motor_audit.py:312,480`, `mega_test_w2.py:127,1115`.

### BUG-DM-STRAT-012 — BAJA — Sin métricas Prometheus

- **Archivos:** `backend/core/dm/strategy.py` global + `generation.py:204-206`
- **Verificación:** `grep "emit_metric\|prometheus\|counter\|metric" strategy.py` → 0 hits.
- **Problema:** sin counter por rama, imposible observar distribución real en prod sin SQL ad-hoc contra `messages.cognitive_metadata`. No integrable con dashboards de latencia / error rate.
- **Fix propuesto (Fase 5):** emitir 2 métricas en `generation.py` tras computar `strategy_hint`:
  ```python
  from core.observability.metrics import emit_metric
  _branch = strategy_hint.split(".")[0].replace("ESTRATEGIA: ", "").strip() or "DEFAULT"
  emit_metric("dm_strategy_branch_total", branch=_branch, creator_id=agent.creator_id)
  if strategy_hint:
      emit_metric("dm_strategy_hint_injected_total", branch=_branch, creator_id=agent.creator_id)
  ```
- **Infra:** `emit_metric` ya existe en `core/observability/metrics.py` (usado por `sell_arbitration/arbitration_layer.py:89,103`).

### BUG-DM-STRAT-013 — BAJA — Log no estructurado

- **Archivo:** `backend/core/dm/phases/generation.py:206`
- **Código:**
  ```python
  206  logger.info(f"[STRATEGY] {strategy_hint.split('.')[0]}")
  ```
- **Problema:** f-string sin `extra={}` → no parseable por Datadog/OpenTelemetry. No tiene `creator_id`, `lead_id`, ni la rama como campos separados.
- **Fix propuesto (Fase 5):** migrar a log estructurado:
  ```python
  logger.info(
      "[STRATEGY] branch=%s",
      _branch,
      extra={"branch": _branch, "creator_id": agent.creator_id, "sender_id": sender_id},
  )
  ```

### BUG-DM-STRAT-014 — BAJA — Re-export backward-compat + tests distribuidos

- **Archivos:** `backend/core/dm_agent_v2.py:28` (re-export con `noqa: F401`), `backend/tests/test_dm_agent_v2.py:521+`, `backend/tests/test_motor_audit.py:312,480`, `backend/tests/test_e2e_pipeline.py:9`.
- **Código ofensor:**
  ```python
  # dm_agent_v2.py:28
  from core.dm.strategy import _determine_response_strategy  # noqa: F401
  ```
- **Problema:** el módulo viejo `dm_agent_v2` mantiene un re-export solo para compatibilidad con tests antiguos que aún lo importan desde allí (`test_dm_agent_v2.py:529: from core.dm_agent_v2 import _determine_response_strategy`). Deuda acumulada desde el refactor `81467a92e` (2026-02-25).
- **Fix propuesto (Fase 5):** migrar imports en los 3 tests a `from core.dm.strategy import _determine_response_strategy`; eliminar la línea de re-export.
- **Tamaño del cambio:** ~8 líneas modificadas, cero riesgo funcional.

---

## 4. Priorización para Fase 5 (scope del PR forensic)

### 4.1 Bloqueantes para PR (debe ir en Fase 5)

1. **BUG-001** (CRÍTICA) — `vocab_meta(apelativos, anti_bugs_verbales)` mined + `creator_display_name` desde calibrations + fallback genérico sin Iris-defaults.
2. **BUG-002** (CRÍTICA) — `vocab_meta(openers_to_avoid)` mined + fallback neutro.
3. **BUG-003** (ALTA) — gate en generation.py para P6 VENTA cuando directive==NO_SELL.
4. **BUG-005** (ALTA) — `vocab_meta(help_signals)` mined + fallback semántico universal por embeddings.
5. **BUG-006** (ALTA) — flag `ENABLE_DM_STRATEGY_HINT` default True.
6. **BUG-011** (BAJA pero decisión CEO explícita) — eliminar dead param `follower_interests`, añadir `creator_id` (neto 7 params).
7. **BUG-012** (BAJA, esencial para medir E1) — métricas Prometheus **3 counters**: `dm_strategy_branch_total`, `dm_strategy_hint_injected_total`, `dm_strategy_vocab_source{vocab_type, source=mined|fallback}`.
8. **Bootstrap 1-time migration** (ver §6.1) — seed `vocab_meta` de Iris con valores actualmente hardcoded. Sin esto, E1 arm B correría con vocab vacío → fallback genérico → regresión garantizada en Iris. **No es un bug per se pero es bloqueante del scope**.

### 4.2 Recomendados pero no bloqueantes

- **BUG-007** (MEDIA) — threshold `history_len` data-derived o env var.
- **BUG-010** (MEDIA) — metadata full hint (1 línea, útil para auditoría post-E1).
- **BUG-013** (BAJA) — log estructurado (1 edit).
- **BUG-014** (BAJA) — limpieza de re-export y tests (low-risk).

### 4.3 Documentados como deuda en DECISIONS.md (Q2 2026)

- **BUG-004** (ALTA) — portado al resolver S6 requiere bucket ampliado con casos FAMILIA/AMIGO → **E2 diferido Q2 2026**.
- **BUG-008** (MEDIA) — char limit "5-30" solo aplica cuando P1 se reactiva vía resolver (parte de E2).
- **BUG-009** (MEDIA) — consolidación naming intents, fuera de scope inmediato.
- Overlap Caso C y Caso E (SOFT_MENTION + CIERRE sin intent) — known gaps post-E1.

---

## 5. Tabla final de bugs (STOP)

| ID | Severidad | En PR Fase 5? | Archivo:Línea | Fix 1-línea |
|----|-----------|---------------|---------------|-------------|
| 001 | CRÍTICA | ✅ | strategy.py:89-90 | `vocab_meta(apelativos, anti_bugs_verbales)` mined + `creator_display_name` desde calibrations + fallback genérico sin Iris-defaults |
| 002 | CRÍTICA | ✅ | strategy.py:86 | `vocab_meta(openers_to_avoid)` mined con auto-detect idioma + fallback neutro (sin regla 1) |
| 003 | ALTA | ✅ | generation.py:194 + arbitration_layer.py:25 | Gate en generation.py: skip P6 VENTA si directive==NO_SELL |
| 004 | ALTA | 📋 | generation.py:197,199 | Mantener desactivado; portar estilo al resolver (E2 Q2 2026) |
| 005 | ALTA | ✅ | strategy.py:57-61 | `vocab_meta(help_signals)` mined + fallback semántico multilingual por embeddings (no listas por idioma) |
| 006 | ALTA | ✅ | generation.py:194 | Añadir flag ENABLE_DM_STRATEGY_HINT default True |
| 007 | MEDIA | ⚠️ (si cabe) | strategy.py:82 | Threshold data-derived o env var `DM_STRATEGY_RECURRENT_THRESHOLD` |
| 008 | MEDIA | 📋 | strategy.py:45 | Data-derived char_p25/p75 solo cuando P1 se reactiva en resolver |
| 009 | MEDIA | 📋 | strategy.py:102 | Consolidación naming intents fuera de scope |
| 010 | MEDIA | ⚠️ (si cabe) | generation.py:205 | Añadir `cognitive_metadata["strategy_hint_full"]` |
| 011 | BAJA | ✅ | strategy.py:19 + gen.py:200 | Eliminar follower_interests (8→7 params; luego se añade creator_id → 7 netos) |
| 012 | BAJA | ✅ | strategy.py global | 3 counters Prometheus: dm_strategy_branch_total, hint_injected_total, vocab_source |
| 013 | BAJA | ⚠️ (si cabe) | generation.py:206 | Log estructurado con extra={} |
| 014 | BAJA | ⚠️ (si cabe) | dm_agent_v2.py:28 + tests | Migrar imports + eliminar re-export |

**Leyenda:** ✅ obligatorio · ⚠️ recomendado · 📋 deuda documentada.

---

## 6. Dependencias externas y bootstrap

Los fixes de BUG-001, BUG-002 y BUG-005 consumen el sistema `vocab_meta` DB siguiendo el principio arquitectural §1.1. Aunque el **mining automático** de cada `vocab_type` depende de otro worker (pipeline separado), este PR **no requiere esperar al mining** para ser mergeable.

### 6.1 Bootstrap 1-time migration (parte del PR Fase 5)

Para no bloquear E1 (medición hot path A/B del flag `ENABLE_DM_STRATEGY_HINT`), el PR incluye una **migración manual** que pobla `vocab_meta` de Iris con los valores actualmente hardcoded:

```sql
-- backend/alembic/versions/XXXX_seed_iris_vocab_meta_from_strategy.py
INSERT INTO vocab_meta (creator_id, vocab_type, value, meta) VALUES
  ('<iris_uuid>', 'apelativos',           'nena',                       '{"source":"bootstrap_from_strategy_py_L90"}'),
  ('<iris_uuid>', 'apelativos',           'tia',                        '{"source":"bootstrap_from_strategy_py_L90"}'),
  ('<iris_uuid>', 'apelativos',           'flor',                       '{"source":"bootstrap_from_strategy_py_L90"}'),
  ('<iris_uuid>', 'apelativos',           'cuca',                       '{"source":"bootstrap_from_strategy_py_L90"}'),
  ('<iris_uuid>', 'apelativos',           'reina',                      '{"source":"bootstrap_from_strategy_py_L90"}'),
  ('<iris_uuid>', 'anti_bugs_verbales',   'flower',                     '{"source":"bootstrap_from_strategy_py_L90"}'),
  ('<iris_uuid>', 'openers_to_avoid',     '¿Que te llamó la atención?', '{"lang":"es","source":"bootstrap_from_strategy_py_L86"}'),
  ('<iris_uuid>', 'openers_to_avoid',     "Que t'ha cridat l'atenció?", '{"lang":"ca","source":"bootstrap_from_strategy_py_L86"}'),
  ('<iris_uuid>', 'help_signals',         'ayuda',                      '{"source":"bootstrap_from_strategy_py_L57"}'),
  ...  -- 14 help_signals totales
;
```

Esto garantiza que E1 con Iris preserve el comportamiento actual (arm A) y permita medir el hint limpio (arm B) sin regresión por vocab vacío.

### 6.2 Mining automático diferido (documentar en DECISIONS.md, Q2 2026)

Worker separado a construir (fuera scope este PR):
- Mining de apelativos: extract top-N tokens posesivos/cariñosos del creator corpus (DMs + posts), filtrado por frecuencia + contexto emocional.
- Mining de `anti_bugs_verbales`: detector adversarial offline que compara output del bot contra respuestas reales y flagea palabras del bot no-presentes en el corpus real.
- Mining de `openers_to_avoid`: clustering de aperturas bot rechazadas manualmente por el creator / copilot.
- Mining de `help_signals`: clustering de mensajes lead previos a respuestas del creator con patrones de resolución.
- Métricas de cobertura: `dm_strategy_vocab_source{source=mined}` vs `source=fallback` → cuando `fallback > 20%` para un creator, alertar para re-mine.

### 6.3 Schema `vocab_meta` (referencia, ya existente desde marzo 2026)

Consistente con sistemas ya data-derived (vocab_meta DB, negation reducer, pool auto-extraction, code-switching universal, intent-stratified few-shot, Bot Question Analyzer vocab afirmaciones). Campos relevantes asumidos:
```
vocab_meta(
  id             uuid PK,
  creator_id     uuid FK → creators.id,
  vocab_type     text,  -- 'apelativos', 'anti_bugs_verbales', 'openers_to_avoid', 'help_signals', ...
  value          text,
  meta           jsonb, -- {lang, frequency, source, confidence, ...}
  created_at     timestamptz,
  updated_at     timestamptz
)
CREATE INDEX ix_vocab_meta_creator_type ON vocab_meta (creator_id, vocab_type);
```

Si el schema difiere del arriba asumido, la Fase 5 lo ajusta al real durante implementación (Read antes de escribir).

---

**STOP Fase 3.** Total 7 bugs bloqueantes ✅, 4 recomendados ⚠️, 3 deuda documentada 📋.

**Cambios post-corrección CEO:**
- BUG-001, 002, 005 migran de `calibrations JSON por idioma` (incorrecto) a **vocab_meta DB mined** (correcto) con fallbacks universales sin defaults Iris.
- Añadida sección §1.1 con principio arquitectural y separación datos lingüísticos vs identidad.
- Añadida sección §6 con bootstrap 1-time migration (parte del PR) + dependencia mining Q2 2026.
- Añadida métrica común `dm_strategy_vocab_source{vocab_type, source=mined|fallback}`.
- `_determine_response_strategy` signatura final: **7 params** (elimina `follower_interests`, añade `creator_id`).

¿Procedo con Fase 4 (papers + repos state-of-the-art)?
