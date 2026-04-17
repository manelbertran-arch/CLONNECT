# WORKER 4 — Forense Claude Code: Memoria (Módulos no cubiertos)

**Modelo:** Opus 4.6 (effort: max)
**Fecha:** 2026-04-16
**Alcance:** 3 módulos de memoria de Claude Code NO cubiertos en `DEEP_DIVE_CONTEXT_ENGINEERING.md`:

1. `services/extractMemories/` (~600 líneas)
2. `memdir/memoryTypes.ts` (~620 líneas) + helpers (`memdir.ts`, `paths.ts`, `memoryScan.ts`, `memoryAge.ts`, `findRelevantMemories.ts`)
3. `services/SessionMemory/` (~450 líneas)

**Objetivo operativo:** desbloquear fix del *Dual Memory Storage Conflict* (`GRAPH_REPORT.md:54`) y handoff i18n (Sprint 3).

Todas las citas son `archivo:línea` verificadas contra `~/instructkr-claude-code/src/**`.

---

## 1. `services/extractMemories/` — Extracción Post-Turn con Forked Agent

### 1.1 ¿Cuándo se activa?

- **Trigger:** cada vez que el modelo produce una respuesta final **sin tool calls** (final del query loop). Disparado como *fire-and-forget* desde `handleStopHooks`.
  - `query/stopHooks.ts:149` → `void extractMemoriesModule!.executeExtractMemories(...)`.
  - `extractMemories.ts:5-7` comenta literalmente: *"It runs once at the end of each complete query loop (when the model produces a final response with no tool calls) via handleStopHooks in stopHooks.ts."*
- **Init:** `utils/backgroundHousekeeping.ts:35` llama `initExtractMemories()` al arrancar — crea una *closure* con el estado mutable de la extracción (cursor, flags, pending context) — ver `extractMemories.ts:296-587`.
- **Drain:** `cli/print.ts:968` → `await extractMemoriesModule!.drainPendingExtraction()` se ejecuta antes del shutdown para permitir que la extracción en curso termine (con timeout soft 60 s, `extractMemories.ts:579-586`).
- **Condiciones de corto-circuito** (todas en `extractMemories.ts:527-567`):
  - `context.toolUseContext.agentId` — salta si es subagente (línea 532).
  - `!tengu_passport_quail` flag → OFF (línea 536).
  - `!isAutoMemoryEnabled()` (línea 545).
  - `getIsRemoteMode()` (línea 550).
  - Si hay extracción en progreso → *stash* y corre como *trailing run* al terminar la actual (líneas 557-564).
- **Throttling:** `tengu_bramble_lintel` GrowthBook flag define cuántos turnos eligibles esperar entre extracciones (default `1`, línea 381). Los *trailing runs* saltan este check (línea 377).

### 1.2 ¿Cómo decide qué extraer?

No lo decide el código imperativo — lo decide un **forked agent**.

- **Forked agent** (patrón crítico): `runForkedAgent` en `extractMemories.ts:415-427` crea un fork perfecto de la conversación principal — mismo system prompt, mismo prefijo de mensajes — para **compartir el prompt cache** (el fork label es `'extract_memories'`).
- **Cursor:** `lastMemoryMessageUuid` (línea 307) marca el último mensaje procesado. `countModelVisibleMessagesSince` (línea 82-110) cuenta solo mensajes `user`/`assistant` posteriores. Fallback: si el UUID fue eliminado por compaction, cuenta todos los mensajes visibles (línea 103-108) — así la extracción no queda permanentemente inhabilitada.
- **Límite duro:** `maxTurns: 5` (línea 426). Las extracciones bien portadas completan en 2-4 turnos (read → write).
- **Transcripción:** `skipTranscript: true` (línea 423) — el fork no toca el transcript del main thread, evitando races.

### 1.3 ¿Idioma?

**No hay directiva explícita de idioma en el prompt de extracción.** El modelo infiere el idioma orgánicamente del contexto.

- **Prompts de extracción** (`services/extractMemories/prompts.ts`):
  - El opener (líneas 29-44) está íntegramente en inglés ("You are now acting as the memory extraction subagent...").
  - Las instrucciones de save/update (líneas 50-154) están en inglés.
  - El tag ` <when_to_save>`, ejemplos (`memoryTypes.ts:50-55, 65-73`) están en inglés.
- **Modelo decide:** como el fork comparte el system prompt y el prefijo de mensajes del main agent, si la conversación fue en español, la memoria también saldrá en español — el modelo alinea idioma al contenido, no a la instrucción.
- **Implicación para el handoff i18n de Sprint 3:** el bug `MEMO_COMPRESSION_PROMPT generates memo in language of lead facts` (commit `8ae594f9`) es consistente con la enseñanza CC: **NO necesitas decirle al modelo "escribe en X"; le basta con la coherencia del contexto**. Si los facts van en el idioma del lead, el memo debe generarse desde ese mismo contexto (no desde un system prompt forzado en EN).

### 1.4 ¿Tipa las memorias antes de guardar?

**Sí, estrictamente.** Taxonomía cerrada de 4 tipos, *frontmatter* obligatorio.

- Los 4 tipos: `user`, `feedback`, `project`, `reference` (`memoryTypes.ts:14-19`).
- El prompt de extracción inyecta:
  - `TYPES_SECTION_INDIVIDUAL` (`memoryTypes.ts:113-178`) o `TYPES_SECTION_COMBINED` (líneas 37-106) — con `<description>`, `<when_to_save>`, `<how_to_use>`, `<body_structure>`, `<examples>` por tipo.
  - `MEMORY_FRONTMATTER_EXAMPLE` (`memoryTypes.ts:261-271`) — plantilla con `name`, `description`, `type: {user, feedback, project, reference}`.
- Validación en lectura: `parseMemoryType` (`memoryTypes.ts:28-31`) — devuelve `undefined` si el tipo no está en el set (degrada gracefully sin romper legacy files).
- El agente extractor, como cualquier otro, solo puede escribir dentro del `memoryDir` (ver §1.6).

### 1.5 Input / Output

**Input (recibe):**
- `REPLHookContext` con la lista completa de `messages` (extractMemories.ts:338).
- `memoryDir` via `getAutoMemPath()` (línea 339).
- `newMessageCount` calculado vs cursor `lastMemoryMessageUuid` (líneas 340-343).
- **Manifest pre-calculado**: `formatMemoryManifest(await scanMemoryFiles(memoryDir, ...))` inyectado en el prompt (líneas 398-400). Motivo (comentario líneas 396-397): *"Pre-inject the memory directory manifest so the agent doesn't spend a turn on `ls`"*.
- Prompt elegido según feature flag: `buildExtractCombinedPrompt` (TEAMMEM ON) o `buildExtractAutoOnlyPrompt` (default), líneas 403-413.

**Output (produce):**
- Archivos `.md` escritos en `memoryDir` (Write/Edit tool).
- `MEMORY.md` actualizado como índice (patrón 2-step: file + index, `prompts.ts:68-82`).
- Eventos telemetry:
  - `tengu_extract_memories_extraction` (con input/output/cache tokens, líneas 473-485).
  - `tengu_extract_memories_error` (línea 500-502).
  - `tengu_extract_memories_skipped_direct_write` (línea 356-358).
  - `tengu_extract_memories_coalesced` (línea 561) — cuando llega un call durante un in-progress.
- `appendSystemMessage(createMemorySavedMessage(memoryPaths))` (línea 491-495) — notifica al main thread en la UI qué memorias se escribieron (filtrando `MEMORY.md` que es meramente índice, líneas 465-467).

### 1.6 Filesystem ops

**Restricción por `createAutoMemCanUseTool`** (`extractMemories.ts:171-222`) — la garantía *sandbox* del forked agent:

| Tool                  | Política                                                                 | Línea   |
|-----------------------|--------------------------------------------------------------------------|---------|
| `REPL`                | `allow` unconditional (REPL re-invoca `canUseTool` internamente)         | 180-183 |
| `FileRead`, `Grep`, `Glob` | `allow` unconditional (read-only)                                    | 186-191 |
| `Bash`                | `allow` solo si `tool.isReadOnly(data)` — nada de `rm`, `mv`, `echo >…`  | 195-204 |
| `FileEdit`, `FileWrite` | `allow` solo si `isAutoMemPath(file_path)` — ancla al `memoryDir`      | 206-215 |
| **Todo lo demás**     | `deny` con mensaje explícito                                             | 217-221 |

La función se **comparte con `autoDream`** (comentario línea 169), lo que da coherencia entre dos agentes de background.

### 1.7 ¿Cómo evita duplicados?

Cinco capas superpuestas:

1. **Mutex main-agent / fork-agent:** `hasMemoryWritesSince` (líneas 121-148) escanea los mensajes del main agent en busca de `tool_use` Write/Edit dirigidos a `isAutoMemPath`. Si encuentra, el fork **se salta** esa ventana y avanza el cursor (líneas 348-360). Comentario clave (líneas 117-119): *"The main agent's prompt has full save instructions — when it writes memories, the forked extraction is redundant"*.
2. **Manifest pre-inyectado:** el agente ve la lista de archivos existentes antes de escribir, con directiva *"Check this list before writing — update an existing file rather than creating a duplicate"* (`prompts.ts:32`).
3. **Cursor avanza solo tras éxito:** `lastMemoryMessageUuid` se actualiza *después* de `runForkedAgent` OK (líneas 432-435). Si el fork falla, el rango queda disponible para el siguiente intento.
4. **In-progress guard + trailing stash:** `inProgress` flag + `pendingContext` (líneas 313, 320-325). Si entra un call durante la ejecución, se **coalesce**: solo el *último* pendingContext sobrevive (línea 562 comentario: *"overwrites any previously stashed context — only the latest matters"*). Al terminar, se dispara un trailing run (líneas 510-521).
5. **`inFlightExtractions` set + drainer:** `drainPendingExtraction` espera todos los promises en vuelo hasta `timeoutMs` (60 s default) antes de shutdown (líneas 579-586). Evita que el proceso muera con una extracción en curso.

---

## 2. `memdir/memoryTypes.ts` (+ helpers) — Taxonomía Tipada

### 2.1 Los 4 tipos

Definidos como tupla `const` para type inference estricta:

```ts
// memoryTypes.ts:14-19
export const MEMORY_TYPES = [
  'user',
  'feedback',
  'project',
  'reference',
] as const
export type MemoryType = (typeof MEMORY_TYPES)[number]
```

### 2.2 ¿Qué define cada tipo?

Cada bloque `<type>` es un contrato en XML-like prose con 5-6 campos. **Resumen comparativo:**

| Tipo       | `<when_to_save>` trigger                              | `<how_to_use>` al recuperar                    | `<body_structure>` exige `Why:` / `How to apply:` | Scope (solo COMBINED) |
|------------|-------------------------------------------------------|------------------------------------------------|---------------------------------------------------|------------------------|
| `user`     | Aprende rol, preferencias, conocimiento del user      | Adaptar explicaciones al perfil                | No (free-form)                                    | `always private` (memoryTypes.ts:45) |
| `feedback` | User corrige ("no hagas X") O confirma ("sí, eso")    | Guiar comportamiento sin repetir guidance      | **Sí** (memoryTypes.ts:63)                        | `default private, team si es convención de proyecto` (línea 59) |
| `project`  | Aprende quién, qué, por qué, por-cuándo               | Entender contexto más allá del código          | **Sí** (memoryTypes.ts:81)                        | `private o team, bias hacia team` (línea 77) |
| `reference`| Aprende sobre sistemas externos (Linear, Grafana...)  | User referencia sistemas externos              | No                                                | `usually team` (línea 92) |

**Insight de diseño:** `feedback` y `project` exigen `**Why:**` y `**How to apply:**` en el cuerpo (`memoryTypes.ts:63, 81`). El comentario explica por qué: *"Knowing why lets you judge edge cases instead of blindly following the rule"* — la motivación permite al modelo razonar sobre casos borde en lugar de aplicar reglas ciegamente. Esto sobrevive al **memory drift**: cuando el contexto ha cambiado, el *why* permite decidir si la regla sigue aplicando.

**Confirmación explícita como señal válida:** `<when_to_save>` de `feedback` (líneas 61, 135) incluye: *"Corrections are easy to notice; confirmations are quieter — watch for them"*. Es decir, Claude Code instruye al modelo a guardar también **validación silenciosa de decisiones no-obvias**, no solo correcciones. Novedad vs sistemas típicos de "save on correction".

### 2.3 ¿Cómo se usan? (INDIVIDUAL vs COMBINED)

Existen **dos versiones** del mismo bloque de tipos:

- `TYPES_SECTION_INDIVIDUAL` (`memoryTypes.ts:113-178`): sin `<scope>`, ejemplos dicen `[saves <type> memory: …]`.
- `TYPES_SECTION_COMBINED` (`memoryTypes.ts:37-106`): añade `<scope>`, ejemplos dicen `[saves <scope> <type> memory: …]` (ej. `[saves team feedback memory: …]`).

**Justificación** (comentario líneas 9-12): *"The two TYPES_SECTION_\* exports below are intentionally duplicated rather than generated from a shared spec — keeping them flat makes per-mode edits trivial without reasoning through a helper's conditional rendering"*. **DRY sacrificado a propósito por legibilidad y facilidad de ajuste por eval**.

### 2.4 ¿Dónde se almacenan?

En `memdir/paths.ts` se resuelven rutas de forma memoizada:

- **Path por defecto**: `{memoryBase}/projects/{sanitized-git-root}/memory/` (`paths.ts:230-232`).
  - `memoryBase` = `CLAUDE_CODE_REMOTE_MEMORY_DIR` env var **o** `~/.claude` (`paths.ts:85-90`).
  - `git-root` obtenido vía `findCanonicalGitRoot(getProjectRoot())` (`paths.ts:203-205`) — *"so all worktrees of the same repo share one auto-memory directory"* (línea 201, referencia `anthropics/claude-code#24382`).
- **Overrides** (en orden de precedencia):
  1. `CLAUDE_COWORK_MEMORY_PATH_OVERRIDE` env var — usado por Cowork para paths session-mounted (`paths.ts:161-166`).
  2. `autoMemoryDirectory` en settings.json — *solo desde fuentes confiables*: policy / flag / local / user. **`projectSettings` EXCLUIDO** por seguridad (`paths.ts:179-186`, comentarios líneas 171-178).
- **Validación SEC** (`paths.ts:109-150`, función `validateMemoryPath`): rechaza paths relativos, root-like (`/`, `C:\`), UNC (`\\server\share`), null-byte injection, tilde-only (`~/`, `~/.`, `~/..` → normalizan a `$HOME` o ancestro, denegados).

### 2.5 Storage — archivos

- Cada memoria es un `.md` con frontmatter YAML:
  ```markdown
  ---
  name: {{memory name}}
  description: {{…}}
  type: user|feedback|project|reference
  ---
  {{content}}
  ```
- `MEMORY.md` es el **índice**, no una memoria (`memdir.ts:34`). Una línea por archivo: `- [Title](file.md) — one-line hook`.
- **Límites** `MEMORY.md`: 200 líneas y 25 KB (`memdir.ts:35-38`). Si excede, se trunca en frontera de línea + byte, y se **appendea warning** nombrando la causa (`truncateEntrypointContent`, líneas 57-103).

### 2.6 ¿Cross-references entre tipos?

**No hay mecanismo de cross-ref explícito.** Las memorias son archivos independientes; `MEMORY.md` solo indexa.

Sin embargo, hay **una regla de conflicto cross-scope** para feedback (COMBINED mode): `<description>` de feedback (`memoryTypes.ts:60`): *"Before saving a private feedback memory, check that it doesn't contradict a team feedback memory — if it does, either don't save it or note the override explicitly"*. La resolución es **LLM-in-loop**: el agente extractor debe leer el team memory antes de escribir uno privado que lo contradiga.

### 2.7 ¿Cómo se resuelve conflicto?

Tres mecanismos:

1. **`MEMORY_DRIFT_CAVEAT`** (`memoryTypes.ts:201-202`): *"If a recalled memory conflicts with current information, trust what you observe now — and update or remove the stale memory rather than acting on it"*.
2. **`TRUSTING_RECALL_SECTION`** — header **"Before recommending from memory"** (`memoryTypes.ts:245`). Nota de eval (líneas 242-244): el wording del header fue A/B tested — *"Before recommending" (action cue) went 3/3; the abstract "Trusting what you recall" went 0/3 in-place. Same body text — only the header differed"*. Ejemplo de micro-iteración basada en evals.
   - Cuerpo: verificar paths (ls), verificar funciones/flags (grep) antes de recomendar (líneas 249-251).
3. **`memoryFreshnessText`** (`memoryAge.ts:33-42`): para memorias >1 día, añade system-reminder: *"This memory is {N} days old. Memories are point-in-time observations, not live state — claims about code behavior or file:line citations may be outdated. Verify against current code before asserting as fact."*
   - Motivación (comentarios líneas 27-31): *"user reports of stale code-state memories (file:line citations to code that has since changed) being asserted as fact — the citation makes the stale claim sound more authoritative, not less"*.

### 2.8 `## What NOT to save` — gate explícito (crítico)

`WHAT_NOT_TO_SAVE_SECTION` (`memoryTypes.ts:183-195`). Prohibiciones clave:
- Code patterns, arquitectura, file paths → **derivable** leyendo el proyecto.
- Git history → **autoritativo** vía `git log`/`blame`.
- Debugging solutions → **ya está en el código + commit msg**.
- Ephemeral task details → **no cross-session**.

Última regla (línea 194) — **eval-validada** (comentario líneas 192-193, *"memory-prompt-iteration case 3, 0/2 → 3/3: prevents 'save this week's PR list' → activity-log noise"*):

> *"These exclusions apply even when the user explicitly asks you to save. If they ask you to save a PR list or activity summary, ask what was *surprising* or *non-obvious* about it — that is the part worth keeping."*

**Esta regla hace algo raro e interesante**: niega un pedido explícito del user sin preguntar. Sobrevivió porque la alternativa (guardar todo) contaminaba MEMORY.md con logs de actividad que desplazaban señales valiosas.

### 2.9 Recall: `findRelevantMemories.ts`

Proceso de 3 fases:

1. **Scan frontmatter** (`memoryScan.ts:35-77`, `scanMemoryFiles`): `readdir` recursivo, filtra `.md` no-`MEMORY.md`, lee primeras 30 líneas de cada uno con `readFileInRange` (que devuelve también `mtimeMs`, evitando doble-stat), parsea frontmatter, devuelve ordenado por mtime desc, cap a 200 archivos.
2. **Pre-filter surfaced** (`findRelevantMemories.ts:46-48`): filtra memorias ya mostradas en turnos previos (`alreadySurfaced`) para no gastar los 5 slots en re-picks que el caller va a descartar.
3. **LLM select con Sonnet** (`findRelevantMemories.ts:77-141`, `selectRelevantMemories`):
   - System prompt: `SELECT_MEMORIES_SYSTEM_PROMPT` (líneas 18-24) — le da query + manifest + tools recientes.
   - Usa `sideQuery` (no-conversation, cheap) con `json_schema` strict (líneas 109-118).
   - **Dedup con tools activos** (líneas 87-95): si el user usó `mcp__X__spawn`, no devolver `spawn` docs — son ruido; la conversación ya las contiene. **Excepto** warnings/gotchas de esos tools — ahí es cuando más importan.

---

## 3. `services/SessionMemory/` — Continuidad Intra-Sesión

### 3.1 ¿Qué es session memory vs memdir vs autoDream?

| Propiedad               | `memdir/` (auto-memory)                        | `SessionMemory/`                                      | `autoDream`                   |
|-------------------------|-----------------------------------------------|-------------------------------------------------------|-------------------------------|
| Alcance temporal        | Cross-session, perpetuo                        | Una sesión                                            | Nocturno, destila logs        |
| Formato                 | N archivos `.md` tipados + `MEMORY.md` index   | 1 archivo `summary.md` con template fijo              | Output: files en memdir       |
| Trigger                 | Post-turn (`stopHooks`)                        | Post-sampling, threshold token+tool                   | Cron nightly (KAIROS mode)    |
| Writer                  | main agent O forked extractor (mutex)          | Forked extractor (Edit-only)                          | Forked agent                  |
| Purpose                 | Recall en futuras conversaciones               | Sobrevivir a compaction intra-sesión                  | Distilación periódica de logs |
| Inyección en prompt     | `buildMemoryPrompt` + `findRelevantMemories` en mensajes | Inyectado en compaction (`sessionMemoryCompact.ts`) | Vía memdir recall              |
| Estructura              | Closed taxonomy (4 types) + frontmatter        | Template de 10 secciones prescriptivo                 | N/A                            |
| Permission scope        | `isAutoMemPath` cualquier path bajo memoryDir  | **Solo** `memoryPath` exacto (single file)            | Mismo que memdir              |

### 3.2 ¿Qué guarda en cada session?

Template fijo (`prompts.ts:11-41`, `DEFAULT_SESSION_MEMORY_TEMPLATE`):

```markdown
# Session Title
# Current State
# Task specification
# Files and Functions
# Workflow
# Errors & Corrections
# Codebase and System Documentation
# Learnings
# Key results
# Worklog
```

Las **instrucciones crudas de update** (`prompts.ts:43-81`, `getDefaultUpdatePrompt`) contienen reglas muy estrictas:

- *"NEVER modify, delete, or add section headers"* (línea 57).
- *"NEVER modify or delete the italic _section description_ lines"* (línea 58) — son *template instructions*, no contenido.
- *"ONLY update the actual content that appears BELOW the italic _section descriptions_"* (línea 59).
- *"Always update 'Current State' to reflect the most recent work — this is critical for continuity after compaction"* (línea 69).

### 3.3 ¿Cuándo se crea, actualiza, cierra?

**Creación** (`sessionMemory.ts:183-232`, `setupSessionMemoryFile`):
- `mkdir` con mode `0o700` (owner-only) del dir.
- `writeFile` con flag `'wx'` (= `O_CREAT|O_EXCL`) — atomico, mode `0o600` (línea 197-200).
- Si `EEXIST`, sigue (línea 207-211).
- Primer write mete el template (línea 201-205).
- Lee el contenido actual con `FileReadTool` (línea 217-226) — **purga `readFileState`** antes (línea 215) porque el dedup de FileRead devolvería `file_unchanged` y no el contenido real.

**Actualización** (`sessionMemory.ts:272-350`, `extractSessionMemory`):
- Hook registrado en `initSessionMemory` (línea 374) vía `registerPostSamplingHook`.
- **Solo main thread** — `querySource !== 'repl_main_thread'` returns (línea 278-281).
- Gate `tengu_session_memory` cached (línea 81-82).
- Config lazy-init memoizado desde `tengu_sm_config` (líneas 240-264).
- `shouldExtractMemory` (líneas 134-181) — algoritmo:
  - Si **no inicializada**: requiere `currentTokenCount >= minimumMessageTokensToInit` (default 10000, `sessionMemoryUtils.ts:33`). Una vez alcanzado, `markSessionMemoryInitialized`.
  - Una vez inicializada, extrae cuando: `(hasMetTokenThreshold && hasMetToolCallThreshold) || (hasMetTokenThreshold && !hasToolCallsInLastTurn)`.
  - `hasMetTokenThreshold`: `currentTokenCount - tokensAtLastExtraction >= minimumTokensBetweenUpdate` (default 5000, línea 34).
  - `hasMetToolCallThreshold`: `toolCallsSinceLastUpdate >= toolCallsBetweenUpdates` (default 3, línea 35).
  - **Invariante clave** (líneas 165-167): *"the token threshold is ALWAYS required. Even if the tool call threshold is met, extraction won't happen until the token threshold is also satisfied."*
- Permite también trigger manual vía `/summary` (línea 387 `manuallyExtractSessionMemory`), saltándose thresholds.

**Cierre**: no hay cierre explícito. El archivo persiste en `{projectDir}/{sessionId}/session-memory/summary.md` — una nueva sesión crea nuevo sessionId y nuevo archivo.

### 3.4 ¿Sobrevive a compaction?

**Sí — es su razón de ser.**

- `sessionMemory.ts:361-371` (`initSessionMemory`): *"Session memory is used for compaction, so respect auto-compact settings"* — si `!autoCompactEnabled`, no registra el hook (el módulo se inhabilita).
- Integración con compaction vive en `services/compact/sessionMemoryCompact.ts` (referenciado desde `getSessionMemoryPath` imports en `filesystem.ts:269`). El compactor lee `summary.md` e inserta su contenido como seed del nuevo contexto post-compact.
- `truncateSessionMemoryForCompact` (`prompts.ts:256-324`): trunca secciones que excedan `MAX_SECTION_LENGTH * 4` chars para no consumir entero el budget post-compact.

### 3.5 ¿Cómo se inyecta en el prompt?

- **No se inyecta en cada turno** — el `MEMORY.md` de memdir sí se inyecta en el system prompt; el `summary.md` de SessionMemory **no**.
- Se lee solo cuando ocurre compaction (vía `sessionMemoryCompact.ts`) y se splicea en el nuevo contexto.
- Alternativa: `getSessionMemoryContent` (`sessionMemoryUtils.ts:110-126`) es la API pública para lecturas manuales (ej. desde el comando `/summary`).

### 3.6 ¿Qué lo distingue de memdir?

- **Single file vs many files** — `summary.md` único, vs `N` archivos tipados en memdir.
- **Template-driven (proceso) vs type-driven (contenido)** — summary.md tiene secciones prescritas (Workflow, Errors, Key results…), memdir tiene tipos semánticos (user, feedback, project, reference).
- **Overwrite vs append** — cada update de summary.md **sobrescribe** con Edit; memdir **acumula** archivos nuevos o actualiza por tema.
- **Threshold-triggered vs end-of-loop** — SessionMemory espera tokens y tool calls, memdir corre a cada ciclo de query.
- **Permission scope** — SessionMemory's `createMemoryFileCanUseTool` (`sessionMemory.ts:460-482`) **solo** permite Edit sobre el path exacto; memdir's `createAutoMemCanUseTool` permite Read/Grep/Glob/read-only Bash + Write/Edit dentro del `memoryDir` completo.
- **Thread scope** — SessionMemory corre *solo en main thread* (línea 278-281); memdir corre en main thread pero desde el hook post-stop.
- **Objetivo** — SessionMemory: continuidad en una sesión frente a compaction; memdir: conocimiento cross-sesión.

### 3.7 Config Thresholds

Defaults (`sessionMemoryUtils.ts:32-36`, `DEFAULT_SESSION_MEMORY_CONFIG`):
- `minimumMessageTokensToInit`: **10000**
- `minimumTokensBetweenUpdate`: **5000**
- `toolCallsBetweenUpdates`: **3**

Cargado vía `tengu_sm_config` dynamic config con override parcial (`sessionMemory.ts:243-263`) — **solo overriding si valor remoto > 0** (línea 249) para evitar que un valor cero accidental rompa defaults.

Budget de contenido:
- Per-section: `MAX_SECTION_LENGTH = 2000` tokens (`prompts.ts:8`).
- Total: `MAX_TOTAL_SESSION_MEMORY_TOKENS = 12000` (línea 9).
- Warnings inyectados al prompt de update si se exceden (`generateSectionReminders`, líneas 164-196) — el LLM recibe: `"'Worklog' is ~2847 tokens (limit: 2000)"` y actúa como compactador.

---

## 4. Cruce con Clonnect

### 4.1 Inventario — equivalentes en Clonnect

| CC                            | Clonnect equivalente                                                  |
|-------------------------------|-----------------------------------------------------------------------|
| `extractMemories/`            | `services/memory_engine.py` (extracción fact-level)                   |
|                               | `services/memory_extraction.py`                                       |
|                               | `services/memory_consolidation_llm.py`                                |
| `memdir/` (typed files)       | **Ninguna equivalencia directa**. Clonnect tiene:                     |
|                               | • `services/memory_service.py:FollowerMemory` (fields, not types)     |
|                               | • `services/memory_engine.py:MemoryEngine` (per-lead + pgvector)      |
|                               | • `core/hierarchical_memory/hierarchical_memory.py` (3-level IMPersona)|
| `SessionMemory/`              | **Ninguna equivalencia directa.** Clonnect NO tiene continuidad       |
|                               | intra-conversación estructurada. El contexto se reconstruye de DB.    |
| `findRelevantMemories.ts`     | `MemoryEngine.search()` + `recall()` (pgvector ANN, sin LLM re-rank)  |
| `MEMORY.md` index             | No aplica (Clonnect es multi-lead, no monolito)                       |
| `autoDream`                   | Parcialmente: `services/memory_consolidator.py`, `memory_consolidation_ops.py` |

### 4.2 ¿Cómo difiere la implementación?

**Clonnect = multi-tenant, DB-native, per-lead:**
- Cada lead tiene su propio `FollowerMemory` (dataclass) en `services/memory_service.py:18-95`, persistido en JSON por creator+follower (`_get_file_path`, líneas 187-193).
- `MemoryStore` caches con `BoundedTTLCache(max_size=500, ttl=600s)` (línea 180) — útil a escala.
- Facts en pgvector (`ENABLE_MEMORY_ENGINE`, `memory_engine.py:35`).
- Ebbinghaus decay sobre facts (`ENABLE_MEMORY_DECAY`, `memory_engine.py:36`).
- i18n: `ConversationMemoryService` tiene regex hardcoded en español (`memory_service.py:331-346` — `ya te (lo )?dije`, `como te comenté`, etc.). Ruptura: no es portable a otros idiomas sin redefinir patrones.

**CC = single-developer, FS-native, cross-repo:**
- Memoria única por (user, git-root). No hay multi-tenancy real — cada repo es su propio silo.
- Archivos `.md` humanos editables directamente (gran ventaja UX: user inspecciona y edita sin dashboard).
- LLM decide qué es relevante via `findRelevantMemories` (Sonnet re-rank post scan).
- No hay decay numérico — en su lugar: `memoryFreshnessText` (warning text) + `TRUSTING_RECALL_SECTION` (verify before recommend). **Decay lingüístico, no aritmético.**

### 4.3 Patrones de CC aplicables a Clonnect

**A. `hasMemoryWritesSince` — single-writer mutex**
- CC (`extractMemories.ts:121-148`): si el main agent ya escribió en `memoryDir` esta turno, el forked extractor **se salta** esa ventana y avanza el cursor.
- Clonnect: `MemoryStore` y `ConversationMemoryService` pueden escribir al mismo lead SIMULTÁNEAMENTE desde `bot_orchestrator` + background task. El *Dual Memory Storage Conflict* (`GRAPH_REPORT.md:54`) es exactamente este problema.
- **Acción:** introducir un cursor compartido (ej. `lead_memories.last_writer`) o un lock *per-lead* que marque quién está escribiendo. El orden debe ser: `MemoryEngine.add()` **o** `ConversationMemoryService.save()`, nunca los dos en la misma tanda.

**B. Frontmatter + manifest pattern para recall escalable**
- CC (`memoryScan.ts:35-77`): lee solo frontmatter (30 líneas, `FRONTMATTER_MAX_LINES=23`) → construye manifest → Sonnet selecciona top-5 → `findRelevantMemories.ts:39-75`.
- Clonnect: `MemoryEngine.recall()` devuelve hits de pgvector directamente, sin re-rank LLM.
- **Acción:** para leads con >50 facts, añadir un paso LLM re-rank entre pgvector recall (N=20) y prompt injection (N=5). Ahorro: evitar inyectar facts con keyword overlap pero baja utilidad semántica.

**C. `memoryFreshnessText` — drift awareness**
- CC (`memoryAge.ts:33-42`): toda memoria > 1 día lleva system-reminder *"Memories are point-in-time observations, not live state..."*.
- Clonnect: los facts viejos se inyectan sin ningún warning. Un fact de hace 3 meses aparece igual que uno de ayer.
- **Acción:** envolver facts con `created_at > 30 días` en system-reminder corto: *"Este recuerdo es de hace X días. Verifica si sigue siendo cierto antes de afirmarlo."*

**D. Closed taxonomy — decisión crítica de producto**
- CC fija 4 tipos (`memoryTypes.ts:14-19`). El modelo no puede inventar tipos nuevos.
- Clonnect: `FollowerMemory` tiene ~20 campos sueltos (interests, objections, products_discussed, …). No hay estructura jerárquica.
- **Acción:** definir taxonomía cerrada Clonnect, por ej.:
  - `interest` (producto/tema que atrae al lead)
  - `objection` (bloqueo) — ya existe
  - `intent_signal` (pregunta de precio, intención de compra)
  - `identity` (nombre, ubicación, PII)
  - `relationship_state` (cliente, customer, lead hot)
  - Cada uno con `<body_structure>` (el fact + **Why** inferencial + **How to apply**).

**E. Two-step save: file + index**
- CC exige que cada save sea `write(file)` + update `MEMORY.md` (`prompts.ts:68-82`).
- Clonnect: facts van a pgvector pero no hay "índice humano" para el creator.
- **Acción parcial:** exponer un dashboard con un `MEMORY.md`-equivalente por creator, navegable. Ortogonal al fix pero aumenta trust.

**F. Eval-driven prompt header wording**
- `TRUSTING_RECALL_SECTION` comentarios (`memoryTypes.ts:242-244`): el header wording se A/B testó — *"Before recommending" → 3/3; "Trusting what you recall" → 0/3*.
- Clonnect: los prompts de memoria no tienen historial de eval wording. Cambios ad-hoc.
- **Acción:** adoptar `eval/` regression suite para prompt edits. El wording del header matters — evaluar antes de commit.

### 4.4 Patrones que NO aplican (y por qué)

1. **Forked-agent pattern (`runForkedAgent`)** — CC es TS/Bun runtime con REPL persistente. Clonnect es FastAPI stateless (webhook → orchestrator). No hay "conversación viva" que forkear. Se resuelve vía background tasks (Celery/asyncio to_thread) — semántica distinta.

2. **`~/.claude/projects/.../memory/` FS storage** — Clonnect tiene ~1000 leads por creator a escala. FS no escala (inodo explosion, backups, GDPR erasure). pgvector + `lead_memories` table es correcto para Clonnect.

3. **`MEMORY.md` siempre inyectado en system prompt** — CC es single-user, single-context. Inyectar el índice completo es barato. Clonnect es multi-lead, multi-creator; el system prompt es per-lead. Lo que aplica es el PATRÓN (pequeño index estable + deep dive on demand), no el artefacto.

4. **4-type taxonomy `{user, feedback, project, reference}`** — son categorías de "dev assistant". Clonnect necesita categorías de "follower engagement" (ver 4.3.D).

5. **Git-root-scoped paths** — Clonnect es un backend global, no per-repo. `creator_id` es el tenant natural.

6. **`tengu_*` GrowthBook flags para throttling** — Clonnect usa env vars (`ENABLE_MEMORY_ENGINE`, `ENABLE_MEMORY_DECAY`). Funcionalmente equivalente; no hace falta migrar a GrowthBook.

### 4.5 *Dual Memory Storage Conflict* — análisis y solución

**El problema en Clonnect** (`graphify-out/GRAPH_REPORT.md:54`):

> *"Dual Memory Storage Conflict (MemoryStore vs ConversationMemoryService) — memory_store, conversation_memory_service, sys33_follower_memory [EXTRACTED 1.00]"*

**Ownership actual (ambiguo):**

| Concern                     | `MemoryStore` (memory_service.py:162)     | `ConversationMemoryService` (memory_service.py:327) |
|-----------------------------|-------------------------------------------|-----------------------------------------------------|
| Storage                     | JSON files `data/followers/`              | DB-first (`lead_memories`) + JSON fallback          |
| Cache                       | `BoundedTTLCache` (500, 600s)             | Ninguno                                             |
| Fields                      | interests, objections, products, scoring, greeting_variant | ConversationFact(s) + regex-detected refs     |
| Language                    | Agnóstico                                 | Hardcoded español (líneas 331-367)                  |
| Written by                  | `bot_orchestrator`, `lead_scoring`         | `dm_agent_v2`, `post_response`                      |
| Lifecycle                   | Whole-object overwrite                    | Append facts + update active flag                   |

**Solape:** ambos guardan "qué dijo este lead". `FollowerMemory.last_messages` (líneas 40-43) solapa con `ConversationFact` de tipo conversational — duplicación de contenido con semántica distinta.

**¿Cómo CC evita este problema?**

1. **Scope separation clara por artefacto:**
   - Cross-session knowledge → `memdir/` (archivo típico)
   - Within-session continuity → `SessionMemory/` (archivo summary)
   - Nightly distillation → `autoDream`
   - Todos PATH-disjuntos y permission-isolated.

2. **Single writer enforcement por scope:**
   - memdir: `hasMemoryWritesSince` bloquea al extractor si el main ya escribió (extractMemories.ts:121-148).
   - SessionMemory: solo el post-sampling hook escribe, y solo en main thread (sessionMemory.ts:278-281).
   - El fork usa canUseTool ultra-restringida — no puede siquiera escribir fuera del artefacto que le corresponde.

3. **Prompt cache sharing como selector natural:**
   - `runForkedAgent` exige mismo prefix → solo puede haber UNA extracción coherente por fork. Coalescing (pendingContext) + trailing run asegura que los intentos concurrentes colapsan a uno.

**Recomendación Clonnect:**

Definir ownership por concern, no por servicio:

| Concern                           | Owner propuesto                                 |
|-----------------------------------|-------------------------------------------------|
| Últimos N mensajes del lead (window) | `FollowerMemory.last_messages` (en-memory cache, lifetime = conversación activa) |
| Facts extraídos (long-term)       | `MemoryEngine` → `lead_memories` table (pgvector) |
| Estado de relación/scoring        | `FollowerMemory` DB-persisted                   |
| Conflict/past-ref detection (ES)  | **BORRAR** `ConversationMemoryService` — mover detección de past-refs a un signal detector en `memory_engine` que anota facts con `is_past_reference: bool` |
| Cache de acceso rápido            | `MemoryStore.BoundedTTLCache` mantener, solo para DB hits |

**Beneficio:** una sola fuente de verdad por concern → no hay dual storage, no hay sync bugs, no hay race conditions entre MemoryStore.save y ConversationMemoryService.save sobre el mismo lead.

**Riesgo de la propuesta:** `ConversationMemoryService` tiene lógica de regex ES útil; moverla sin pérdida requiere test coverage previo (ver `tests/test_memory_engine_bugs.py`).

### 4.6 Handoff i18n (Sprint 3) — qué aprender de CC

**Fix reciente** (commit `8ae594f9`): *"i18n bug — MEMO_COMPRESSION_PROMPT generates memo in language of lead facts"*.

**Lo que CC enseña sobre i18n:**
- El prompt de extracción CC está TODO en inglés (`extractMemories/prompts.ts:29-44`; `memoryTypes.ts` entero).
- Pero las memorias escritas salen **en el idioma del contexto** — porque el fork comparte el system prompt + message prefix del main agent.
- **Inferencia:** el modelo alinea idioma al CONTEXTO dominante, no a la INSTRUCCIÓN. Forzar `"write in X"` es a menudo contraproducente — genera respuestas ligeramente artificiales.
- **Validación:** el handoff Sprint 3 soluciona el mismo problema fundamentando el prompt en el contenido (facts en lang L → memo en lang L), no con un flag de idioma.

**Regla derivada para Clonnect:**
- Prompts de compresión/extracción/memoria NO deben tener "respond in Spanish" hardcoded.
- Deben operar sobre el contenido que les pasas; si el contenido está en ES, el output será ES.
- Si necesitas garantía de idioma (ej. para un creator multilingüe con leads en 3 idiomas), pasa la directiva junto a la señal de idioma **extraída del contenido**, no como constante del prompt.

---

## 5. Apéndice — Tabla de dependencias CC-memory

```
extractMemories.ts
  ├─ memdir/memdir.ts       (ENTRYPOINT_NAME, DIR_EXISTS_GUIDANCE)
  ├─ memdir/memoryScan.ts   (scanMemoryFiles, formatMemoryManifest)
  ├─ memdir/paths.ts        (getAutoMemPath, isAutoMemoryEnabled, isAutoMemPath)
  ├─ memdir/teamMemPaths.ts (feature('TEAMMEM') only)
  └─ extractMemories/prompts.ts
       ├─ memdir/memoryTypes.ts (TYPES_SECTION_*, WHAT_NOT_TO_SAVE_SECTION, MEMORY_FRONTMATTER_EXAMPLE)

memdir/memdir.ts
  ├─ memdir/paths.ts
  ├─ memdir/memoryTypes.ts
  │    └─ (leaves, no deps)
  └─ memdir/teamMemPrompts.ts (TEAMMEM only)

memdir/findRelevantMemories.ts
  ├─ memdir/memoryScan.ts
  └─ utils/sideQuery.ts (LLM Sonnet select)

SessionMemory/sessionMemory.ts
  ├─ SessionMemory/prompts.ts (template + update prompt)
  ├─ SessionMemory/sessionMemoryUtils.ts (config, thresholds, state)
  ├─ utils/permissions/filesystem.ts (getSessionMemoryPath, getSessionMemoryDir)
  ├─ utils/forkedAgent.ts (runForkedAgent)
  └─ utils/hooks/postSamplingHooks.ts (registerPostSamplingHook)

stopHooks.ts:149  ──fires──►  extractMemories.executeExtractMemories
setup.ts:294      ──init──►   initSessionMemory  ──registers──►  postSamplingHook
print.ts:968      ──drain──►  extractMemories.drainPendingExtraction
backgroundHousekeeping.ts:35 ─init──► initExtractMemories
```

---

## 6. Citas completas — índice

- **Trigger wiring:**
  - `src/query/stopHooks.ts:149` — dispara `executeExtractMemories`
  - `src/setup.ts:294` — llama `initSessionMemory`
  - `src/utils/backgroundHousekeeping.ts:35` — llama `initExtractMemories`
  - `src/cli/print.ts:968` — llama `drainPendingExtraction`
- **Gates:**
  - `src/memdir/paths.ts:30-55` — `isAutoMemoryEnabled`
  - `src/memdir/paths.ts:69-77` — `isExtractModeActive`
  - `src/services/SessionMemory/sessionMemory.ts:80-82` — `isSessionMemoryGateEnabled` (`tengu_session_memory`)
  - `src/services/extractMemories/extractMemories.ts:536` — `tengu_passport_quail`
  - `src/services/extractMemories/extractMemories.ts:381` — `tengu_bramble_lintel`
- **Taxonomía:**
  - `src/memdir/memoryTypes.ts:14-19` — `MEMORY_TYPES`
  - `src/memdir/memoryTypes.ts:28-31` — `parseMemoryType`
  - `src/memdir/memoryTypes.ts:37-106` — `TYPES_SECTION_COMBINED`
  - `src/memdir/memoryTypes.ts:113-178` — `TYPES_SECTION_INDIVIDUAL`
  - `src/memdir/memoryTypes.ts:183-195` — `WHAT_NOT_TO_SAVE_SECTION`
  - `src/memdir/memoryTypes.ts:201-202` — `MEMORY_DRIFT_CAVEAT`
  - `src/memdir/memoryTypes.ts:216-222` — `WHEN_TO_ACCESS_SECTION`
  - `src/memdir/memoryTypes.ts:240-256` — `TRUSTING_RECALL_SECTION`
  - `src/memdir/memoryTypes.ts:261-271` — `MEMORY_FRONTMATTER_EXAMPLE`
- **Paths & security:**
  - `src/memdir/paths.ts:85-90` — `getMemoryBaseDir`
  - `src/memdir/paths.ts:109-150` — `validateMemoryPath` (SEC)
  - `src/memdir/paths.ts:161-166` — `getAutoMemPathOverride` (Cowork env)
  - `src/memdir/paths.ts:179-186` — `getAutoMemPathSetting` (settings.json, sin projectSettings)
  - `src/memdir/paths.ts:223-235` — `getAutoMemPath`
  - `src/memdir/paths.ts:274-278` — `isAutoMemPath`
  - `src/utils/permissions/filesystem.ts:261-263` — `getSessionMemoryDir`
  - `src/utils/permissions/filesystem.ts:269-271` — `getSessionMemoryPath`
- **Extraction internals:**
  - `src/services/extractMemories/extractMemories.ts:121-148` — `hasMemoryWritesSince` (mutex)
  - `src/services/extractMemories/extractMemories.ts:171-222` — `createAutoMemCanUseTool`
  - `src/services/extractMemories/extractMemories.ts:251-269` — `extractWrittenPaths`
  - `src/services/extractMemories/extractMemories.ts:296-587` — `initExtractMemories` (closure)
  - `src/services/extractMemories/extractMemories.ts:329-523` — `runExtraction`
  - `src/services/extractMemories/extractMemories.ts:415-427` — `runForkedAgent` call
  - `src/services/extractMemories/extractMemories.ts:473-485` — telemetry `tengu_extract_memories_extraction`
- **Session memory internals:**
  - `src/services/SessionMemory/sessionMemory.ts:134-181` — `shouldExtractMemory`
  - `src/services/SessionMemory/sessionMemory.ts:183-232` — `setupSessionMemoryFile`
  - `src/services/SessionMemory/sessionMemory.ts:272-350` — `extractSessionMemory`
  - `src/services/SessionMemory/sessionMemory.ts:357-375` — `initSessionMemory`
  - `src/services/SessionMemory/sessionMemory.ts:460-482` — `createMemoryFileCanUseTool`
  - `src/services/SessionMemory/sessionMemoryUtils.ts:32-36` — `DEFAULT_SESSION_MEMORY_CONFIG`
  - `src/services/SessionMemory/prompts.ts:11-41` — `DEFAULT_SESSION_MEMORY_TEMPLATE`
  - `src/services/SessionMemory/prompts.ts:43-81` — `getDefaultUpdatePrompt`
  - `src/services/SessionMemory/prompts.ts:256-324` — `truncateSessionMemoryForCompact`
- **Recall:**
  - `src/memdir/findRelevantMemories.ts:18-24` — `SELECT_MEMORIES_SYSTEM_PROMPT`
  - `src/memdir/findRelevantMemories.ts:39-75` — `findRelevantMemories`
  - `src/memdir/findRelevantMemories.ts:77-141` — `selectRelevantMemories`
  - `src/memdir/memoryScan.ts:35-77` — `scanMemoryFiles`
  - `src/memdir/memoryScan.ts:84-94` — `formatMemoryManifest`
  - `src/memdir/memoryAge.ts:33-42` — `memoryFreshnessText`
- **Build memory prompt:**
  - `src/memdir/memdir.ts:57-103` — `truncateEntrypointContent`
  - `src/memdir/memdir.ts:129-147` — `ensureMemoryDirExists`
  - `src/memdir/memdir.ts:199-266` — `buildMemoryLines`
  - `src/memdir/memdir.ts:272-316` — `buildMemoryPrompt`
  - `src/memdir/memdir.ts:327-370` — `buildAssistantDailyLogPrompt` (KAIROS)
  - `src/memdir/memdir.ts:375-407` — `buildSearchingPastContextSection`
  - `src/memdir/memdir.ts:419-507` — `loadMemoryPrompt`
- **Clonnect refs (para cross-ref):**
  - `services/memory_service.py:18-95` — `FollowerMemory` dataclass
  - `services/memory_service.py:162-314` — `MemoryStore`
  - `services/memory_service.py:327+` — `ConversationMemoryService`
  - `services/memory_engine.py:157+` — `MemoryEngine`
  - `core/hierarchical_memory/hierarchical_memory.py` — 3-level IMPersona
  - `core/memory.py:1-30` — DEPRECATED marker
  - `graphify-out/GRAPH_REPORT.md:54` — Dual Memory Storage Conflict flag
