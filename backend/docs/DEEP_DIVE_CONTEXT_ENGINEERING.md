# Claude Code Context Engineering — Deep Dive

## 1. query.ts — Main Loop

### Primary Exported Function

**Function signature** (lines 218–238):
```typescript
export async function* query(
  params: QueryParams,
): AsyncGenerator<
  | StreamEvent
  | RequestStartEvent
  | Message
  | TombstoneMessage
  | ToolUseSummaryMessage,
  Terminal
>
```

This is an async generator function. The inner implementation is `queryLoop`, which implements the actual while-loop.

### QueryParams (type definition at lines 180–198)

```typescript
type QueryParams = {
  messages: Message[]
  systemPrompt: SystemPrompt
  userContext: { [k: string]: string }
  systemContext: { [k: string]: string }
  canUseTool: CanUseToolFn
  toolUseContext: ToolUseContext
  fallbackModel?: string
  querySource: QuerySource
  maxOutputTokensOverride?: number
  maxTurns?: number
  skipCacheWrite?: boolean
  taskBudget?: { total: number }
  deps?: QueryDeps
}
```

### Loop Entry Point and State Management

**Main loop** (line 306): `while (true)` with mutable `state` object reassigned at continue sites.

**State structure** (lines 203–216):
```typescript
type State = {
  messages: Message[]
  toolUseContext: ToolUseContext
  autoCompactTracking: AutoCompactTrackingState | undefined
  maxOutputTokensRecoveryCount: number
  hasAttemptedReactiveCompact: boolean
  maxOutputTokensOverride: number | undefined
  pendingToolUseSummary: Promise<ToolUseSummaryMessage | null> | undefined
  stopHookActive: boolean | undefined
  turnCount: number
  transition: Continue | undefined
}
```

**Initial state** (lines 267–278): Initialized with params.messages, maxOutputTokensOverride, turnCount=1, and other tracking fields.

### Loop Flow — Step by Step

#### [1] User Input Processing (lines 336–363)

1. **Stream request start signal** (line 336): `yield { type: 'stream_request_start' }`
2. **Query tracking initialization** (lines 346–362): Increments queryTracking.depth or creates new chainId
3. **Async skill prefetch** (lines 330–334): Non-blocking prefetch that runs during model streaming

#### [2] Message Filtering and Content Transformation (lines 364–425)

1. **getMessagesAfterCompactBoundary** (line 364): Filters to messages after last compact boundary
2. **Tool result size budget enforcement** (lines 378–393): `applyToolResultBudget()` with content replacement
3. **History snip** (lines 400–409): Optional snip compaction if feature enabled
4. **Microcompact** (lines 413–425): Optional prompt cache editing via `deps.microcompact()`
5. **Context collapse** (lines 439–446): Optional context collapse if enabled

#### [3] Auto-Compaction Decision (lines 448–543)

1. **System prompt assembly** (lines 448–450):
   ```typescript
   const fullSystemPrompt = asSystemPrompt(
     appendSystemContext(systemPrompt, systemContext),
   )
   ```

2. **Auto-compact trigger** (lines 453–466): Calls `deps.autocompact()` with:
   - Current messages
   - toolUseContext
   - cacheSafeParams (systemPrompt, userContext, systemContext, toolUseContext, forkContextMessages)
   - querySource and tracking state

3. **Compaction result processing** (lines 469–543):
   - Token counting and analytics logging (lines 477–502)
   - Task budget carryover calculation (lines 508–515)
   - Reset tracking state (lines 521–526)
   - Yield post-compact boundary messages (lines 530–532)
   - Update messagesForQuery (line 535)

#### [4] Token Budget and Blocking Limit Check (lines 628–648)

1. **Hoists reactive-compact and context-collapse gates** (lines 616–620)
2. **Skips synthetic preempt** if reactive-compact or context-collapse can handle it
3. **Calls `calculateTokenWarningState()`** (line 637) to check `isAtBlockingLimit`
4. **Returns error** if blocking limit hit (lines 642–646)

#### [5] Model Streaming Loop (lines 653–863)

**Wrapper**: `while (attemptWithFallback)` for fallback model retry.

**Inner streaming** (lines 659–863): `for await (const message of deps.callModel({...}))`:

1. **Streaming fallback detection** (lines 712–741): If streaming falls back to different model, discard previous assistant/tool messages
2. **Message assembly** (lines 747–787): For each streamed message:
   - Clone for legacy/observable input backfill (lines 747–786)
   - Check for recoverable errors (withheld prompt-too-long, max-output-tokens, media-size) (lines 799–822)
   - Yield if not withheld (line 824)
   - Push to `assistantMessages` if type==='assistant' (line 827)
   - Collect tool_use blocks (lines 829–834)
   - Add to streaming tool executor if available (lines 838–844)

3. **Streaming tool results collection** (lines 847–862): Drain completed results from executor

4. **Microcompact boundary emission** (lines 870–892): Yield deferred cache_deleted_input_tokens

#### [6] Post-Sampling Hooks (lines 1000–1009)

```typescript
if (assistantMessages.length > 0) {
  void executePostSamplingHooks(
    [...messagesForQuery, ...assistantMessages],
    systemPrompt,
    userContext,
    systemContext,
    toolUseContext,
    querySource,
  )
}
```

Fires asynchronously (not awaited) — extractMemory, skillImprovement, magicDocs hooks.

#### [7] Abort Handling (lines 1015–1052)

1. **Check abort signal** (line 1015)
2. **Drain remaining tool results** from streaming executor (lines 1019–1023)
3. **Emit tool-result error** or interruption message (lines 1025–1050)
4. **Chicago MCP cleanup** (lines 1033–1041)
5. **Return** with reason='aborted_streaming' (line 1051)

#### [8] Tool Summary Generation (lines 1054–1482)

1. **Yield pending tool summary** from prior turn (lines 1055–1060)
2. **Check `needsFollowUp`** (if false, exit to completion path; if true, execute tools)
3. **Generate next summary** (lines 1415–1481): Non-blocking Haiku call via `generateToolUseSummary()`

#### [9] No Follow-Up Path — Stop Hooks and Completion (lines 1062–1358)

**When no tool_use blocks are present:**

1. **Prompt-too-long recovery** (lines 1070–1117):
   - Drain context-collapse staged collapses if available (lines 1089–1117)
   - Retry with collapse_drain_retry transition

2. **Reactive-compact recovery** (lines 1119–1183):
   - Call `reactiveCompact.tryReactiveCompact()` (lines 1120–1132)
   - Yield post-compact messages (lines 1148–1151)
   - Transition to reactive_compact_retry or surface error (lines 1152–1182)

3. **Max-output-tokens recovery** (lines 1188–1256):
   - **Escalating retry** (lines 1195–1221): Retry with ESCALATED_MAX_TOKENS if override not set
   - **Multi-turn recovery** (lines 1223–1252): Inject recovery message, transition to max_output_tokens_recovery
   - **Exhaustion** (lines 1254–1256): Surface error

4. **Stop Hooks** (lines 1267–1276):
   - Call `handleStopHooks()` (line 1267)
   - Check `preventContinuation` flag (lines 1278–1280)
   - Handle blocking errors (lines 1282–1306)

5. **Token Budget Check** (lines 1308–1355):
   - Check `budgetTracker.checkTokenBudget()`
   - Decision: 'continue' → auto-continuation nudge message
   - Decision: 'completionEvent' → emit event, possibly early stop for diminishing returns

6. **Completion** (line 1357): Return `{ reason: 'completed' }`

#### [10] Tool Execution Path (lines 1360–1727)

**When tool_use blocks are present:**

1. **Tool execution** (lines 1366–1409):
   - Log streaming vs. non-streaming executor choice (lines 1367–1378)
   - Iterate tool results (lines 1384–1408)
   - Detect hook_stopped_continuation (lines 1388–1393)
   - Normalize to API messages (lines 1395–1400)
   - Update toolUseContext from results (lines 1402–1407)

2. **Post-tool-batch attachments** (lines 1547–1628):
   - Drain queued commands (lines 1570–1578)
   - Call `getAttachmentMessages()` (lines 1580–1590): Inserts memory, skill attachments, command attachments
   - Consume memory prefetch if settled (lines 1599–1614)
   - Inject skill discovery prefetch (lines 1620–1628)
   - Remove consumed commands from queue (lines 1632–1643)

3. **Tool refresh** (lines 1660–1671): Refresh MCP tool list if configured

4. **Turn increment and max-turns check** (lines 1679–1712):
   - Increment turnCount (line 1679)
   - Check maxTurns limit (lines 1705–1712)

5. **Recursive transition** (lines 1715–1727):
   - Build new State with accumulated messages
   - Reset recovery counts, maxOutputTokensOverride
   - Pass through tracking and transition info
   - `state = next; continue` (line 1727) → jumps to top of while loop

### Key Imports

- `query` from this file is the main entry point (exported async generator)
- `callModel` via `deps.callModel()` — routes to API in src/services/api/claude.ts
- `getAttachmentMessages()` from `./utils/attachments.js` — on-demand attachment injection
- `prependUserContext()`, `appendSystemContext()` from `./utils/api.js` — context wrapping
- `executePostSamplingHooks()` from `./utils/hooks/postSamplingHooks.js` — post-LLM hooks
- `handleStopHooks()` from `./query/stopHooks.js` — stop-hook evaluation
- `autocompact()`, `microcompact()` via `deps` — compaction services

### Loop Exit Points

- Thrown errors → error propagated
- `.return()` on generator → cleanup (notifyCommandLifecycle)
- Early `return { reason: ... }` statements:
  - `'blocking_limit'` (line 646)
  - `'image_error'` (line 977)
  - `'model_error'` (line 996)
  - `'aborted_streaming'` (line 1051)
  - `'aborted_tools'` (line 1515)
  - `'hook_stopped'` (line 1520)
  - `'prompt_too_long'` (lines 1175, 1182)
  - `'collapse_drain_retry'` / `'reactive_compact_retry'` / `'max_output_tokens_*'` (continue, not return)
  - `'completed'` (line 1357)
  - `'max_turns'` (line 1711)

---

## 2. QueryEngine.ts — Engine

### Primary Class

**`QueryEngine`** (lines 183–1177):
- Constructor (lines 199–206): Accepts `QueryEngineConfig`, initializes mutableMessages, abortController, permissionDenials, readFileState, totalUsage
- Public async generator `submitMessage()` (lines 208–1156): Yields `SDKMessage` (SDK-normalized output)
- Helper methods: `interrupt()`, `getMessages()`, `getReadFileState()`, `getSessionId()`, `setModel()`

**Convenience wrapper: `ask()`** (lines 1186–1295): Creates a QueryEngine, calls submitMessage(), yields SDKMessage

### QueryEngineConfig (type at lines 129–172)

Critical configuration:
- `cwd`, `tools`, `commands`, `mcpClients`, `agents`, `canUseTool`, `getAppState`, `setAppState`
- `initialMessages`, `readFileCache`, `customSystemPrompt`, `appendSystemPrompt`
- `userSpecifiedModel`, `fallbackModel`, `thinkingConfig`, `maxTurns`, `maxBudgetUsd`, `taskBudget`
- `jsonSchema` for structured output
- `snipReplay` callback (SDK-only, injected for HISTORY_SNIP feature)

### submitMessage() Entry and Setup (lines 208–556)

#### Phase 1: System Prompt Construction (lines 283–324)

1. **Fetch system prompt parts** (lines 287–299):
   ```typescript
   const {
     defaultSystemPrompt,
     userContext: baseUserContext,
     systemContext,
   } = await fetchSystemPromptParts({...})
   ```
   - Source: `src/utils/queryContext.js`
   - Combines default system prompt + tool descriptions

2. **Memory mechanics injection** (lines 315–318):
   ```typescript
   const memoryMechanicsPrompt = customPrompt && hasAutoMemPathOverride()
     ? await loadMemoryPrompt()
     : null
   ```

3. **Final system prompt assembly** (lines 320–324):
   ```typescript
   const systemPrompt = asSystemPrompt([
     ...(customPrompt ? [customPrompt] : defaultSystemPrompt),
     ...(memoryMechanicsPrompt ? [memoryMechanicsPrompt] : []),
     ...(appendSystemPrompt ? [appendSystemPrompt] : []),
   ])
   ```

#### Phase 2: User Input Processing (lines 334–461)

1. **Create ProcessUserInputContext** (lines 334–394):
   - `messages`, `setMessages`, `options` (tools, model, commands, etc.)
   - `getAppState`, `setAppState`, `abortController`
   - `readFileState`, `nestedMemoryAttachmentTriggers`, `loadedNestedMemoryPaths`, etc.

2. **Process user input** (lines 409–427):
   ```typescript
   const {
     messages: messagesFromUserInput,
     shouldQuery,
     allowedTools,
     model: modelFromUserInput,
     resultText,
   } = await processUserInput({...})
   ```
   - Source: `src/utils/processUserInput/processUserInput.js`
   - Extracts @-mentions, processes slash commands, builds user message

3. **Persist to transcript** (lines 449–462):
   ```typescript
   if (persistSession && messagesFromUserInput.length > 0) {
     const transcriptPromise = recordTranscript(messages)
     // Fire-and-forget in bare mode, await otherwise
   }
   ```

4. **Prepare replay messages** (lines 465–473):
   ```typescript
   const replayableMessages = messagesFromUserInput.filter(msg =>
     (msg.type === 'user' && ...) || (msg.type === 'system' && msg.subtype === 'compact_boundary')
   )
   ```

#### Phase 3: Query Invocation (lines 675–686)

```typescript
for await (const message of query({
  messages,
  systemPrompt,
  userContext,
  systemContext,
  canUseTool: wrappedCanUseTool,
  toolUseContext: processUserInputContext,
  fallbackModel,
  querySource: 'sdk',
  maxTurns,
  taskBudget,
}))
```

**Key point**: `toolUseContext` here is the ProcessUserInputContext (contains tools, options, getAppState, etc.)

### Message Normalization and Transcription (lines 688–750)

**For each message from query**:

1. **Record to transcript** (lines 717–731): Fire-and-forget for assistant, await for user/boundary
2. **Acknowledge initial messages** (lines 735–750): If replayUserMessages, emit SDKUserMessageReplay

### Message Type Dispatch (lines 757–968)

Switch over `message.type`:

- **'assistant'**: Push to mutableMessages, emit normalizeMessage(), capture stop_reason
- **'progress'**: Push and record inline, emit normalizeMessage()
- **'user'**: Push and emit normalizeMessage()
- **'stream_event'**: Update currentMessageUsage, accumulate on message_stop
- **'attachment'**: Push, record inline, extract structured_output, handle max_turns_reached, emit queued_command replays
- **'system'**: Handle snip boundary replay, emit compact_boundary, handle api_retry
- **'tool_use_summary'**: Emit as SDK message
- **'stream_request_start'**: No-op (control signal only)
- **'tombstone'**: No-op (message removal signal)

### Budget and Limit Checks (lines 971–1048)

- **USD budget exceeded** (lines 972–1002): Yield error result and return
- **Structured output retry limit** (lines 1005–1048): Yield error result and return

### Final Result Emission (lines 1058–1155)

1. **Extract result message** (line 1058): Find last assistant or user message
2. **Flush transcript** (lines 1073–1080): Await flushSessionStorage
3. **Check result success** (line 1082): `isResultSuccessful(result, lastStopReason)`
4. **Yield result** (lines 1083–1155): Either error_during_execution or success
   - Success includes: `textResult`, `stop_reason`, `usage`, `structured_output`, `permission_denials`

### User Context Injection

**Location**: `api.ts:prependUserContext()` (lines 449–474)

**Applied in query.ts**:
```typescript
messages: prependUserContext(messagesForQuery, userContext),
```

**Mechanism**:
- Creates synthetic user message with `<system-reminder>` block
- Injects `# key\nvalue` pairs for each userContext entry
- Marked as `isMeta: true`
- Prepended to messages array (first element)
- Bypassed in NODE_ENV=test or if context is empty

### System Context Injection

**Location**: `api.ts:appendSystemContext()` (lines 437–447)

**Applied in query.ts**:
```typescript
const fullSystemPrompt = asSystemPrompt(
  appendSystemContext(systemPrompt, systemContext),
)
```

**Mechanism**:
- Appends `key: value` entries to systemPrompt array
- Joins with newline
- Filters out empty entries
- Returns new systemPrompt array

### Post-Sampling Hooks

Called in **query.ts:1000–1009**:
```typescript
void executePostSamplingHooks(
  [...messagesForQuery, ...assistantMessages],
  systemPrompt,
  userContext,
  systemContext,
  toolUseContext,
  querySource,
)
```

**Fire-and-forget** — does not block query loop continuation.

---

## 3. attachments.ts — On-Demand Injection

### Primary Function

**`getAttachments()`** (lines 742–1003):
```typescript
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

**Called from**: `query.ts:getAttachmentMessages()` (line 1580)

**Scope**: Both main thread and subagents (agent-scoped queuedCommands)

### Attachment Processing Groups

#### User Input Attachments (lines 772–814)

Triggered by non-null `input` parameter (user text on turn 0):

1. **At-mentioned files** (line 774): `processAtMentionedFiles()` — extracts @file paths
2. **MCP resource mentions** (line 777): `processMcpResourceAttachments()` — extracts @uri references
3. **Agent mentions** (line 780): `processAgentMentions()` — extracts @agent-name references
4. **Skill discovery** (lines 800–812): Turn-0 skill discovery signal (if feature enabled + skipSkillDiscovery not set)

#### Thread Attachments (lines 823–940)

Executed in all threads (main + subagents):

1. **Queued commands** (line 828): `getQueuedCommandAttachments()` — mode='prompt' + 'task-notification'
2. **Date change** (line 829): `getDateChangeAttachments()` — midnight crossing
3. **Ultrathink effort** (line 832): `getUltrathinkEffortAttachment()` — keyword detection
4. **Deferred tools delta** (line 835): `getDeferredToolsDeltaAttachment()` — tool-search announcements
5. **Agent listing delta** (line 850): `getAgentListingDeltaAttachment()` — agent pool changes
6. **MCP instructions delta** (line 853): `getMcpInstructionsDeltaAttachment()` — MCP server instruction changes
7. **Companion intro** (line 865): `getCompanionIntroAttachment()` — buddy introduction (if BUDDY feature)
8. **Changed files** (line 870): `getChangedFiles()` — edited files since last turn
9. **Nested memory** (line 871): `getNestedMemoryAttachments()` — CLAUDE.md file discovery
10. **Dynamic skills** (line 873): `getDynamicSkillAttachments()` — skill directory discovery
11. **Skill listing** (line 874): `getSkillListingAttachments()` — skill descriptions
12. **Plan mode** (line 880): `getPlanModeAttachments()` — plan mode reminders
13. **Plan mode exit** (line 881): `getPlanModeExitAttachment()` — exit notification
14. **Auto mode** (line 884): `getAutoModeAttachments()` — auto mode reminders (if TRANSCRIPT_CLASSIFIER)
15. **Auto mode exit** (line 887): `getAutoModeExitAttachment()` — auto exit notification
16. **Todo/task reminders** (line 892): `getTodoReminderAttachments()` or `getTaskReminderAttachments()`
17. **Teammate mailbox** (line 906): `getTeammateMailboxAttachments()` — swarm DM delivery
18. **Team context** (line 910): `getTeamContextAttachment()` — team coordination (first turn only)
19. **Agent pending messages** (line 915): `getAgentPendingMessageAttachments()` — agent-scoped messages
20. **Critical system reminder** (line 918): `getCriticalSystemReminderAttachment()` — user-injected critical text
21. **Compaction reminder** (line 923): `getCompactionReminderAttachment()` — nudge to compact
22. **Context efficiency** (line 935): `getContextEfficiencyAttachment()` — snip nudge

#### Main-Thread-Only Attachments (lines 943–986)

Only when `isMainThread = true`:

1. **IDE selection** (line 945): `getSelectedLinesFromIDE()` — user-selected code
2. **IDE opened file** (line 948): `getOpenedFileFromIDE()` — file open in editor + nested memory
3. **Output style** (line 951): `getOutputStyleAttachment()` — non-default output style
4. **Diagnostics** (line 954): `getDiagnosticAttachments()` — linter/compiler errors
5. **LSP diagnostics** (line 957): `getLSPDiagnosticAttachments()` — language server diagnostics
6. **Unified tasks** (line 960): `getUnifiedTaskAttachments()` — background task status
7. **Async hook responses** (line 963): `getAsyncHookResponseAttachments()` — hook event responses
8. **Token usage** (line 966): `getTokenUsageAttachment()` — context window breakdown
9. **Budget USD** (line 974): `getMaxBudgetUsdAttachment()` — spend/budget tracking
10. **Output token usage** (line 979): `getOutputTokenUsageAttachment()` — turn output budget
11. **Verify plan reminder** (line 982): `getVerifyPlanReminderAttachment()` — plan verification prompt

### Complete Attachment Type Enumeration

See `Attachment` union type (lines 439–716) for all 58+ attachment types:

**File Attachments:**
- `file` — user at-mentioned file content
- `compact_file_reference` — lightweight reference (for compaction)
- `pdf_reference` — large PDF reference (page count, size)
- `already_read_file` — file already in context
- `edited_text_file` — file changed during turn
- `edited_image_file` — image changed during turn
- `directory` — directory listing
- `selected_lines_in_ide` — IDE-selected code
- `opened_file_in_ide` — file open in editor

**Memory & Context:**
- `nested_memory` — CLAUDE.md discovered via traversal
- `relevant_memories` — prefetch-based memory injection
- `current_session_memory` — session-wide memory snapshot

**Skills & Tools:**
- `dynamic_skill` — skill directory
- `skill_listing` — formatted skill descriptions
- `skill_discovery` — newly discovered skills (Haiku signal)
- `deferred_tools_delta` — announced new tools (tool-search)
- `agent_listing_delta` — announced new agents
- `mcp_instructions_delta` — announced MCP server instructions
- `invoked_skills` — skills used in current turn

**Task & Planning:**
- `todo_reminder` — todo list reminder
- `task_reminder` — task list reminder
- `task_status` — individual task update
- `plan_mode` — plan mode reminder (full/sparse)
- `plan_mode_reentry` — re-entering after exit
- `plan_mode_exit` — exiting plan mode
- `verify_plan_reminder` — nudge to verify plan
- `auto_mode` — auto mode reminder
- `auto_mode_exit` — exiting auto mode

**Queued Commands & Communication:**
- `queued_command` — user/system message attachment
- `teammate_mailbox` — swarm DM delivery
- `team_context` — team coordination setup
- `async_hook_response` — hook event response
- `agent_mention` — @agent reference

**Output & Rendering:**
- `output_style` — non-default output format
- `output_token_usage` — output token budget state
- `critical_system_reminder` — user-injected system text
- `companion_intro` — buddy introduction

**Diagnostics & Status:**
- `diagnostics` — file diagnostics
- `plan_file_reference` — plan file content
- `mcp_resource` — MCP resource content
- `command_permissions` — allowed tools list
- `token_usage` — context window breakdown
- `budget_usd` — USD spend tracking
- `bagel_console` — debug console sample

**Context Management:**
- `date_change` — midnight crossing notification
- `ultrathink_effort` — thinking-mode activation
- `compaction_reminder` — nudge to compact
- `context_efficiency` — snip nudge
- `max_turns_reached` — max turn limit hit
- `hook_*` — hook event attachments (11 variants)

### Attachment Triggering Conditions

**Priority grouping:**

1. **Per-turn cap** (MAX_MEMORY_BYTES = 4096 per file × 5 files = 20KB/turn)
2. **Session-wide cap** (RELEVANT_MEMORIES_CONFIG.MAX_SESSION_BYTES = 60KB total)
3. **Throttle intervals:**
   - Plan mode: every 5 turns, full reminder every 5th attachment
   - Auto mode: every 5 turns, full reminder every 5th attachment
   - Todo reminder: 10+ turns since write, 10+ turns since last reminder
   - Task reminder: 10+ turns since task management, 10+ turns since last reminder
4. **One-time events:** date_change, plan_mode_exit, plan_mode_reentry, max_turns_reached
5. **Feature gates:** BUDDY, TRANSCRIPT_CLASSIFIER, BG_SESSIONS, HISTORY_SNIP, KAIROS, etc.

### Key Helpers

**`createAttachmentMessage()`** (lines 3201–3210):
```typescript
export function createAttachmentMessage(attachment: Attachment): AttachmentMessage
```
Wraps attachment in Message with uuid and timestamp.

**`getQueuedCommandAttachments()`** (lines 1046–1083):
- Filters `mode='prompt'` and `mode='task-notification'`
- Builds image content blocks from pastedContents
- Returns array of 'queued_command' attachments

**`memoryFilesToAttachments()`** (lines 1710–1775):
- Dedup against loadedNestedMemoryPaths (non-evicting Set) and readFileState (LRU)
- Fires InstructionsLoaded hooks if applicable
- Marks in readFileState with isPartialView flag if content differs from disk

**`getDirectoriesToProcess()`** (lines 1656–1689):
- Computes nested directories between CWD and target file
- Returns separate lists for nested and CWD-level directories for phased processing

---

## 4. End-to-End Flow Map

### Pipeline Trace: One User Input Through the System

```
USER INPUT
  ↓
[1] INPUT PROCESSING
    query.ts:query() → queryLoop() at line 240
    - Entry point: async generator, receives QueryParams
    - file: query.ts, function: queryLoop (lines 240–1729)
    
  ↓
[2] USER MESSAGE CONSTRUCTION
    QueryEngine.ts:submitMessage() at line 208
    - Processes @mentions, slash commands, image pastes
    - File: QueryEngine.ts, function: processUserInput() at line 415
    - Source: utils/processUserInput/processUserInput.js
    
  ↓
[3] SYSTEM PROMPT ASSEMBLY
    QueryEngine.ts:submitMessage() at lines 287–324
    - Fetches default system prompt + tool descriptions
    - File: utils/queryContext.js (imported)
    - Appends memory mechanics prompt if memory-path set
    - Appends appendSystemPrompt if provided
    - Returns: SystemPrompt array (strings)
    
  ↓
[4] SYSTEM CONTEXT INJECTION
    query.ts:queryLoop() at line 449
    - Calls: appendSystemContext(systemPrompt, systemContext)
    - File: utils/api.ts, function: appendSystemContext (lines 437–447)
    - Appends "key: value" entries to system prompt array
    
  ↓
[5] USER CONTEXT INJECTION
    query.ts:queryLoop() at line 660
    - Calls: prependUserContext(messagesForQuery, userContext)
    - File: utils/api.ts, function: prependUserContext (lines 449–474)
    - Creates synthetic user message with <system-reminder> block
    - Prepends to messages array
    
  ↓
[6] ATTACHMENT GENERATION (TURN 0)
    query.ts:getAttachmentMessages() — delegates to:
    utils/attachments.ts:getAttachments() at line 742
    
    Parallel groups (lines 772–993):
    A. User input attachments:
       - processAtMentionedFiles() → FileAttachment | directory
       - processMcpResourceAttachments() → mcp_resource
       - processAgentMentions() → agent_mention
       - getTurnZeroSkillDiscovery() → skill_discovery
    
    B. Thread attachments (all threads):
       - getQueuedCommandAttachments() → queued_command
       - getDateChangeAttachments() → date_change
       - getDynamicSkillAttachments() → dynamic_skill
       - getNestedMemoryAttachments() → nested_memory
       - And 18 others...
    
    C. Main-thread-only:
       - getSelectedLinesFromIDE() → selected_lines_in_ide
       - getOpenedFileFromIDE() → opened_file_in_ide + nested_memory
       - getOutputStyleAttachment() → output_style
       - And 8 others...
    
    Returns: Attachment[] (0–60+ items)
    
  ↓
[7] ATTACHMENT TO MESSAGE CONVERSION
    query.ts:getAttachmentMessages() at line 1580
    - Calls: createAttachmentMessage(attachment)
    - File: utils/attachments.ts, function: createAttachmentMessage (lines 3201–3210)
    - Yields each as AttachmentMessage with uuid + timestamp
    
  ↓
[8] MESSAGE ACCUMULATION
    query.ts:queryLoop() at line 1716
    - Merges: [...messagesForQuery, ...assistantMessages, ...toolResults]
    - For next iteration state
    
  ↓
[9] TOKEN BUDGET PRECALCULATION
    query.ts:queryLoop() at line 637
    - Calls: calculateTokenWarningState() — checks blocking limit
    - File: services/compact/autoCompact.ts
    - May return early with error if at blocking limit
    
  ↓
[10] MICROCOMPACT (IF ENABLED)
    query.ts:queryLoop() at line 413
    - Calls: deps.microcompact(messagesForQuery, toolUseContext, querySource)
    - File: services/compact/microcompact.ts (via deps injection)
    - Returns: { messages, compactionInfo? }
    - May edit prompt cache; deferred boundary emission
    
  ↓
[11] AUTO-COMPACTION (IF TRIGGERED)
    query.ts:queryLoop() at line 453
    - Calls: deps.autocompact(messagesForQuery, toolUseContext, {...}, querySource, tracking, snipTokensFreed)
    - File: services/compact/autoCompact.ts (via deps injection)
    - Checks: token count + grace-period + consecutive failures
    - Returns: { compactionResult?, consecutiveFailures }
    - Yields post-compact boundary messages if triggered
    
  ↓
[12] LLM CALL
    query.ts:queryLoop() at line 659
    - Calls: deps.callModel({...})
    - File: services/api/claude.ts
    - Parameters:
      - messages: prependUserContext(messagesForQuery, userContext)
      - systemPrompt: appendSystemContext(systemPrompt, systemContext)
      - thinkingConfig, tools, signal, options (model, fastMode, etc.)
      - taskBudget (if set in params)
    
    Returns: AsyncIterator<StreamEvent | Message>
    
  ↓
[13] STREAMING RESPONSE PROCESSING
    query.ts:queryLoop() at line 659 (for-await loop)
    - Processes each streamed message:
      - Emit or withhold (recoverable errors)
      - Collect assistant messages + tool_use blocks
      - Feed to StreamingToolExecutor if enabled
    
    Functions:
    - isWithheldPromptTooLong() — reactiveCompact.isWithheldPromptTooLong()
    - isWithheldMaxOutputTokens() — check for max_output_tokens error
    - isWithheldMediaSizeError() — reactiveCompact.isWithheldMediaSizeError()
    
    Fallback handling (lines 893–953):
    - If FallbackTriggeredError thrown, retry with fallbackModel
    - Clear previous messages, reset executors, log event
    
  ↓
[14] POST-SAMPLING HOOKS (FIRE-AND-FORGET)
    query.ts:queryLoop() at line 1001
    - Calls: executePostSamplingHooks(...)
    - File: utils/hooks/postSamplingHooks.js
    - Events: extractMemory, skillImprovement, magicDocs
    - NOT awaited — fires in background
    
  ↓
[15] ERROR RECOVERY (IF NEEDED)
    query.ts:queryLoop() at lines 1070–1256
    
    A. Context-collapse drain (lines 1089–1117):
       - Calls: contextCollapse.recoverFromOverflow()
       - File: services/contextCollapse/index.js
       - Transition: collapse_drain_retry
    
    B. Reactive-compact (lines 1119–1182):
       - Calls: reactiveCompact.tryReactiveCompact()
       - File: services/compact/reactiveCompact.js
       - Transition: reactive_compact_retry or surface error
    
    C. Max-output-tokens escalation (lines 1195–1221):
       - Retry with ESCALATED_MAX_TOKENS (8k → 64k)
       - Transition: max_output_tokens_escalate
    
    D. Multi-turn recovery (lines 1223–1252):
       - Inject recovery message: "Output token limit hit. Resume directly..."
       - Transition: max_output_tokens_recovery
    
  ↓
[16] STOP HOOKS
    query.ts:queryLoop() at line 1267
    - Calls: handleStopHooks(messagesForQuery, assistantMessages, systemPrompt, userContext, systemContext, toolUseContext, querySource, stopHookActive)
    - File: query/stopHooks.ts
    - Returns: { preventContinuation?, blockingErrors? }
    
    If preventContinuation: return { reason: 'stop_hook_prevented' }
    If blockingErrors: inject into messages, transition: stop_hook_blocking
    
  ↓
[17] COMPLETION CHECK (NO TOOL CALLS)
    query.ts:queryLoop() at line 1062
    - if (!needsFollowUp) → completion path (steps 15–16)
    - else → tool execution path (steps 18–20)
    
  ↓
[18] TOOL EXECUTION (IF TOOL CALLS PRESENT)
    query.ts:queryLoop() at line 1382
    - Calls: streamingToolExecutor.getRemainingResults() or runTools(...)
    - File: services/tools/StreamingToolExecutor.js or services/tools/toolOrchestration.js
    - Iterates tool updates, yields messages, normalizes for API
    
  ↓
[19] POST-TOOL ATTACHMENTS
    query.ts:queryLoop() at line 1580
    - Calls: getAttachmentMessages(null, updatedToolUseContext, null, queuedCommandsSnapshot, messagesWithToolResults, querySource)
    - File: utils/attachments.ts, function: getAttachments()
    - Same attachment generation as [6], but with tool results in context
    
    Additional: Memory prefetch consumption (lines 1599–1614)
    - Calls: filterDuplicateMemoryAttachments() + pendingMemoryPrefetch.promise
    - Injects prefetched nested memory + skill discovery
    
  ↓
[20] TURN CONTINUATION
    query.ts:queryLoop() at line 1716
    - Check maxTurns (lines 1705–1712)
    - Build new State with accumulated messages
    - state = next; continue → loop back to top
    
  ↓
[21] RECURSIVE RECURSION (LOOP)
    Continues until:
    - needsFollowUp = false (step 17)
    - maxTurns exceeded (step 20)
    - Stop hook prevented (step 16)
    - Early return on error (step 15)
    
  ↓
RESPONSE TO USER
    query.ts:query() (line 229) yields Terminal from queryLoop
    QueryEngine.ts:submitMessage() converts to SDKMessage
    User receives: result, usage, permission_denials, stop_reason
```

### Key Cross-File Integration Points

| Step | File (function) | Caller | Purpose |
|------|-----------------|--------|---------|
| 1 | query.ts (query) | User code | Entry point |
| 2 | QueryEngine.ts (submitMessage) | SDK caller | High-level orchestration |
| 3 | utils/queryContext.js (fetchSystemPromptParts) | QueryEngine (line 291) | System prompt assembly |
| 4 | utils/api.ts (appendSystemContext) | query.ts (line 449) | System context append |
| 5 | utils/api.ts (prependUserContext) | query.ts (line 660) | User context prepend |
| 6 | utils/attachments.ts (getAttachments) | query.ts (line 1580) | Attachment generation |
| 7 | utils/attachments.ts (createAttachmentMessage) | query.ts (line 1609) | Message wrapping |
| 9 | services/compact/autoCompact.ts (calculateTokenWarningState) | query.ts (line 637) | Token check |
| 10 | services/compact/microcompact.ts (microcompact) | query.ts (line 413) | Prompt cache edit |
| 11 | services/compact/autoCompact.ts (autocompact) | query.ts (line 453) | Full compaction |
| 12 | services/api/claude.ts (callModel) | query.ts (line 659) | API streaming |
| 14 | utils/hooks/postSamplingHooks.js (executePostSamplingHooks) | query.ts (line 1001) | Post-LLM hooks |
| 15A | services/contextCollapse/index.js (recoverFromOverflow) | query.ts (line 1094) | Context collapse drain |
| 15B | services/compact/reactiveCompact.js (tryReactiveCompact) | query.ts (line 1120) | Reactive compaction |
| 16 | query/stopHooks.ts (handleStopHooks) | query.ts (line 1267) | Stop hook evaluation |
| 18 | services/tools/toolOrchestration.js (runTools) | query.ts (line 1382) | Tool execution |

---

## NOT FOUND Sections

The following items could not be definitively located in the 3 primary files:

1. **Token budget enforcement logic** — Referenced in query.ts:1308–1355 via `checkTokenBudget()` from `./query/tokenBudget.js`, but that file was not read. Exact implementation NOT FOUND.
2. **Compaction summary generation** — Referenced in query.ts:528 as `buildPostCompactMessages()` from `./services/compact/compact.js`, but source not read. NOT FOUND.
3. **Reactive compact details** — Referenced as `reactiveCompact.isWithheldPromptTooLong()` and `tryReactiveCompact()`, but file not read. Exact conditions NOT FOUND.
4. **Context collapse recovery details** — Referenced as `contextCollapse.recoverFromOverflow()`, but file not read. Exact mechanism NOT FOUND.
5. **Tool orchestration specifics** — `runTools()` from `./services/tools/toolOrchestration.js` and `StreamingToolExecutor` class logic—files not read. NOT FOUND.
6. **Memory prefetch settle logic** — `startRelevantMemoryPrefetch()` from `./utils/attachments.js` reference in query.ts:300, but full implementation not detailed. Settle mechanism NOT FOUND.
7. **Stop hook implementation** — `handleStopHooks()` from `./query/stopHooks.js` referenced, but source not read. Specific conditions NOT FOUND.
8. **LLM API stream message format** — `deps.callModel()` returns `AsyncIterator<StreamEvent | Message>`, but StreamEvent type definition not fully traced. Format NOT FOUND.

---

**Document generated:** 2026-04-08
**Source files analyzed:** 3 (query.ts, QueryEngine.ts, attachments.ts)
**Total LoC read:** ~7,021 lines
**Scope:** Behavior-only reference (no recommendations, no interpretation)

