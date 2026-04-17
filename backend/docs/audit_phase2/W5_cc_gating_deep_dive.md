# W5 — Forense CC Gating (per-turn)

**Worker:** W5
**Modelo:** Opus 4.6 (effort=max)
**Fecha:** 2026-04-16
**Scope:** Documentar **exactamente** cómo Claude Code (CC) decide qué attachments inyectar per-turn, y **sin implementar**, proponer adaptación a Clonnect (DM single-shot).
**Fuentes primarias:**
- `~/instructkr-claude-code/src/utils/attachments.ts` (3997 líneas)
- `~/instructkr-claude-code/src/query.ts` (1729 líneas)
- `~/instructkr-claude-code/src/utils/attachments.ts:743` — `getAttachments()` orchestrator
- `~/instructkr-claude-code/src/utils/attachments.ts:1005` — `maybe()` wrapper

> **Nota terminológica.** El CRUCE §2 y DEEP_DIVE_CC usan "`getAttachments`". En el código real la función exportada se llama **`getAttachments`** (attachments.ts:743) y el wrapper desde query.ts es **`getAttachmentMessages`** (importado de `./utils/attachments.js`, llamado en query.ts:1580). Ambas se refieren al mismo sistema. En este documento uso `getAttachments` para la función orchestrator.

---

## 0. TL;DR Arquitectónico

CC no tiene **un orchestrator central que decida priorización**. Tiene un **dispatcher paralelo** (`getAttachments`) que ejecuta ~38 gates independientes en paralelo, cada uno envuelto en un `maybe()` que captura errores y loggea duración. El sistema es **distribuido, fail-silent, y stateless en su mayor parte**:

- **Cada gate decide autónomamente** si inyecta algo; no hay negociación entre gates por budget.
- **El cap por categoría está hard-coded dentro de cada gate** (ej. MAX_MEMORY_BYTES=4096 dentro de `readMemoriesForSurfacing`).
- **El único "session-wide cap" real** es `RELEVANT_MEMORIES_CONFIG.MAX_SESSION_BYTES = 60KB` — y sólo gatekeea `startRelevantMemoryPrefetch`, no re-prioriza lo ya inyectado.
- **La prioridad efectiva emerge del orden de concatenación**: `[userAttachments, threadAttachments, mainThreadAttachments]` (attachments.ts:998-1001), pero como todos corren en paralelo, "prioridad" = "quién llena el prompt primero" no se aplica — el prompt final los concatena todos.
- **Timeout global: 1000ms** (attachments.ts:767) — todos los gates comparten un `AbortController` que dispara abort tras 1s. Gates que tardan más se cancelan silenciosamente.

El truco real: **cada gate está diseñado para ser idempotente, barato (< 50ms típicos) y auto-throttlable por inspección del histórico de mensajes**. Compact naturalmente resetea throttles porque el histórico desaparece.

---

## 1. El Orchestrator `getAttachments`

**Archivo:** `src/utils/attachments.ts:743-1003`
**Signatura:**
```ts
export async function getAttachments(
  input: string | null,
  toolUseContext: ToolUseContext,
  ideSelection: IDESelection | null,
  queuedCommands: QueuedCommand[],
  messages?: Message[],
  querySource?: QuerySource,
  options?: { skipSkillDiscovery?: boolean },
): Promise<Attachment[]>
```

### Flujo de control

```
getAttachments(input, ctx, ...)
│
├─ if CLAUDE_CODE_DISABLE_ATTACHMENTS || CLAUDE_CODE_SIMPLE:
│     return getQueuedCommandAttachments(queuedCommands)   # bailout
│
├─ abortController = createAbortController()
│  setTimeout(() => ac.abort(), 1000)                       # 1s hard cap
│
├─ userInputAttachments = input ? [                         # sequential-first
│     maybe('at_mentioned_files', ...),
│     maybe('mcp_resources', ...),
│     maybe('agent_mentions', ...),
│     …skill_discovery (if EXPERIMENTAL_SKILL_SEARCH)
│  ] : []
│  await Promise.all(userInputAttachments)                  # populates
│                                                           # nestedMemoryAttachmentTriggers
│
├─ allThreadAttachments = [                                 # all threads
│     queued_commands, date_change, ultrathink_effort,
│     deferred_tools_delta, agent_listing_delta,
│     mcp_instructions_delta,
│     (BUDDY) companion_intro,
│     changed_files, nested_memory,
│     dynamic_skill, skill_listing,
│     plan_mode, plan_mode_exit,
│     (TRANSCRIPT_CLASSIFIER) auto_mode, auto_mode_exit,
│     todo_reminders|task_reminders,
│     (AgentSwarms) teammate_mailbox, team_context,
│     agent_pending_messages,
│     critical_system_reminder,
│     (COMPACTION_REMINDERS) compaction_reminder,
│     (HISTORY_SNIP) context_efficiency,
│  ]
│
├─ mainThreadAttachments = isMainThread ? [                 # main only
│     ide_selection, ide_opened_file,
│     output_style,
│     diagnostics, lsp_diagnostics,
│     unified_tasks, async_hook_responses,
│     token_usage, budget_usd, output_token_usage,
│     verify_plan_reminder,
│  ] : []
│
├─ Promise.all([                                            # PARALLEL
│     Promise.all(allThreadAttachments),
│     Promise.all(mainThreadAttachments)
│  ])
│
├─ clearTimeout(timeoutId)
│
└─ return [                                                 # CONCAT ORDER
     ...userAttachmentResults.flat(),
     ...threadAttachmentResults.flat(),
     ...mainThreadAttachmentResults.flat(),
   ]
```

### El wrapper `maybe()` (attachments.ts:1005-1042)

Cada gate está envuelto en un higher-order:

```ts
async function maybe<A>(label: string, f: () => Promise<A[]>): Promise<A[]> {
  const start = Date.now()
  try {
    const result = await f()
    if (Math.random() < 0.05) {                             # 5% sampling
      logEvent('tengu_attachment_compute_duration', {
        label, duration_ms, attachment_size_bytes, attachment_count
      })
    }
    return result
  } catch (e) {
    logError(e); logAntError(…)
    return []                                               # FAIL SILENT
  }
}
```

**Implicaciones:**
- Errores en un gate no afectan a otros (aislamiento).
- Telemetría 5%-sampled — un gate lento en 1 turn no siempre aparece en logs.
- `return []` en failure = **no se distingue "no aplica" de "crashed"** desde fuera.

### El "orden de prioridad" implícito

No hay prioridad explícita, pero hay **tres decisiones estructurales** que actúan como priority proxy:

1. **User-input attachments van primero** (`await Promise.all(userInputAttachments)` antes del bloque thread).
   **Razón (attachments.ts:817-818):** `processAtMentionedFiles` popula `nestedMemoryAttachmentTriggers` que `getNestedMemoryAttachments` consume después.
2. **Thread + main-thread en paralelo** — no compiten por tiempo, cada uno por su cap interno.
3. **Concat final es estable** (attachments.ts:998-1001): user → thread → main. El modelo ve los attachments en ese orden.

---

## 2. Catálogo exhaustivo de Gates

Documento **cada gate** con su entry en el formato solicitado.

### 2.1 Per-turn caps (memoria)

#### Gate: `relevant_memories`
- **Archivo:line:** `attachments.ts:2196` (selector) + `attachments.ts:2361` (prefetch) + `query.ts:1599-1614` (consume)
- **Trigger:** User envía input con ≥2 palabras (single-word prompts skipped).
- **Throttle:** Ninguno per-turn. Gate session-wide vía `MAX_SESSION_BYTES=60*1024`.
- **Cap:**
  - `MAX_MEMORY_LINES = 200` (por archivo, attachments.ts:269)
  - `MAX_MEMORY_BYTES = 4096` (por archivo, attachments.ts:277)
  - **5 archivos máximo por inyección** (`.slice(0, 5)` en attachments.ts:2234)
  - Efectivo: 5 × 4KB = 20KB/turn
  - Session cap: 60KB acumulado (attachments.ts:288, ~3 inyecciones completas)
- **Contenido:** `{ type: 'relevant_memories', memories: [{path, content, mtimeMs, header, limit?}] }`
  Se inyecta como `<system-reminder>` (bypass el per-message tool-result budget, por eso el per-file byte cap).
- **Depende de:**
  - `isAutoMemoryEnabled()` — `.claude/memory/` existe
  - GrowthBook flag `tengu_moth_copse` (attachments.ts:2367)
  - `collectSurfacedMemories(messages)` — escanea histórico para `alreadySurfaced` set (attachments.ts:2251-2266) + byte tally
  - `readFileState` — filtra archivos ya leídos por el modelo vía FileReadTool
- **Ejecución:** **async prefetch** vía `startRelevantMemoryPrefetch` (attachments.ts:2361), llamado una vez por user turn desde query.ts. Se consume post-tools en query.ts:1599-1614 con `using` para cleanup automático.
- **Failure mode:** Si el prefetch no ha settled al collect point, skip y retry en siguiente iteration (zero-wait).

**Comentario clave** (attachments.ts:280-288):
> "Per-turn cap (5 × 4KB = 20KB) bounds a single injection, but over a long session the selector keeps surfacing distinct files — ~26K tokens/session observed in prod. Cap the cumulative bytes: once hit, stop prefetching entirely. Budget is ~3 full injections; after that the most-relevant memories are already in context. Scanning messages (rather than tracking in toolUseContext) means compact naturally resets the counter."

**Decisión arquitectónica crítica:** byte-counting via message scanning → **compaction resetea automáticamente**. No hay state externa que mantener en sincronía.

---

### 2.2 Throttle intervals — turn-based

#### Gate: `plan_mode`
- **Archivo:line:** `attachments.ts:1186-1242`
- **Trigger:** `appState.toolPermissionContext.mode === 'plan'`
- **Throttle:** Cada `PLAN_MODE_ATTACHMENT_CONFIG.TURNS_BETWEEN_ATTACHMENTS = 5` **human turns** (attachments.ts:259-262).
  - "Human turn" = message.type==='user' && !isMeta && !hasToolResultContent (attachments.ts:1146-1150).
  - Excluye tool-result messages explícitamente — crítico porque el tool loop llama getAttachmentMessages por cada tool round (attachments.ts:1140-1142).
  - **Primera turn en plan mode: no throttle** (si `foundPlanModeAttachment === false`, siempre adjunta).
- **Cap:** 1 attachment por emisión.
- **Contenido:** `{ type: 'plan_mode', reminderType: 'full' | 'sparse', isSubAgent, planFilePath, planExists }`
  - **Full/sparse cycle:** `FULL_REMINDER_EVERY_N_ATTACHMENTS = 5`. 1°, 6°, 11°… = full; resto = sparse.
  - Plus `plan_mode_reentry` attachment si `hasExitedPlanModeInSession() && plan file exists`.
- **Depende de:** Permission context mode, plan file existence, session state flag `hasExitedPlanModeInSession`.

#### Gate: `auto_mode`
- **Archivo:line:** `attachments.ts:1335-1374` (gated on `feature('TRANSCRIPT_CLASSIFIER')`)
- **Trigger:** `mode === 'auto'` OR (`mode === 'plan'` AND `autoModeStateModule.isAutoModeActive()`).
- **Throttle:** `AUTO_MODE_ATTACHMENT_CONFIG.TURNS_BETWEEN_ATTACHMENTS = 5` (attachments.ts:264-267).
  - Cuenta human turns backward hasta encontrar último `auto_mode` attachment.
  - `auto_mode_exit` attachment **resetea el throttle** (attachments.ts:1305-1308).
- **Cap:** 1 attachment por emisión.
- **Contenido:** `{ type: 'auto_mode', reminderType: 'full'|'sparse' }` (ciclo cada 5 como plan_mode).
- **Depende de:** `feature('TRANSCRIPT_CLASSIFIER')`, permission mode, autoModeStateModule.

**Comentario clave** (attachments.ts:1284-1287):
> "a single human turn with 100 tool calls would fire ~20 reminders if we counted assistant messages. Auto mode's target use case is long agentic sessions, where this accumulated 60-105× per session."

#### Gate: `todo_reminders` / `task_reminders` (v1 / v2)
- **Archivo:line:** `attachments.ts:3266-3317` (v1) + `attachments.ts:3375-3432` (v2)
- **Dispatch:** En orchestrator line 893-897: `isTodoV2Enabled() ? getTaskReminderAttachments : getTodoReminderAttachments`.
- **Trigger (v1):** TodoWrite tool en el toolkit; dispara reminder.
- **Trigger (v2):** TaskUpdate tool en el toolkit; ant-only (`USER_TYPE==='ant'`).
- **Throttle (ambas):**
  - `TODO_REMINDER_CONFIG.TURNS_SINCE_WRITE = 10` (attachments.ts:254-257)
  - `TODO_REMINDER_CONFIG.TURNS_BETWEEN_REMINDERS = 10`
  - **AND lógico:** ambos thresholds deben cumplirse.
  - Cuenta **assistant turns** (no human turns, a diferencia de plan/auto mode). Ignora thinking messages.
- **Cap:** 1 attachment.
- **Contenido:** `{ type: 'todo_reminder'|'task_reminder', content: todos|tasks, itemCount }`
- **Depende de:** Tool en toolkit, BRIEF_TOOL (SendUserMessage) NO está en toolkit (si está, skip — BRIEF conflicts with nag pattern).

#### Gate: `verify_plan_reminder`
- **Archivo:line:** `attachments.ts:3894-3929`
- **Trigger:** `USER_TYPE==='ant'` + env `CLAUDE_CODE_VERIFY_PLAN` truthy + `appState.pendingPlanVerification` existe + verification no iniciada/completada.
- **Throttle:** Cuenta human turns desde `plan_mode_exit` (attachments.ts:3872-3889). Dispara cada `VERIFY_PLAN_REMINDER_CONFIG.TURNS_BETWEEN_REMINDERS = 10` turns (attachments.ts:291-293), con módulo exacto (no "≥").
  - Dato crítico: **cuenta desde plan_mode_exit, no desde start** → reminder sólo post-implementation.
- **Cap:** 1 attachment `{ type: 'verify_plan_reminder' }`.
- **Depende de:** ant user, env flag, plan verification state.

---

### 2.3 One-time events (flag-gated)

#### Gate: `plan_mode_exit`
- **Archivo:line:** `attachments.ts:1248-1273`
- **Trigger:** `needsPlanModeExitAttachment()` flag == true (set elsewhere cuando user exit plan mode).
- **Throttle:** N/A — one-shot. Flag se clearea inmediatamente (`setNeedsPlanModeExitAttachment(false)`).
- **Bailout:** Si aún estamos en plan mode (mode==='plan'), clear flag pero no emit.
- **Cap:** 1 attachment.
- **Contenido:** `{ type: 'plan_mode_exit', planFilePath, planExists }`

#### Gate: `auto_mode_exit`
- **Archivo:line:** `attachments.ts:1380-1400`, gated en `TRANSCRIPT_CLASSIFIER`.
- **Trigger:** `needsAutoModeExitAttachment()` flag == true.
- **Bailout:** Si aún activo (mode==='auto' OR autoModeStateModule.isAutoModeActive()), clear flag pero no emit.
- **Cap:** 1 attachment `{ type: 'auto_mode_exit' }`.

#### Gate: `date_change`
- **Archivo:line:** `attachments.ts:1415-1444`
- **Trigger:** `getLocalISODate() !== getLastEmittedDate()`.
- **Throttle:** Se ejecuta cada turn pero noop si date igual. Flag `lastDate === null` → first turn, record pero don't emit (no primer date_change).
- **Cap:** 1 attachment.
- **Contenido:** `{ type: 'date_change', newDate: currentDate }`
- **Side-effect (KAIROS feature):** Flush yesterday's transcript to per-day file via `sessionTranscriptModule.flushOnDateChange` si KAIROS activo.

**Comentario arquitectónico clave** (attachments.ts:1406-1411):
> "The date_change attachment is appended at the tail of the conversation, so the model learns the new date without mutating the cached prefix. messages[0] intentionally keeps the stale date — clearing that cache would regenerate the prefix and turn the entire conversation into cache_creation on the next turn (~920K effective tokens per midnight crossing per overnight session)."

**→ Patrón crítico:** **Prefix cache hygiene**. Signals dinámicos **nunca mutan el prefix**; van al tail.

#### Gate: `max_turns_reached`
- **Archivo:line:** `query.ts:1509-1513` (aborted path) + `query.ts:1706-1710` (normal path)
- **Trigger:** `maxTurns && nextTurnCount > maxTurns`
- **Ubicación anómala:** NO está en `attachments.ts`. Se genera inline en `query.ts` en dos puntos (aborted-with-turns-exceeded y normal-with-turns-exceeded).
- **Cap:** 1 attachment `{ type: 'max_turns_reached', maxTurns, turnCount }`.
- **Observación:** Esto rompe la abstracción "todos los attachments vienen de getAttachments". `max_turns_reached` es un terminal signal cuyo lugar natural es el tool loop, no el dispatcher.

---

### 2.4 Feature-gated gates

#### Gate: `companion_intro` (BUDDY)
- **Archivo:line:** `attachments.ts:864-870`, gated en `feature('BUDDY')`.
- **Trigger:** Buddy feature on. Internals en `buddy/prompt.ts` (`getCompanionIntroAttachment`).
- **Throttle:** Inferido por `messages` scan (una vez por conversación típicamente).

#### Gate: `auto_mode`, `auto_mode_exit` (TRANSCRIPT_CLASSIFIER)
- Ya documentados en §2.2-§2.3.

#### Gate: `compaction_reminder` (COMPACTION_REMINDERS)
- **Archivo:line:** `attachments.ts:3931-3955`
- **Trigger stack:**
  1. `feature('COMPACTION_REMINDERS')` ON (en orchestrator 922-933)
  2. GrowthBook `tengu_marble_fox` ON
  3. `isAutoCompactEnabled()` true
  4. Model contextWindow >= 1_000_000 tokens
  5. `usedTokens >= effectiveWindow * 0.25` (25% de window usado)
- **Cap:** 1 attachment `{ type: 'compaction_reminder' }`.
- **Lógica:** Sólo en modelos con ventanas >= 1M (Claude 4+), alertar cuando usaste ≥25% del contexto.

#### Gate: `context_efficiency` (HISTORY_SNIP)
- **Archivo:line:** `attachments.ts:3963-3983`
- **Trigger:**
  1. `feature('HISTORY_SNIP')`
  2. `isSnipRuntimeEnabled()` true
  3. `shouldNudgeForSnips(messages)` true — lógica en `snipCompact.ts`:
     - Cada N tokens de crecimiento sin snip; reset en snips/nudges/compacts previos.
- **Cap:** 1 attachment `{ type: 'context_efficiency' }`.
- **Nota:** La lógica de pacing está en `shouldNudgeForSnips`, no en este gate — el gate sólo consulta el snip module.

#### Gate: `teammate_mailbox` + `team_context` (AgentSwarms)
- **Archivos:** `attachments.ts:3532-3769` + `attachments.ts:3775-3805`
- **Trigger stack:**
  - `isAgentSwarmsEnabled()`
  - `USER_TYPE==='ant'`
  - Resolved `agentName` via AsyncLocalStorage/dynamicTeamContext/teamContext
  - Excluido si `querySource === 'session_memory'` (attachments.ts:904) — evita robo de mensajes por forked agent.
- **Contenido:** Lista de mensajes unread de teammates (deduped por from+timestamp+text prefix; idle-notifications collapsed to latest).
- **Side-effects:**
  - Marca mensajes como leídos **después** de construir el attachment (evita loss si falla).
  - Procesa `shutdown_approved` messages → remove teammate del team file, unassign tasks.
- **Cap por attachment:** No hay — todos los mensajes unread se devuelven. Hay dedup pero no truncation por size.
- **Team context:** Sólo primer turno para teammates (no team lead); detecta con `messages.some(m => m.type === 'assistant')`.

#### Gate: `skill_discovery` (EXPERIMENTAL_SKILL_SEARCH)
- **Archivo:** `attachments.ts:801-813`, gated en `feature('EXPERIMENTAL_SKILL_SEARCH') && skillSearchModules && !options?.skipSkillDiscovery`.
- **Trigger:** User input presente + gate pasa.
- **Bailout explícito:** `skipSkillDiscovery` se pasa para evitar disparar discovery cuando `input` es un SKILL.md auto-expanded (ej. 110KB de contenido fires ~3.3s AKI queries; session 13a9afae).
- **Contenido:** `getTurnZeroSkillDiscovery(input, messages, ctx)` — turn-0 Haiku/AKI call.

#### Gate: `KAIROS`
- Aparece como **feature modifier** en `date_change` (attachments.ts:1437-1441) y en BRIEF_TOOL_NAME init (attachments.ts:200-205).
- No es un gate independiente — modifica comportamiento de gates existentes (`date_change` trigger flushOnDateChange).

#### BG_SESSIONS
- **Archivo:** `query.ts:1685-1702`
- **Trigger:** `feature('BG_SESSIONS')` + `!toolUseContext.agentId` (main thread only) + `taskSummaryModule.shouldGenerateTaskSummary()`.
- **Acción:** Fire-and-forget `maybeGenerateTaskSummary` con fork del contexto.
- **Observación:** No inyecta un attachment via getAttachments — genera un summary side-channel. Es más un **hook** que un gate de inyección.

---

### 2.5 Delta-based gates (cache-friendly)

#### Gate: `deferred_tools_delta`
- **Archivo:line:** `attachments.ts:1455-1475`
- **Trigger stack:**
  1. `isDeferredToolsDeltaEnabled()`
  2. `isToolSearchEnabledOptimistic()`
  3. `modelSupportsToolReference(model)`
  4. `isToolSearchToolAvailable(tools)`
  5. `getDeferredToolsDelta(tools, messages, scanContext)` returns non-null delta.
- **Lógica:** Diff entre tools actuales vs. tools ya anunciados (reconstruidos de attachments previos).
- **Cap:** 1 attachment con payload = delta (no full list).
- **Export note:** "Exported for compact.ts — the gate must be identical at both call sites."

#### Gate: `agent_listing_delta`
- **Archivo:line:** `attachments.ts:1490-1556` (aproximado; función continúa)
- **Trigger:** `shouldInjectAgentListInMessages()` + AgentTool en pool + hay delta de agents.
- **Razón** (attachments.ts:1482-1488): El agent list se embedía en la description de AgentTool, causando ~10.2% del fleet cache_creation. Mover a delta attachment mantiene la tool description estática.

#### Gate: `mcp_instructions_delta`
- **Archivo:line:** `attachments.ts:1559-1585` (aprox).
- **Trigger:** `isMcpInstructionsDeltaEnabled()` + hay delta en MCP instructions.
- Mismo patrón cache-friendly que los dos anteriores.

---

### 2.6 Contextual gates (siempre evaluados)

#### Gate: `queued_commands`
- **Archivo:** `attachments.ts:1046-1083`
- **Trigger:** `queuedCommands` con mode ∈ {'prompt', 'task-notification'}.
- **Cap:** Ninguno — todos los queued se inyectan con imageBlocks procesados.
- **Agent scoping** (query.ts:1566-1578): Main thread → agentId===undefined; subagents → sólo task-notifications con su agentId.

#### Gate: `changed_files`
- **Archivo:** `attachments.ts:2063-2161`
- **Trigger:** `readFileState` tiene paths cacheados + mtime cambió + no deny rules + pasa `FileReadTool.validateInput`.
- **Cap:** Por archivo: aplica `MAX_LINES_TO_READ` y `readImageWithTokenBudget` para imágenes.
- **Contenido:** `{ type: 'edited_text_file', filename, snippet }` (snippet = diff extract vía `getSnippetForTwoFileDiff`) o `edited_image_file`.
- **Eviction rule (crítica):** Sólo evict del `readFileState` en ENOENT (archivo borrado). Transient failures (EACCES, race-with-atomic-save de VS Code format-on-save) NO evict (attachments.ts:2144-2156, ver PR #18525).

#### Gate: `nested_memory`
- **Archivo:** `attachments.ts:2167-2194`
- **Trigger:** `toolUseContext.nestedMemoryAttachmentTriggers.size > 0`.
- **Activación:** `processAtMentionedFiles` popula los triggers cuando user menciona un archivo; este gate luego carga CLAUDE.md nested desde CWD hasta el target file.
- **Side-effect:** `nestedMemoryAttachmentTriggers.clear()` post-inyección — se consume.

#### Gate: `dynamic_skill`
- **Archivo:** `attachments.ts:2547-2601`
- **Trigger:** `dynamicSkillDirTriggers.size > 0` (skill dirs nuevos detectados).
- **Cap:** Reporta todos los SKILL.md candidates encontrados por dir.

#### Gate: `skill_listing`
- **Archivo:** `attachments.ts:2661+`
- **Trigger stack:**
  - `NODE_ENV !== 'test'`
  - Skill tool en toolkit
  - Hay `newSkills` (no todos ya sent)
- **State:** `sentSkillNames: Map<agentKey, Set<string>>` — per-agent tracking.
- **Resume handling:** `suppressNextSkillListing()` flag clearea injection en --resume paths (attachments.ts:2633-2636) — evita re-inyectar ~600 tokens por respawn.
- **Skill-search integration:** Si EXPERIMENTAL_SKILL_SEARCH + enabled, filtra a bundled + MCP (`filterToBundledAndMcp`, max 30; fallback bundled-only).

#### Gate: `critical_system_reminder`
- **Archivo:** `attachments.ts:1587-1595`
- **Trigger:** `toolUseContext.criticalSystemReminder_EXPERIMENTAL` set.
- **Cap:** 1 attachment con content.
- **Observación:** Nombrado "EXPERIMENTAL" — probablemente API interna para inyectar reminders críticos desde hooks.

#### Gate: `ultrathink_effort`
- **Archivo:** `attachments.ts:1446-1452`
- **Trigger:** `isUltrathinkEnabled() && input && hasUltrathinkKeyword(input)`.
- **Cap:** 1 attachment `{ type: 'ultrathink_effort', level: 'high' }`.
- **Telemetría:** `logEvent('tengu_ultrathink')`.

---

### 2.7 Main-thread-only gates

#### Gate: `ide_selection`, `ide_opened_file`
- **Archivos:** `attachments.ts:1614-1644` (selection), `getOpenedFileFromIDE` (~1864).
- **Trigger:** IDE conectado (MCP) + ideSelection válida + file no denied.

#### Gate: `output_style`
- **Archivo:** `attachments.ts:1597-1612`
- **Trigger:** `settings.outputStyle !== 'default'`.
- **Cap:** 1 attachment con style name.

#### Gate: `diagnostics`, `lsp_diagnostics`
- **Archivos:** `attachments.ts:2854+`, `2883+`.
- **Trigger:** Diagnostic tracker / LSP registry tienen items.

#### Gate: `unified_tasks`
- **Archivo:** `attachments.ts:3439-3462`
- **Trigger:** Task framework tiene delta de attachments.
- **Contenido:** `task_status` attachments per task (taskId, type, status, deltaSummary, outputFilePath).
- **Side-effect:** `applyTaskOffsetsAndEvictions` actualiza state post-inyección.

#### Gate: `async_hook_responses`
- **Archivo:** `attachments.ts:3464+`
- **Trigger:** `checkForAsyncHookResponses()` returns responses.

#### Gate: `token_usage`
- **Archivo:** `attachments.ts:3807-3826`
- **Trigger:** `CLAUDE_CODE_ENABLE_TOKEN_USAGE_ATTACHMENT` env truthy.
- **Contenido:** `{ used, total, remaining }`.

#### Gate: `output_token_usage`
- **Archivo:** `attachments.ts:3828-3844`
- **Trigger:** `feature('TOKEN_BUDGET')` + budget > 0.
- **Contenido:** `{ turn, session, budget }`.

#### Gate: `budget_usd`
- **Archivo:** `attachments.ts:3846-3862`
- **Trigger:** `maxBudgetUsd !== undefined`.
- **Contenido:** `{ used, total, remaining }`.

#### Gate: `agent_pending_messages`
- **Archivo:** `attachments.ts:1085-1101`
- **Trigger:** `toolUseContext.agentId` set (subagent).
- **Drain:** Llama `drainPendingMessages(agentId, …)` — queued_command attachments con `origin: 'coordinator'`.

---

## 3. DECISION LOGIC — ¿Cómo decide CC qué inyectar?

### 3.1 NO hay orchestrator central que priorice por budget

**Evidencia:** `getAttachments` (attachments.ts:743-1003) es puramente un dispatcher paralelo. No hay código del tipo:

```ts
// CÓDIGO NO EXISTENTE EN CC
const budget = getAvailableTokenBudget()
const gates = sortByPriority([...gates])
for (const gate of gates) {
  const result = await gate()
  if (sizeOf(result) > budget) skip
  results.push(result); budget -= sizeOf(result)
}
```

**En cambio:** Cada gate gestiona su propio cap internamente. El resultado agregado puede ser arbitrariamente grande dentro de los caps individuales.

### 3.2 Cada gate decide **independientemente**, bajo 5 patterns reconocibles

| Pattern | Ejemplo | Throttle mechanism |
|---|---|---|
| **Scan-history throttle** | `plan_mode`, `auto_mode`, `todo`, `task`, `verify_plan` | Iterate messages backward, cuenta turns hasta último attachment similar; compare contra constante. Stateless — compact resetea naturalmente. |
| **Flag + clear** | `plan_mode_exit`, `auto_mode_exit` | AppState flag set externamente; gate clearea post-emit. One-shot. |
| **State diff** | `date_change`, `deferred_tools_delta`, `agent_listing_delta`, `mcp_instructions_delta` | Compara current state vs. last-emitted; emit solo si cambió. |
| **Trigger-consume** | `nested_memory`, `dynamic_skill`, `changed_files`, `agent_pending_messages` | Set/queue populado por otro código; gate lo drena y clear. |
| **Feature + env + threshold** | `compaction_reminder`, `context_efficiency`, `verify_plan_reminder`, `token_usage` | Stack de condiciones; todas AND. Sale temprano con return []. |

### 3.3 Priority proxy = orden de concatenación

```ts
return [
  ...userAttachmentResults.flat(),    // 1st: user-input-driven
  ...threadAttachmentResults.flat(),  // 2nd: context/state signals
  ...mainThreadAttachmentResults.flat(), // 3rd: main-thread-only UX
]
```

El modelo los **ve en ese orden**, lo cual actúa como priority proxy implícito: si Anthropic hubiera querido priorizar algo, lo hubiera puesto primero. Pero dentro de cada grupo, el orden es el declarado en el array literal — sin negociación, sin drops.

### 3.4 Budget compete resolution: **no existe**

No hay resolución de competencia por tokens. El único mecanismo que se acerca es:
- **`RELEVANT_MEMORIES_CONFIG.MAX_SESSION_BYTES = 60KB`** — session-wide para memorias. Pero es un **circuit breaker** (stops prefetching), no un prioritizer.
- **`MAX_MEMORY_BYTES = 4096` per-file + 5 files max** — cap interno del gate.
- **1000ms timeout global** (attachments.ts:767) — cancela gates lentos; efectivamente "budget de tiempo", no de tokens.

### 3.5 Por qué funciona sin priorizador

Razones arquitectónicas:
1. **Caps internos suman a un techo predecible.** Cada gate tiene un techo pequeño; la suma es manejable (~pocas KB típicas).
2. **Gates mutuamente excluyentes por construcción.** Ej: `plan_mode` y `auto_mode` no coexisten (diferentes modes). `plan_mode_exit` y `plan_mode` tampoco (permission mode check).
3. **Telemetría 5%-sampled** para detectar gates runaway post-facto, no en hot path.
4. **Compact como limpia natural.** Cualquier accumulation se resetea en compaction porque gates scanean el histórico vivo.
5. **Cache discipline más importante que size discipline.** El `date_change` fix (attachments.ts:1406-1411) y `agent_listing_delta` (~10.2% del fleet cache_creation saved) son señales de que **Anthropic priorizó cache stability over minimizing tokens**. Meter más contenido al tail es barato; invalidar el prefix es caro.

### 3.6 Resumen operativo: **"muchos gates pequeños, cache-stable, fail-silent, stateless-where-possible"**

Trade-off consciente: sacrificar predictibilidad de tamaño total a cambio de:
- Simplicidad por gate.
- Cache-friendliness (attachments al tail).
- Recovery via compact.
- Desarrollo paralelo (añadir un gate no coordina con los demás).

---

## 4. ADAPTACIÓN A CLONNECT

### 4.1 Contexto: Clonnect DM vs. CC session

| Dimensión | CC | Clonnect |
|---|---|---|
| **Turn model** | Multi-turn live session (minutos-horas) | Single-shot DM per generation (segundos) |
| **History** | In-memory during session, compacta | Persistent en DB entre sessions (meses) |
| **User agent** | Developer usando CLI | Creator's clone respondiendo a lead |
| **Tool loop** | Sí (múltiples iterations por user turn) | No (single LLM call) |
| **File state** | Dynamic (user edits, IDE opens) | Static (creator profile, offerings) |
| **Context window pressure** | Alta (tool results, files, long sessions) | Media (history of DMs) |
| **Cache discipline** | Crítica (prompt caching en stream) | Ya en pipeline (content-hash, per-creator) |

### 4.2 Mapeo gate-por-gate: ¿aplica a Clonnect?

**Leyenda:** ✅ Aplica directo · 🟡 Aplica adaptado · ❌ No aplica · 🆕 Nuevo específico de DM

| CC Gate | Aplica? | Adaptación Clonnect |
|---|---|---|
| `at_mentioned_files` | ❌ | DM no tiene `@file` syntax. |
| `mcp_resources` | ❌ | Sin MCP en pipeline DM. |
| `agent_mentions` | ❌ | Sin multi-agent en DM. |
| `skill_discovery` | ❌ | Sin skills tool. |
| `queued_commands` | ❌ | Sin command queue. |
| `date_change` | 🟡 | **"first_dm_of_new_day_with_lead"** — si `last_dm_date != today`, incluir time-context. Barato y alto valor (especialmente para leads con ciclos largos). |
| `ultrathink_effort` | ❌ | Sin keyword trigger mechanism. |
| `deferred_tools_delta` | ❌ | Sin tool pool. |
| `agent_listing_delta` | ❌ | — |
| `mcp_instructions_delta` | ❌ | — |
| `companion_intro` (BUDDY) | ❌ | — |
| `changed_files` | 🟡 | **"creator_profile_delta"** — si `creator.updated_at > last_dm.generated_at`, inyectar el diff (ej: new offering, new content). |
| `nested_memory` | 🟡 | **"lead_context_nested"** — si el lead menciona un tema (ej: "your article on X"), cargar el memo-relevante del creator. |
| `dynamic_skill` | ❌ | — |
| `skill_listing` | ❌ | — |
| `plan_mode` | ❌ | No hay plan mode. |
| `plan_mode_exit` | ❌ | — |
| `auto_mode` | ❌ | — |
| `auto_mode_exit` | ❌ | — |
| `todo_reminders` | ❌ | — |
| `task_reminders` | ❌ | — |
| `teammate_mailbox` | ❌ | Sin swarms. |
| `team_context` | ❌ | — |
| `agent_pending_messages` | ❌ | — |
| `critical_system_reminder` | 🟡 | **"lead_urgency_signal"** — si `lead.status==='hot'` o similar flag, inyectar reminder explícito de priorizar close. |
| `compaction_reminder` | 🟡 | **"conversation_compression_needed"** — si la serialización del histórico de DMs con este lead > threshold, trigger compress. |
| `context_efficiency` | 🟡 | Misma idea que ↑, variante más light (nudge vs hard compress). |
| `ide_selection` | ❌ | — |
| `ide_opened_file` | ❌ | — |
| `output_style` | ✅ | **"creator_voice_style"** — ya tenemos esto en el pipeline, pero el pattern CC valida: inyectar al tail, no al prefix. |
| `diagnostics`, `lsp_diagnostics` | ❌ | — |
| `unified_tasks` | ❌ | — |
| `async_hook_responses` | ❌ | — |
| `token_usage` | ❌ | Interno al runtime, no semantic. |
| `output_token_usage` | ❌ | — |
| `budget_usd` | ❌ | — |
| `verify_plan_reminder` | ❌ | — |
| `max_turns_reached` | ❌ | DM es single-shot. |
| `relevant_memories` | ✅ | **Aplicación directa**. Ya tenemos `memories` en Clonnect; el pattern CC valida: cap per-file + session cap + scan-history throttle. Actualmente Clonnect usa static flags — migrar a scan-history throttle es alto valor. |

**Resumen:** de ~38 gates CC, **~10 son aplicables (directa o adaptada)** a Clonnect.

### 4.3 Nuevos gates específicos de DM (🆕)

Gates que CC no tiene pero son naturales para DM:

1. **`last_contact_age`** — Si `now - last_dm.sent_at > N days`, inyectar bridge ("hace tiempo que no hablamos de...").
2. **`unread_inbound_summary`** — Si hay DMs inbound unreplied por el lead entre el último outbound y ahora (ej. lead mandó 3 mensajes seguidos), resumen.
3. **`first_contact`** — Si no hay DMs previos con este lead, inyectar "intro" reminder (presentarse, tono inicial, no pushy).
4. **`creator_content_freshness`** — Si el lead menciona contenido del creator (post, video, artículo) y la publish_at está en últimos N días, attachar content excerpt.
5. **`lead_funnel_stage_delta`** — Si el lead ha avanzado en el funnel (ej: de cold→warm), inyectar delta de stage + guardrails relevantes.
6. **`business_context_intent`** — NLU ligero en el inbound DM: si detecta intent ∈ {pricing, service, booking}, attachar offerings del creator.
7. **`time_zone_greeting`** — Si es primera DM en el "día local del lead" (derivar de lead.timezone), incluir cue de greeting apropiado.
8. **`emotional_escalation`** — Si el inbound DM tiene señales de escalación emocional (regex + sentiment), inyectar de-escalation guardrail.
9. **`conversation_length_warning`** — Si la conversación lead-clone lleva >N messages sin conversion signal, inyectar "shift strategy" reminder.
10. **`recurring_question_detected`** — Si el inbound repite pregunta ya respondida en historial, inyectar "don't repeat yourself, acknowledge and advance".

### 4.4 Pseudocódigo propuesto — `decide_attachments_clonnect`

**NO implementado. Diseño conceptual.**

```python
# core/dm/attachments/orchestrator.py (hypothetical)

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable
import asyncio

@dataclass(frozen=True)
class DmAttachment:
    """Tail-appended signal for the DM generation prompt.
    Mirrors CC's Attachment: lives at tail, never mutates the
    cached prefix (creator profile, voice, system instructions)."""
    type: str
    payload: dict
    # Estimated tokens; used by telemetry but NOT by a priority resolver.
    # Caps are enforced inside each gate, not globally.
    est_tokens: int

@dataclass
class DmContext:
    """Everything a gate needs to decide. Analog of ToolUseContext.
    All fields are pre-loaded from DB before orchestrator runs."""
    lead: Any                    # Lead DB row
    creator: Any                 # Creator DB row
    inbound_dm: Any              # The triggering inbound DM
    dm_history: list[Any]        # Prior DMs with this lead (chronological)
    creator_memories: Any        # Memory store for this creator
    creator_content: Any         # Creator's posts/articles recent
    now: datetime                # Wall clock — injected for testability

# ---------------------------------------------------------------------
# Per-gate pattern: async function returning list[DmAttachment].
# Each gate owns its own cap. Returns [] when not triggered OR on error.
# ---------------------------------------------------------------------

async def _maybe(
    label: str,
    f: Callable[[], Awaitable[list[DmAttachment]]],
) -> list[DmAttachment]:
    """Mirrors CC's maybe(): error isolation, 5% telemetry."""
    start = datetime.now()
    try:
        result = await f()
        if should_sample(0.05):
            log_event("dm_attachment_compute", {
                "label": label,
                "duration_ms": (datetime.now() - start).total_seconds() * 1000,
                "count": len(result),
                "est_tokens": sum(a.est_tokens for a in result),
            })
        return result
    except Exception as e:
        log_error(f"dm_attachment gate '{label}' failed: {e}")
        return []  # Fail silent. No other gate blocked.

# --- Applicable CC gates (adapted) ---

async def gate_relevant_memories(ctx: DmContext) -> list[DmAttachment]:
    """Direct port of CC's relevant_memories pattern.
    Cap: MAX_MEMORY_BYTES=4096 per memo, MAX_FILES=5, MAX_SESSION_BYTES=60K.
    Throttle: scan dm_history for already-surfaced memos (de-dup)."""
    surfaced = collect_surfaced_memories(ctx.dm_history)
    if surfaced.total_bytes >= MAX_SESSION_BYTES:  # 60K per lead-lifetime
        return []
    # Use inbound_dm.text as query; filter by already-surfaced + readFileState analog.
    candidates = await find_relevant_memos(
        query=ctx.inbound_dm.text,
        memories=ctx.creator_memories,
        exclude=surfaced.paths,
        limit=5,
    )
    if not candidates:
        return []
    read = await read_memos_with_cap(candidates, per_file_cap=4096)
    return [DmAttachment(
        type="relevant_memories",
        payload={"memories": read},
        est_tokens=sum(estimate_tokens(m.content) for m in read),
    )]

async def gate_date_change(ctx: DmContext) -> list[DmAttachment]:
    """If the last DM was not today (creator's tz), inject date cue."""
    if not ctx.dm_history:
        return []
    last_local_date = local_date(ctx.dm_history[-1].sent_at, ctx.creator.tz)
    now_local_date = local_date(ctx.now, ctx.creator.tz)
    if last_local_date == now_local_date:
        return []
    return [DmAttachment(
        type="date_change",
        payload={"new_date": str(now_local_date)},
        est_tokens=15,
    )]

async def gate_creator_profile_delta(ctx: DmContext) -> list[DmAttachment]:
    """Analog of CC's changed_files: creator profile edited since last DM."""
    if not ctx.dm_history:
        return []
    last_out = next((d for d in reversed(ctx.dm_history) if d.direction == "out"), None)
    if last_out is None or ctx.creator.updated_at <= last_out.generated_at:
        return []
    diff = compute_creator_delta(
        before_version=last_out.creator_snapshot,
        after=ctx.creator,
    )
    if not diff:
        return []
    return [DmAttachment(
        type="creator_delta",
        payload={"changes": diff},
        est_tokens=estimate_tokens(diff),
    )]

async def gate_output_style(ctx: DmContext) -> list[DmAttachment]:
    """Creator voice style overrides — keep at tail like CC."""
    if ctx.creator.voice_style == "default":
        return []
    return [DmAttachment(
        type="output_style",
        payload={"style": ctx.creator.voice_style},
        est_tokens=30,
    )]

async def gate_critical_reminder(ctx: DmContext) -> list[DmAttachment]:
    """Analog of CC's critical_system_reminder: urgent lead signals."""
    reminders = []
    if ctx.lead.status == "hot":
        reminders.append("HOT_LEAD: prioritize progression, not small talk.")
    if ctx.lead.marked_urgent_at and ctx.lead.marked_urgent_at > (ctx.now - timedelta(hours=24)):
        reminders.append("LEAD_MARKED_URGENT_RECENT")
    if not reminders:
        return []
    return [DmAttachment(
        type="critical_reminder",
        payload={"content": " / ".join(reminders)},
        est_tokens=sum(len(r.split()) for r in reminders),
    )]

# --- New DM-specific gates ---

async def gate_first_contact(ctx: DmContext) -> list[DmAttachment]:
    """First DM ever with this lead → intro guardrails."""
    if ctx.dm_history:
        return []
    return [DmAttachment(
        type="first_contact",
        payload={"guidance": "This is the first message. Introduce briefly, match tone, no pushy offers."},
        est_tokens=25,
    )]

async def gate_last_contact_age(ctx: DmContext) -> list[DmAttachment]:
    """Long silence → bridge context."""
    if not ctx.dm_history:
        return []
    last_any = ctx.dm_history[-1]
    gap = ctx.now - last_any.sent_at
    if gap < timedelta(days=14):
        return []
    return [DmAttachment(
        type="long_silence",
        payload={"days_since": gap.days, "last_topic": last_any.topic_tag},
        est_tokens=20,
    )]

async def gate_unread_inbound_burst(ctx: DmContext) -> list[DmAttachment]:
    """Lead sent N messages without a reply — summarize so we address all."""
    if not ctx.dm_history:
        return []
    # Walk backwards from latest; count consecutive 'in' messages before the last 'out'.
    burst = []
    for dm in reversed(ctx.dm_history):
        if dm.direction == "out":
            break
        burst.append(dm)
    if len(burst) < 2:  # The inbound_dm itself counts as 1; need ≥2 for "burst"
        return []
    return [DmAttachment(
        type="inbound_burst",
        payload={
            "count": len(burst),
            "summary": summarize_burst(burst),
        },
        est_tokens=100,
    )]

async def gate_conversation_compression(ctx: DmContext) -> list[DmAttachment]:
    """Analog of compaction_reminder: history size > threshold → nudge/compact.
    Note: actual compaction runs outside this gate; this just signals."""
    history_tokens = sum(estimate_tokens(d.text) for d in ctx.dm_history)
    if history_tokens < 8000:  # threshold analog
        return []
    return [DmAttachment(
        type="compression_needed",
        payload={"history_tokens": history_tokens},
        est_tokens=15,
    )]

# ---------------------------------------------------------------------
# Orchestrator — mirrors getAttachments. Runs gates in parallel, 1s timeout.
# ---------------------------------------------------------------------

async def decide_attachments_clonnect(ctx: DmContext) -> list[DmAttachment]:
    """Parallel dispatcher of DM gates. No budget resolver: each gate
    enforces its own cap. Ordering at concat mirrors CC's priority proxy."""
    # Global soft deadline like CC's 1s.
    async with asyncio.timeout(1.0):
        # --- User-input-dependent gates (sequential first if deps exist) ---
        # In CC these populate nestedMemoryAttachmentTriggers. In Clonnect
        # we don't yet have such a dependency; leave empty.
        input_results: list[list[DmAttachment]] = []

        # --- State/context gates (parallel) ---
        all_gates = await asyncio.gather(
            _maybe("relevant_memories", lambda: gate_relevant_memories(ctx)),
            _maybe("date_change", lambda: gate_date_change(ctx)),
            _maybe("creator_delta", lambda: gate_creator_profile_delta(ctx)),
            _maybe("output_style", lambda: gate_output_style(ctx)),
            _maybe("critical_reminder", lambda: gate_critical_reminder(ctx)),
            _maybe("first_contact", lambda: gate_first_contact(ctx)),
            _maybe("last_contact_age", lambda: gate_last_contact_age(ctx)),
            _maybe("inbound_burst", lambda: gate_unread_inbound_burst(ctx)),
            _maybe("compression_needed", lambda: gate_conversation_compression(ctx)),
            return_exceptions=False,  # maybe() already swallows
        )

    # Concat order acts as priority proxy (as in CC):
    # input-driven → state signals → stylistic/formatting.
    return [a for batch in (input_results + all_gates) for a in batch]
```

### 4.5 Trade-offs de la adaptación

| Decisión | Pro | Contra | Recomendación |
|---|---|---|---|
| **Parallel + fail-silent** | Aislamiento, latency bajo | Un gate buggy se esconde | Añadir alerta si `len(result) == 0` es sospechoso (ej: gate que siempre debería disparar). |
| **No priority resolver** | Simplicidad | Attachment bloat si muchos gates disparan en DM caliente | Monitorear sum(est_tokens) per-DM; alarm a >N. |
| **Per-gate cap internal** | Control local | Ninguna visión global | Enforce per-type caps via type system (estrategia de medio plazo). |
| **1s timeout** | Cap latencia | Gates lentos se pierden siempre | Trackear cancellation rate por gate; gates > 500ms p99 merecen optimización. |
| **Scan-history throttle** | Stateless (compact resetea naturalmente) | Repetir scan cada DM puede ser O(N) por gate | Pre-computar summaries de dm_history 1 vez, pasar a todos los gates (analog de `messages` en CC). |
| **Cache-stable tail** | Preserva prefix cache | Requiere que template de generation respete la distinción | Verificar que `prompt_service` concatena creator-profile como prefix, attachments como tail. |

### 4.6 Prioridad de migración (desde los flags estáticos actuales)

En orden de valor/esfuerzo:

1. **`relevant_memories` scan-history throttle** — Actualmente static; CC pattern valida alto ROI y es drop-in (session cap simple).
2. **`date_change` (creator tz)** — Barato, alto valor UX (specially lead revive).
3. **`first_contact`** — Barato, corrige un fallo conocido (intros atropellan).
4. **`creator_profile_delta`** — Valor alto para creators que iteran mucho.
5. **`critical_reminder` para hot leads** — Ya hay estado `lead.status`; sólo hay que rutearlo al tail.
6. **`inbound_burst`** — Resuelve lead-fatigue en bursts de DMs.
7. **`compression_needed`** — Defensa contra long-conversations.

El resto (🆕 nuevos) son experiments de producto, no migrations.

---

## 5. Findings para Decisión 2 (diseño arquitectónico)

**Lo que este deep-dive desbloquea:**

1. **CC NO tiene un orchestrator-con-budget.** La premisa del CRUCE §2 ("per-turn dynamic gates") es correcta, pero **el mecanismo NO es priorización por budget** — es **paralelo + caps locales + fail-silent**. Cualquier diseño Clonnect que asuma "sort gates by priority, fill budget" estaría sobre-diseñando vs. CC.

2. **La disciplina real es cache-stability, no token-minimization.** Tres comentarios del código lo demuestran explícitamente (date_change ~920K cache-creation evitados, agent_listing_delta 10.2% fleet cache_creation, skill_listing ~600 tokens/resume). **Recomendación Clonnect: antes de optimizar lo que se inyecta, verificar la topología del prompt** (prefix stable = creator profile, voice, system; tail dynamic = attachments).

3. **Session-wide cap tiene 1 solo lugar (memories).** El resto son per-turn. Para Clonnect, lo análogo es **per-lead-lifetime** (dm_history vive para siempre). Aplicar `MAX_SESSION_BYTES` por lead a `relevant_memories` es directo; no hace falta inventar un global budget.

4. **Throttle-via-history-scan es el workhorse.** 5 de los ~38 gates usan este pattern. Es stateless, robusto a fallos, y compact/reset naturalmente. **Para Clonnect, usar dm_history como source-of-truth para throttle es idiomático** — mejor que mantener state externa (Redis counter, DB flag) que puede des-sincronizarse.

5. **1s timeout global + per-gate 5% telemetry es suficiente para producción.** No hay tracing distribuido inter-gate. **Para Clonnect, empezar con ese presupuesto de observability es razonable**.

6. **`max_turns_reached` está fuera de getAttachments (query.ts).** Es una señal **terminal** del tool loop, no una decoración. En Clonnect no aplica (no hay loop), pero el pattern "señales terminales van donde se generan, no en el orchestrator de attachments" es trasladable (ej: si Clonnect añadiera multi-turn agentic, la señal "conversation ended" no iría en orchestrator sino en el loop).

---

## 6. Referencias clave del código (para búsqueda rápida)

| Referencia | Archivo:línea | Descripción |
|---|---|---|
| Orchestrator principal | `attachments.ts:743` | `getAttachments(input, ctx, ideSelection, queuedCommands, messages, querySource, options)` |
| Error wrapper | `attachments.ts:1005` | `maybe(label, f)` — fail-silent + telemetry |
| Timeout global | `attachments.ts:767` | `setTimeout(ac => ac.abort(), 1000, abortController)` |
| Concat order | `attachments.ts:998-1001` | user → thread → main |
| Memory cap per-file | `attachments.ts:277` | `MAX_MEMORY_BYTES = 4096` |
| Memory session cap | `attachments.ts:288` | `MAX_SESSION_BYTES = 60 * 1024` |
| Plan mode throttle | `attachments.ts:259-262` | `TURNS_BETWEEN_ATTACHMENTS: 5`, `FULL_REMINDER_EVERY_N_ATTACHMENTS: 5` |
| Auto mode throttle | `attachments.ts:264-267` | idem plan_mode |
| Todo reminder throttle | `attachments.ts:254-257` | `TURNS_SINCE_WRITE: 10`, `TURNS_BETWEEN_REMINDERS: 10` |
| Verify plan throttle | `attachments.ts:291-293` | `TURNS_BETWEEN_REMINDERS: 10` |
| Memory prefetch start | `attachments.ts:2361` | `startRelevantMemoryPrefetch` |
| Memory prefetch consume | `query.ts:1599-1614` | Post-tools collect with `using` |
| Tool loop entry | `query.ts:1580` | `getAttachmentMessages(null, ctx, null, queued, [...], querySource)` |
| Max turns signal | `query.ts:1509-1513, 1706-1710` | Generado fuera del orchestrator |
| BG_SESSIONS hook | `query.ts:1685-1702` | Fire-and-forget task summary (not an attachment) |
| Snip feature | `query.ts:401-410` | `snipModule.snipCompactIfNeeded` |

---

## 7. Apéndice — Gates completos en orden de aparición

```
User-input (if input != null):
  1. at_mentioned_files              [attachments.ts:775]
  2. mcp_resources                   [attachments.ts:778]
  3. agent_mentions                  [attachments.ts:781]
  4. skill_discovery                 [attachments.ts:801]  (EXPERIMENTAL_SKILL_SEARCH)

All threads:
  5. queued_commands                 [attachments.ts:829]
  6. date_change                     [attachments.ts:830]
  7. ultrathink_effort               [attachments.ts:833]
  8. deferred_tools_delta            [attachments.ts:836]
  9. agent_listing_delta             [attachments.ts:851]
 10. mcp_instructions_delta          [attachments.ts:854]
 11. companion_intro                 [attachments.ts:864]  (BUDDY)
 12. changed_files                   [attachments.ts:871]
 13. nested_memory                   [attachments.ts:872]
 14. dynamic_skill                   [attachments.ts:874]
 15. skill_listing                   [attachments.ts:875]
 16. plan_mode                       [attachments.ts:881]
 17. plan_mode_exit                  [attachments.ts:882]
 18. auto_mode                       [attachments.ts:885]  (TRANSCRIPT_CLASSIFIER)
 19. auto_mode_exit                  [attachments.ts:888]  (TRANSCRIPT_CLASSIFIER)
 20. todo_reminders|task_reminders   [attachments.ts:893]
 21. teammate_mailbox                [attachments.ts:907]  (AgentSwarms)
 22. team_context                    [attachments.ts:911]  (AgentSwarms)
 23. agent_pending_messages          [attachments.ts:916]
 24. critical_system_reminder        [attachments.ts:919]
 25. compaction_reminder             [attachments.ts:924]  (COMPACTION_REMINDERS)
 26. context_efficiency              [attachments.ts:936]  (HISTORY_SNIP)

Main thread only:
 27. ide_selection                   [attachments.ts:946]
 28. ide_opened_file                 [attachments.ts:949]
 29. output_style                    [attachments.ts:952]
 30. diagnostics                     [attachments.ts:955]
 31. lsp_diagnostics                 [attachments.ts:958]
 32. unified_tasks                   [attachments.ts:961]
 33. async_hook_responses            [attachments.ts:964]
 34. token_usage                     [attachments.ts:967]
 35. budget_usd                      [attachments.ts:975]
 36. output_token_usage              [attachments.ts:980]
 37. verify_plan_reminder            [attachments.ts:983]

Generated outside getAttachments:
 38. max_turns_reached               [query.ts:1509, 1706]

Async side-channels (not attachments):
  -  relevant_memories prefetch     [attachments.ts:2361 → query.ts:1599]
  -  BG_SESSIONS task summary       [query.ts:1685]
  -  skill discovery prefetch       [query.ts:1620]
```

**Total gates orchestrator:** 37 (en `getAttachments`) + 1 fuera (`max_turns_reached`) = **38**.

---

**FIN W5.**
