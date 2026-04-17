# W6 — Forense CC Compaction Deep Dive

**Worker:** 6
**Model:** Opus 4.6
**Fecha:** 2026-04-16
**Scope:** 3 estrategias de compaction en Claude Code (CC) + adaptación a Clonnect

---

## TL;DR

CC implementa **4 estrategias de reducción de contexto** (no 3 — aparece una cuarta oculta, `trySessionMemoryCompaction`) estructuradas en una **pipeline jerárquica** que ataca el problema a 3 niveles de granularidad:

| Nivel | Estrategia | Granularidad | Disparador | Coste |
|-------|-----------|--------------|------------|-------|
| L1 | **microCompact** (+ time-based + cached-MC) | tool_results individuales | Pre-cada-turn + gap-temporal | ~0 tokens (cache-edit API o content-clear) |
| L2 | **Session Memory Compact** | conversación → MD + tail preservado | Pre-autocompact, si `tengu_sm_compact` ON | ~0 LLM calls (SM extraído en background) |
| L3 | **autoCompact** | conversación completa → resumen 9 secciones | `tokens >= ctx - 13K` | 1 LLM call forked, p99=17.3K tokens output |
| L4 | **reactiveCompact** | recuperación post-API-error | API devuelve `prompt_too_long` (413) o `media_size_error` | 1 LLM call forked post-error |

Clonnect tiene **0 estrategias de compaction**. Su contexto pressure (style=41% del budget en Sprint 4) viene de no tener ninguna capa que lo reduzca dinámicamente.

---

## PASO 1 — microCompact (archivo: `src/services/compact/microCompact.ts`, 531 líneas)

### 1.1 Propósito

microCompact es la **capa L1 pre-request**: se ejecuta ANTES de cada llamada API para limpiar tool results viejos sin invalidar el prompt cache (si es posible).

### 1.2 Las 3 variantes internas

microCompact es **una fachada** (`microcompactMessages`, línea 253) que despacha a 3 paths distintos según gates de feature flags y condiciones de sesión:

```
microcompactMessages(messages, toolUseContext, querySource)
    │
    ├─ maybeTimeBasedMicrocompact(msgs, querySource)       ← línea 267
    │   └─ Cold-cache fast path (mutates content)
    │
    ├─ if feature('CACHED_MICROCOMPACT'):
    │       cachedMicrocompactPath(msgs, querySource)       ← línea 276
    │       └─ Warm-cache path (cache-edit API, no content mutation)
    │
    └─ fallback: return { messages } unchanged               ← línea 292
```

### 1.3 ¿Cuándo se activa?

**Every turn**, pre-API-call. Pero solo HACE algo si:

- **Time-based path** (`microCompact.ts:422-444`, `evaluateTimeBasedTrigger`):
  - `config.enabled` = true (flag `tengu_slate_heron`)
  - `querySource` viene del main thread (no subagentes)
  - Gap desde último mensaje assistant > `gapThresholdMinutes` (default **60 min**, ver `timeBasedMCConfig.ts:32`)
  - Razón del 60 min: TTL de prompt cache del servidor es 1h → garantizado expirado → "full prefix will be rewritten anyway" (`timeBasedMCConfig.ts:23`)

- **Cached microcompact path** (solo main thread, línea 276-286):
  - Flag `CACHED_MICROCOMPACT` activo
  - Modelo soporta cache editing
  - querySource es main thread (no session_memory, no prompt_suggestion)
  - Triggers por **count** (número de tool_results registered vs keepRecent threshold de GrowthBook)

### 1.4 ¿Qué compacta exactamente?

**SOLO tool_results** de un conjunto blanco llamado `COMPACTABLE_TOOLS` (`microCompact.ts:41-50`):

```typescript
const COMPACTABLE_TOOLS = new Set<string>([
  FILE_READ_TOOL_NAME,      // Read
  ...SHELL_TOOL_NAMES,       // Bash, etc.
  GREP_TOOL_NAME,            // Grep
  GLOB_TOOL_NAME,            // Glob
  WEB_SEARCH_TOOL_NAME,      // WebSearch
  WEB_FETCH_TOOL_NAME,       // WebFetch
  FILE_EDIT_TOOL_NAME,       // Edit
  FILE_WRITE_TOOL_NAME,      // Write
])
```

**NO compacta:** user messages, assistant text, attachments, thinking blocks, system prompt, tool_use blocks (solo sus _results_ pareados).

### 1.5 ¿Cómo decide qué mantener vs comprimir?

**Heurística recency-only** (`microCompact.ts:456-463`):

```typescript
const keepRecent = Math.max(1, config.keepRecent)       // floor 1
const keepSet = new Set(compactableIds.slice(-keepRecent))  // últimos N
const clearSet = new Set(compactableIds.filter(id => !keepSet.has(id)))  // resto
```

- `keepRecent` default = 5 (time-based) o configurable vía GrowthBook `tengu_cached_microcompact_config`
- Floor de 1 es intencional: slice(-0) devuelve el array entero (bug trap documentado línea 458-460)
- **No hay ranking semántico**: siempre "los N más recientes"

### 1.6 ¿Qué hace con el prompt cache? (deferred boundary emission)

Hay **dos paths con tratamientos opuestos del cache**:

#### Time-based (cold-cache) — MUTATES content
```typescript
// microCompact.ts:475-492
const newContent = message.message.content.map(block => {
  if (block.type === 'tool_result' && clearSet.has(block.tool_use_id)) {
    return { ...block, content: TIME_BASED_MC_CLEARED_MESSAGE }  // '[Old tool result content cleared]'
  }
  return block
})
```
- Reemplaza el contenido del tool_result con un marker string → reduce tokens directamente en el prompt
- El cache ya está expirado (>60 min), así que mutar no pierde nada
- Llama `resetMicrocompactState()` (línea 517) + `notifyCacheDeletion()` (línea 526)

#### Cached MC (warm-cache) — NO mutates content
```typescript
// microCompact.ts:369-394
// "Return messages unchanged - cache_reference and cache_edits are added at API layer
// Boundary message is deferred until after API response so we can use
// actual cache_deleted_input_tokens from the API instead of client-side estimates"
pendingCacheEdits = cacheEdits  // queue for API layer
return { messages, compactionInfo: { pendingCacheEdits: {...} } }
```
- Usa la **cache-edit API de Anthropic** (prompts.ts → `cache_reference` + `cache_edits` blocks a nivel API)
- El prompt local NO cambia → el cache sigue hit
- **Deferred boundary emission**: el "boundary message" (UI-visible) no se emite hasta DESPUÉS de la respuesta API, para usar el conteo real de `cache_deleted_input_tokens` en vez de estimaciones cliente-side

### 1.7 Per-turn, cada N turns, u oportunista

**Per-turn** — se evalúa en cada turno del main loop, pero solo actúa cuando cumple umbrales:
- Time-based: gap > 60 min → dispara
- Cached MC: cuenta de tools registered > trigger threshold → dispara
- Sin trigger: return unchanged (no-op)

### 1.8 Entrada / salida

```typescript
Input: (messages: Message[], toolUseContext?: ToolUseContext, querySource?: QuerySource)
Output: { messages: Message[], compactionInfo?: { pendingCacheEdits?: {...} } }
```

- `messages` puede ser el mismo array (no-op) o contener tool_results con content reemplazado
- `compactionInfo.pendingCacheEdits` señala al API layer que debe insertar cache_edits blocks

---

## PASO 2 — autoCompact (archivo: `src/services/compact/autoCompact.ts`, 352 líneas)

### 2.1 Propósito

autoCompact es la **capa L3**: genera un resumen narrativo de TODA la conversación cuando el token count se acerca al context window. Corresponde al banner "Context left until auto-compact: N%" que el usuario ve.

### 2.2 Thresholds

```typescript
// autoCompact.ts:62-70
export const AUTOCOMPACT_BUFFER_TOKENS    = 13_000    // trigger
export const WARNING_THRESHOLD_BUFFER_TOKENS = 20_000 // warning UI
export const ERROR_THRESHOLD_BUFFER_TOKENS   = 20_000 // error UI
export const MANUAL_COMPACT_BUFFER_TOKENS    = 3_000  // manual /compact
const MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES   = 3      // circuit breaker
const MAX_OUTPUT_TOKENS_FOR_SUMMARY          = 20_000 // reserved output
```

**Cálculo del threshold** (`autoCompact.ts:72-91`):
```
effectiveWindow = contextWindow(model) - 20_000 (reserved output)
autoCompactThreshold = effectiveWindow - 13_000
```

Para Sonnet 4.5/200K: `autoCompactThreshold ≈ 200_000 - 20_000 - 13_000 = 167_000`.

### 2.3 Circuit breaker

```typescript
// autoCompact.ts:260-265
if (tracking?.consecutiveFailures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES) {
  return { wasCompacted: false }
}
```

Razón documentada (`autoCompact.ts:68-69`):
> "BQ 2026-03-10: 1,279 sessions had 50+ consecutive failures (up to 3,272) in a single session, wasting ~250K API calls/day globally."

### 2.4 ¿Genera 9-section summary? SÍ

`src/services/compact/prompt.ts:66-77` define las **9 secciones** literales. Tres variantes (`BASE`, `PARTIAL`, `PARTIAL_UP_TO`) comparten la estructura:

1. **Primary Request and Intent** — todos los requests explícitos del usuario
2. **Key Technical Concepts** — conceptos/frameworks discutidos
3. **Files and Code Sections** — archivos examinados/modificados + snippets
4. **Errors and fixes** — errores + cómo se arreglaron + feedback del usuario
5. **Problem Solving** — problemas resueltos y troubleshooting en curso
6. **All user messages** — TODOS los user messages no-tool-results (crítico para feedback)
7. **Pending Tasks** — tareas pendientes explícitas
8. **Current Work** — qué se estaba trabajando _justo antes_ del summary
9. **Optional Next Step** — próximo paso con **quotes verbatim del último turno** (anti-drift)

### 2.5 ¿Qué es el `<analysis>` scratchpad?

Un **drafting scratchpad** (`prompt.ts:31-44`):
```
Before providing your final summary, wrap your analysis in <analysis> tags
to organize your thoughts and ensure you've covered all necessary points.
```

El LLM genera `<analysis>...</analysis><summary>...</summary>` en dos bloques. Luego `formatCompactSummary()` (`prompt.ts:311-335`) **tira el analysis**:
```typescript
formattedSummary = formattedSummary.replace(/<analysis>[\s\S]*?<\/analysis>/, '')
```

Razón: "it's a drafting scratchpad that improves summary quality but has no informational value once the summary is written" (`prompt.ts:314-315`).

**Técnica prompting clave**: "think-first, then answer" formalizado con XML tags que se strippean antes de re-inyectar. Equivale a chain-of-thought pero estructurado y eliminado.

### 2.6 Flujo de autocompact

```
autoCompactIfNeeded(messages, ctx, ...)
    ├─ Circuit breaker check                       (línea 260)
    ├─ shouldAutoCompact?                          (línea 268)
    │   ├─ Gates: DISABLE_COMPACT, recursion-guards
    │   ├─ Contexto-collapse override              (línea 215)
    │   ├─ Reactive-only mode override             (línea 195)
    │   └─ tokenCountWithEstimation >= threshold
    │
    ├─ trySessionMemoryCompaction() FIRST          (línea 288) ← L2 preempts L3
    │   └─ Si SM disponible → retorna sin llamada LLM
    │
    └─ compactConversation() (en compact.ts)       (línea 313)
        ├─ runForkedAgent con getCompactPrompt()
        ├─ Extrae <summary>
        ├─ formatCompactSummary() tira <analysis>
        ├─ createPostCompactFileAttachments()      (compact.ts:1415)
        ├─ createSkillAttachmentIfNeeded()         (compact.ts:558)
        ├─ processSessionStartHooks('compact')     (compact.ts:592)
        ├─ Emite compact boundary marker
        └─ buildPostCompactMessages(result)        (compact.ts:330)

        Resultado = [
            boundaryMarker,
            summaryMessages,          ← el <summary> formateado
            ...messagesToKeep,        ← tail preservado (reactive/SM) o []
            ...attachments,           ← top-5 files re-inyectados
            ...hookResults,
        ]
```

### 2.7 Reactive-only mode (autoCompact.ts:195-199)

Flag experimental `REACTIVE_COMPACT` + GrowthBook `tengu_cobalt_raccoon`:
> "suppress proactive autocompact, let reactive compact catch the API's prompt-too-long"

Apuesta: ahorrar 1 LLM call de compact en el 95% de sesiones que nunca llegarían a 413, a cambio de una latency spike en el 5% que sí.

---

## PASO 3 — reactiveCompact

### 3.1 Archivo NO existe en el build público

```bash
$ find ~/instructkr-claude-code/src -name "reactiveCompact*"
(vacío)
```

El import es **condicional y runtime-only** (`query.ts:15-17`):
```typescript
const reactiveCompact = feature('REACTIVE_COMPACT')
  ? (require('./services/compact/reactiveCompact.js') as typeof import('./services/compact/reactiveCompact.js'))
  : null
```

`REACTIVE_COMPACT` es un feature flag **ant-only** (Anthropic interno). El archivo existe en el build interno pero está stripped del open-source dump. Lo reconstruyo desde su surface API en `query.ts`:

### 3.2 API inferida

```typescript
// reactiveCompact module exports (inferido de query.ts:15-17, 811, 1084, 1120):
interface ReactiveCompactModule {
  isReactiveCompactEnabled(): boolean
  isWithheldPromptTooLong(msg: Message): boolean
  isWithheldMediaSizeError(msg: Message): boolean
  tryReactiveCompact(params: {
    hasAttempted: boolean
    querySource: QuerySource
    aborted: boolean
    messages: Message[]
    cacheSafeParams: CacheSafeParams
  }): Promise<CompactionResult | null>
}
```

### 3.3 Cuándo se activa

**Recovery path post-API-error**. Flujo (`query.ts:1062-1175`):

1. Main loop envía request → API devuelve error `prompt_too_long` (413) o `media_size_error`
2. El stream loop **withholds** el error (no se propaga al usuario todavía, líneas 788-817)
3. Post-stream, antes de surface:
   - Si es 413 y `CONTEXT_COLLAPSE` está activo: intenta drain primero (`query.ts:1086-1117`) — es más barato
   - Si drain vacío / media error / collapse off: dispara `tryReactiveCompact()` (línea 1120)
4. Si compactó: reintenta la request con postCompactMessages (línea 1148-1165)
5. Si no: surface error + early return (línea 1173-1175) — NO fall through a stop hooks (evita death spiral)

### 3.4 Diferencias con auto/micro

| Dimensión | microCompact | autoCompact | reactiveCompact |
|-----------|--------------|-------------|-----------------|
| **When** | pre-request, proactivo | pre-request, proactivo | post-error, reactivo |
| **Scope** | tool_results individuales | conversación completa | conversación completa |
| **Trigger** | gap-time o count | token threshold | API 413 / media error |
| **LLM call** | 0 | 1 forked | 1 forked (post-failure) |
| **Media stripping** | no | no | **sí** (media_size_error path) |
| **Single-shot** | no (per-turn) | no | **sí** (`hasAttemptedReactiveCompact` guard) |

### 3.5 Single-shot guarantee

```typescript
// query.ts:1121, 1157
hasAttempted: hasAttemptedReactiveCompact,
// ...
hasAttemptedReactiveCompact: true,  // state mark para siguiente iteración
```

Solo 1 intento de reactive compact por sesión de prompt-too-long. Si el retry post-compact vuelve a 413, surface el error en vez de loop infinito.

### 3.6 Circuit breaker MAX_CONSECUTIVE_FAILURES=3

Ese número pertenece a **autoCompact**, no a reactiveCompact (`autoCompact.ts:70`):
```typescript
const MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3
```

reactiveCompact tiene su propio mecanismo más simple: el flag `hasAttemptedReactiveCompact` a nivel state machine (query.ts:1157) — single-shot por overflow event.

### 3.7 Death spiral guard

```typescript
// query.ts:1168-1175
// No recovery — surface the withheld error and exit. Do NOT fall
// through to stop hooks: the model never produced a valid response,
// so hooks have nothing meaningful to evaluate. Running stop hooks
// on prompt-too-long creates a death spiral: error → hook blocking
// → retry → error → … (the hook injects more tokens each cycle).
```

Insight transferible: **nunca ejecutar post-failure hooks en modo recovery** — cada hook puede inyectar tokens y empeorar el context pressure que causó el fail.

---

## PASO 4 — Session memory que sobrevive compaction

### 4.1 La claim del DEEP_DIVE_CC

> "post-compact session memory survives and memories re-inject"

### 4.2 Cómo funciona

Dos mecanismos complementarios:

#### A) Session Memory como FUENTE (no víctima) de compaction

`trySessionMemoryCompaction` (`sessionMemoryCompact.ts:514-630`) es una estrategia L2 que **reemplaza** la llamada LLM de autoCompact cuando:

1. El feature `tengu_sm_compact` está ON (`sessionMemoryCompact.ts:403-432`)
2. Existe un archivo session memory no-vacío (`getSessionMemoryContent()`)
3. SM contiene contenido real (no solo template)

En ese caso, el _summary_ que se inyecta post-compact **NO lo genera un forked LLM call** — lo genera el SM ya extraído en background:

```typescript
// sessionMemoryCompact.ts:464-469
let summaryContent = getCompactUserSummaryMessage(
    truncatedContent,   // ← session memory MD file, no LLM output
    true,
    transcriptPath,
    true,
)
```

Resultado: 0 LLM calls en el compact path. El SM ya existía porque se extrae periódicamente en background (`sessionMemory.ts:1-150`).

#### B) Re-inyección post-compact

`buildPostCompactMessages` (`compact.ts:330-338`):
```typescript
return [
    result.boundaryMarker,
    ...result.summaryMessages,       ← SM o LLM summary
    ...(result.messagesToKeep ?? []),← tail preservado (reactive/SM path)
    ...result.attachments,           ← top-5 files + plan + skills + MCP instructions
    ...result.hookResults,           ← SessionStart hooks
]
```

Y en `compactConversation` (`compact.ts:531-585`):
```typescript
const [fileAttachments, asyncAgentAttachments] = await Promise.all([
  createPostCompactFileAttachments(preCompactReadFileState, context, POST_COMPACT_MAX_FILES_TO_RESTORE),  // top-5 archivos leídos antes
  createAsyncAgentAttachmentsIfNeeded(context),
])
// ... + plan attachment, plan mode, skills, tools delta, agent listing, MCP instructions
```

**Qué sobrevive compaction**:
- `boundaryMarker` con `compactMetadata` (discoveredTools, preservedSegment)
- `summaryMessages` (el 9-section output, `<analysis>` stripped)
- `messagesToKeep` (solo en reactive/SM paths: el tail literal preservado — mínimo 10K tokens / 5 text-block messages, máximo 40K tokens, ver `sessionMemoryCompact.ts:57-61`)
- `attachments`: top-5 files leídos (`POST_COMPACT_MAX_FILES_TO_RESTORE = 5`), plan activo, skills invocados, plan mode instructions, tools/agent/MCP deltas re-announced
- `hookResults`: output de `processSessionStartHooks('compact', ...)` — tus CLAUDE.md se re-inyectan

**Qué NO sobrevive**:
- Tool results crudos (reemplazados por su menciónen summary)
- Thinking blocks antiguos
- Tool_use blocks antiguos (salvo los del tail preservado)
- Attachments delta ya consumidos (se re-inyectan vía `createPostCompactFileAttachments`)

#### C) postCompactCleanup re-injection triggers

`postCompactCleanup.ts:31-77`:
```typescript
resetMicrocompactState()              // cache state reset (nueva oportunidad de edit)
resetContextCollapse()                // si aplica
getUserContext.cache.clear?.()        // próximo turn re-lee CLAUDE.md
resetGetMemoryFilesCache('compact')   // rearma el hook InstructionsLoaded
clearSystemPromptSections()
clearClassifierApprovals()
clearSpeculativeChecks()
clearBetaTracingState()
clearSessionMessagesCache()
// intentionally NOT: resetSentSkillNames (skill_listing ~4K tokens de cache_creation)
```

**Insight transferible**: cada cache que se clear-ea es una **señal de re-inyección** en el próximo turn. La decisión de qué NO clear (skill_listing) se toma por cost-benefit: cuánto cuesta re-inyectar vs cuánto valor aporta.

### 4.3 El ciclo completo

```
Background:
  sessionMemory.ts extrae periódicamente → MD file en disco
  Triggers: initialization threshold (tokens) + update threshold (tokens delta + tool calls)

Main loop hit autocompact threshold:
  1. autoCompactIfNeeded()
  2. trySessionMemoryCompaction() ← SM disponible? usa su content como summary
  3. compactConversation() ← fallback si SM no sirve
  4. Ambos emiten CompactionResult con:
     - summaryMessages (= SM content o LLM output)
     - messagesToKeep (= tail preservado en SM/reactive paths)
     - attachments (top-5 files, plan, skills, deltas)
     - hookResults (CLAUDE.md re-cargado vía SessionStart hook)
  5. postCompactCleanup() → next turn re-lee caches limpiados
  6. Next turn: prompt contiene summary + tail + attachments + hooks → "memory survived"
```

---

## PASO 5 — Adaptación a Clonnect

### 5.1 Diferencias fundamentales de arquitectura

| Dimensión | Claude Code | Clonnect |
|-----------|------------|----------|
| Pattern | Agente multi-turn | DM single-shot |
| Session duration | Minutos-horas | ~2s por reply |
| Conversation memory | Cliente acumula | Stateless (recall en cada turn) |
| Context pressure source | Tool results acumulados | Prompt composition (style + facts + memoria + RAG) |
| Context window budget | 200K (Sonnet 4.5) | ~8-26K (depende modelo) |
| Tool results | Sí, abundantes | **0** (no hay tools en producción) |

**Consecuencia clave**: microCompact, que limpia tool_results, **no aplica directamente a Clonnect**. El context pressure viene de otro sitio.

### 5.2 Análisis de aplicabilidad

#### microCompact → ❌ NO aplica directamente
- Clonnect no genera tool_results → nada que compactar
- El style (41% del budget Sprint 4) se carga en cada request estáticamente, no se "acumula"
- **PERO**: la idea de **pre-compaction por recency-windowing** es transferible al pipeline de facts/memoria/RAG (ver 5.3.A)

#### autoCompact → ❌ NO aplica tal cual, ✅ SÍ el mecanismo
- Clonnect no tiene una "conversación" continua en contexto del lado server — cada DM es un prompt nuevo construido desde cero
- NO hay un "13K buffer vs ctx window" porque el context nunca crece con la conversación
- **PERO**: la técnica `<analysis>` + `<summary>` + strip es directamente aplicable a un componente nuevo (ver 5.3.C)

#### reactiveCompact → ⚠️ PARCIAL, ya existe algo
- Clonnect ya tiene `truncation_recovery` (Sprint 1) — equivalente a reactiveCompact (mismo patrón: post-error recovery)
- Gap: no hay "media stripping" ni "drain-first" (Clonnect no tiene context collapse)
- El death spiral guard (no-run-hooks-on-failure) **debería auditarse**

### 5.3 Propuestas específicas para Clonnect

#### A) **PromptSliceCompactor** — análogo microCompact adaptado

**Disparador**: pre-request, siempre. Actúa solo si `prompt_estimated_tokens > budget * 0.8`.

**Qué compacta**:
- **facts[]**: mantiene top-N por importance score (MMR ya usado en recall). Drop resto.
- **memoria (memo)**: si `len(memo) > THRESHOLD`, toma solo los últimos N párrafos (recency).
- **RAG chunks**: ya existe truncation, pero el scoring podría ser recency-weighted como keepRecent de CC.

**NO toca**:
- Style guide (es estático-per-request, no compactable por selección — ver componente C)
- Último turn del usuario (siempre literal)

**Implementación sugerida**:
```python
# core/dm/phases/context.py (extend)
class PromptSliceCompactor:
    def __init__(self, budget_tokens: int, ratios: dict):
        self.budget = budget_tokens
        self.ratios = ratios  # {"style": 0.35, "facts": 0.15, "memo": 0.20, "rag": 0.20, "history": 0.10}

    def compact(self, components: dict) -> dict:
        estimated = sum(rough_tokens(c) for c in components.values())
        if estimated <= self.budget:
            return components
        # Per-component cap by ratio
        compacted = {}
        for name, content in components.items():
            cap = int(self.budget * self.ratios.get(name, 0.10))
            if rough_tokens(content) > cap:
                compacted[name] = self._truncate_to(content, cap, strategy=name)
            else:
                compacted[name] = content
        return compacted
```

**Por qué funciona**: es el equivalente a `COMPACTABLE_TOOLS` set — whitelist de qué se puede truncar, preserve el resto literal.

#### B) **StyleDistillCache** — análogo cached-MC para style guide

**Problema**: style = 41% del budget y NO cambia entre messages del mismo creator.

**Solución**: versión de cache-edit API NO es posible (OpenRouter/Gemini no exponen cache editing). Pero se puede **hashear y precomputar**:

1. Hash del style guide (sha256) por creator
2. Precomputar una **versión comprimida** (distillation) offline, cacheada en DB:
   - Full style guide: 800 tokens
   - Distilled: ~200 tokens (preserving persona voice rules + banned phrases, droppeando ejemplos largos)
3. En runtime, si budget tight → usar distilled; si hay holgura → full

**Disparador**: configurable por creator — un flag `use_distilled_style_under_pressure` + threshold de tokens disponibles.

**NO implementes** este como nuevo LLM call en runtime. Precomputa offline y cachea por version hash.

#### C) **TurnAnalysisCompression** — técnica `<analysis>` aplicada al memo

El patrón `<analysis>...</analysis><summary>...</summary>` (drafted + stripped) es aplicable a **el prompt de memo compression** (ya existe en Clonnect: `MEMO_COMPRESSION_PROMPT`).

**Propuesta**: añadir `<analysis>` block al prompt actual. El LLM:
1. Primero drafta su thinking sobre qué facts son redundantes/contradictorios en `<analysis>`
2. Luego emite el memo final en `<memo>`
3. Server-side: `re.sub(r'<analysis>.*?</analysis>', '', out, flags=re.DOTALL)` antes de persistir

**Beneficio esperado**: memos más coherentes (chain-of-thought estructurado) sin inflación de tokens persistidos.

**NO implementes** sin primero medir en CCEE si la mejora compensa el output tokens extra.

#### D) **ContextPressureMetric + Circuit Breaker**

Análogo a `AUTOCOMPACT_BUFFER_TOKENS = 13_000` y `MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3`:

**Métrica**: track `prompt_tokens_estimated / budget` en cada generación DM, emitir a logs + Statsig-like.

**Circuit breaker**: si una lead genera 3 consecutive truncation_recovery hits, **marcar la lead** para revisión manual (su memo/facts están en estado irrecuperable, NO seguir retrying).

Razón directa del warning docstring de CC: "250K API calls/day wasted globally" — el mismo riesgo existe en un DM system en escala.

#### E) **PostCompactReload** — análogo a postCompactCleanup

Cuando un reply falla por context pressure → Clonnect hoy re-genera con prompt más corto. Debería también:
- Invalidar RAG cache del lead (trigger re-rank con chunks más pequeños)
- Forzar recall() con `budget=min_recall_budget` (re-entrar con menos context)
- Emitir evento `ctx_pressure_recovery` para análisis offline

No clear-es demasiado: en Clonnect no hay hooks ni module-level state grande.

### 5.4 Priority matrix (no implementación, solo análisis)

| # | Componente | ROI esperado | Riesgo | Dependencias |
|---|-----------|---|---|---|
| A | PromptSliceCompactor | **Alto** (ataca el 41% style directo) | Medio (cambia prompt ratios) | cache_boundary.py ya creado |
| B | StyleDistillCache | Alto (−600 tokens/request) | Bajo (precomputado, opt-in) | DB migration para versionado |
| D | ContextPressureMetric + Circuit Breaker | Medio (ahorro futuro en edge cases) | Muy bajo (read-only metric) | Logging infra |
| C | TurnAnalysisCompression en memo | Bajo-Medio (calidad > coste) | Medio (cambia MEMO prompt) | CCEE measurement gate |
| E | PostCompactReload | Bajo (edge cases) | Bajo | truncation_recovery existente |

### 5.5 Lo que NO hay que copiar de CC

- **Forked-agent LLM summary**: Clonnect es single-shot; meter un forked LLM call en el hot path de DM añade 2-5s latency que mata el UX.
- **compact boundary markers**: no hay conversación-server-side que marcar.
- **SessionStart hooks post-compact**: no aplica, no hay session concept.
- **Cache-edit API**: proveedores de Clonnect (Gemini/OpenRouter) no exponen esa API.

---

## Referencias

- `src/services/compact/microCompact.ts` — 531 líneas, 3 paths
- `src/services/compact/autoCompact.ts` — 352 líneas, thresholds y circuit breaker
- `src/services/compact/prompt.ts` — 375 líneas, 9-section template + `<analysis>` stripping
- `src/services/compact/compact.ts` — 1708 líneas (solo ~120 leídas), `buildPostCompactMessages`, `compactConversation`, `createPostCompactFileAttachments`
- `src/services/compact/sessionMemoryCompact.ts` — 630 líneas, L2 preempt path
- `src/services/compact/postCompactCleanup.ts` — 78 líneas, cache invalidation tree
- `src/services/compact/timeBasedMCConfig.ts` — 43 líneas, 60-min gap threshold
- `src/services/SessionMemory/sessionMemory.ts` — 150+ líneas leídas, background extraction
- `src/query.ts:1060-1185` — reactiveCompact invocation site (archivo mismo no en build OSS)

**Archivos Clonnect relevantes para adaptación**:
- `core/dm/phases/context.py` (1253 líneas) — donde live el prompt composition
- `core/dm/cache_boundary.py` (137 líneas, untracked) — nuevo, candidato a host PromptSliceCompactor
- `services/prompt_service.py` (231 líneas) — style guide carrier, candidato StyleDistillCache
