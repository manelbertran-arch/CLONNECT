# AUDIT PART 1 — Message Input & Audio Pipeline

**Date:** 2026-03-19
**Scope:** Evolution webhook → Instagram webhook → Media download → Transcriber → Audio Intelligence → Early save → SSE notify
**Intent:** Analysis only. No code changes.

---

## 1. Evolution Webhook (`api/routers/messaging_webhooks/evolution_webhook.py`)

### What it does
Receives WhatsApp messages via Evolution API (Baileys). Entry point is `POST /webhook/evolution`. Routing by instance name via `EVOLUTION_INSTANCE_MAP`. Handles: text, audio (download + transcribe + audio intelligence), image, video, sticker, document, reaction, message deletion, connection status, group events. Outgoing (fromMe) messages are saved to DB but don't trigger DM agent. Incoming messages go through two layers of dedup (ID-based + content hash), then early save, then DM agent in background via `asyncio.create_task`.

### Does it actually do it?
Yes. Both creators (`stefano_bonanno`, `iris_bertran`) are wired via `EVOLUTION_INSTANCE_MAP`. The full pipeline runs: webhook → dedup → early save → DM agent → copilot/autopilot.

### Bugs / edge cases / dead code

**BUG — LID JID phone normalization (line 346):**
```python
sender_number = remote_jid.replace("@s.whatsapp.net", "").replace("@g.us", "").replace("@lid", "")
```
This does NOT strip the Baileys LID timestamp suffix. A LID JID like `34692419787-1610116326@lid` becomes `34692419787-1610116326`, not `34692419787`. `_normalize_wa_phone()` (lines 51–66) handles this correctly with `.split("-")[0]`, but is NOT used here. LID JIDs are a Baileys-specific format that appear when contacts use newer WhatsApp account types. If triggered, `follower_id = "wa_34692419787-1610116326"` would fail to match any existing lead and create a ghost lead.

**BUG — Profile pic update missing `creator_id` filter (lines 1094–1096):**
```python
lead = db.query(Lead).filter(
    Lead.platform_user_id == follower_id
).first()
```
No `creator_id` filter. If two creators both have a lead from the same WhatsApp number (phone recycling, or a follower who follows both creators), the first DB row returned may belong to the wrong creator. Only the `profile_pic_url` and `full_name` are updated (only if missing), so blast radius is low — but it's a correctness bug.

**BUG — Language forced to "es" when Gemini Tier 1 handles audio (lines 682–684):**
```python
detected_lang = getattr(transcript, "language", None) or "es"
if detected_lang == "auto":
    detected_lang = "es"
```
Tier 1 Gemini (`_transcribe_gemini_audio`) returns `language` in the cascade as the **input** param, not a detected language (see Transcriber section, Bug #1). When called with `language=None`, `detected_lang = None` → `Transcript.language = "auto"` → `detected_lang` here becomes `"es"`. Result: any audio transcribed by Gemini Tier 1 (i.e., whenever Groq fails) is tagged as Spanish regardless of actual language. Audio Intelligence then runs with `language="es"` → Spanish summary even for Catalan audio. **This is the upstream root cause of the language bug fixed this session — the fix in audio_intelligence.py is correct but this upstream source of wrong language survives.**

**DESIGN — Hardcoded instance map:**
```python
EVOLUTION_INSTANCE_MAP: Dict[str, str] = {
    "stefano-fitpack": "stefano_bonanno",
    "iris-bertran": "iris_bertran",
}
```
Adding a third creator requires a code change + deploy. No DB-driven lookup.

**DESIGN — Content dedup uses MD5 of sender+text (line 103):**
Content dedup has a 60s TTL. If a lead legitimately sends the same message twice within 60s (e.g., "Hola" "Hola" because they got no response), the second one is silently dropped. This is intentional but may surprise creators.

**EDGE CASE — Early save skips new leads:**
`_do_early_save()` returns `False` if the lead doesn't exist yet (`_el = None`). New leads on their first-ever message get no early save, no SSE notification, and the message only appears in the frontend after the DM agent completes (2–5s slower path).

### Data in / out
- **In:** HTTP POST from Evolution API server. JSON body with `event`, `instance`, `data` (containing `key`, `message`, `pushName`).
- **Out:** `{"status": "ok", "event": ..., "sender": ..., "processing": true}` (200). DM agent result is fire-and-forget.

### Downstream
After DM agent processes: copilot saves `pending_approval` message or autopilot sends via Evolution send endpoint. SSE `new_message` event fires to connected frontends.

---

## 2. Instagram Webhook (`api/routers/messaging_webhooks/instagram_webhook.py` + `core/instagram_modules/webhook.py`)

### What it does
Two endpoints exist:
- `/instagram/webhook` — old handler (Iris only, no `webhook_count` tracking)
- `/webhook/instagram` — new V9 handler (Stefano, tracks `webhook_count`)

Both call `get_handler_for_creator` → `InstagramHandler` → `handle_webhook_impl`. The handler routes by IGSID (matching `page_id` or `ig_user_id` in DB). Processing is async via `asyncio.create_task` — webhook returns 200 immediately.

### Does it actually do it?
Yes. Confirmed: Iris → old endpoint, Stefano → new endpoint. Both funnel into the same `handle_webhook_impl`.

### Bugs / edge cases / dead code

**BUG — `known_ids` may contain `None` (webhook.py:92):**
```python
known_ids = {handler.page_id, handler.ig_user_id}
```
If either `handler.page_id` or `handler.ig_user_id` is `None` (e.g., creator not fully configured), `None` is inserted into the set. The check `if message.sender_id in known_ids` won't incorrectly match string sender IDs to `None`, but it's defensive code that could mask a misconfigured creator. In practice, a `None` page_id means no creator would be found for that IGSID, and the message would be processed as a lead message from the page/user itself — not a security issue, but unexpected behavior.

**BUG — `lead_id=""` passed to copilot (dispatch.py:162):**
```python
pending = await copilot.create_pending_response(
    creator_id=handler.creator_id,
    lead_id="",         # ← empty string, not actual lead UUID
    follower_id=message.sender_id,
    ...
)
```
`lead_id` is explicitly empty string. `create_pending_response` must resolve the lead from `follower_id` internally, which it does. However, the `pending_responses` DB record has `lead_id=""` (a non-UUID string) or the copilot resolves it internally and uses the real UUID. This should be audited in `core/copilot_service.py` — if `lead_id` is stored as-is, this is a data integrity issue.

**DESIGN — Reaction handling:**
Reactions (`message.reactions`) are extracted but not dispatched through the DM agent. They are recorded in `_record_received` only. No copilot/autopilot suggestion is generated for reactions — this is intentional.

**DESIGN — Background task error swallowing:**
Processing exceptions are caught at the for-loop level (webhook.py:257–267) and logged, not surfaced to the caller. If the DM agent crashes, the webhook still returns success. The creator sees no error.

### Data in / out
- **In:** Meta webhook JSON `{entry: [{messaging: [...]}]}`.
- **Out:** `{"status": "ok", "messages_processed": N, ...}` wrapped in 200 from the outer endpoint.

### Downstream
`dispatch_response` → either copilot (`create_pending_response`) or autopilot (Instagram Graph API send).

---

## 3. Media Download + Cloudinary (`_download_evolution_media`, evolution_webhook.py:550–713)

### What it does
Fetches media bytes from Evolution API via `getBase64FromMediaMessage` endpoint. Saves to a temp file. Uploads to Cloudinary for permanent URL. For audio: calls transcriber cascade + audio intelligence pipeline. Returns dict with `url`, `mimetype`, `transcription`, `audio_intel`.

### Does it actually do it?
Yes. All 5 media types supported: audio, image, video, sticker, document. Cloudinary upload happens for all types; transcription only for audio.

### Bugs / edge cases

**EDGE CASE — No permanent URL if Cloudinary fails:**
If Cloudinary upload fails (line 670, `cloud_err` is caught and logged), `result["url"]` stays `None`. The message is saved to DB with `msg_metadata["url"] = None`. The WhatsApp CDN URL (expires in 24h per CLAUDE.md) is never persisted here — it's only in the raw Evolution payload. After 24h, the media is inaccessible.

**EDGE CASE — No file size check before Cloudinary:**
Large video files (near 25MB Whisper limit, but also over Cloudinary free tier limits) could fail at upload. The error is caught and logged but the `url` silently stays `None`.

**EDGE CASE — Instagram media not uploaded to Cloudinary:**
This function is Evolution-only. Instagram media CDN URLs (also expire in 24h) follow a different path and are NOT uploaded to Cloudinary in this codebase. This is an existing gap unrelated to this function.

**DESIGN — Temp file lifecycle:**
Temp file is cleaned up in `finally` regardless of Cloudinary upload status. This is correct — Cloudinary upload uses bytes not the file path.

### Data in / out
- **In:** Evolution webhook payload dict, `instance` name, `media_type` string.
- **Out:** `{"url": str|None, "mimetype": str, "transcription": str, "audio_intel": dict, "detected_language": str}`.

---

## 4. Transcriber (`ingestion/transcriber.py`)

### What it does
3-tier cascade: Tier 0 (Groq Whisper v3 Turbo, free) → Tier 1 (Gemini 2.0 Flash audio native) → Tier 2 (OpenAI Whisper-1). Returns a `Transcript` with `full_text`, `language`, `model_used`. Called by both Evolution webhook (audio) and implicitly by Instagram audio handling.

### Does it actually do it?
Yes. Tier 0 (Groq) is the primary path. GROQ_API_KEY confirmed present in Railway (via `GROQ_API_KEY` env var). Fallback chain works correctly.

### Bugs / edge cases / dead code

**BUG — Tier 1 Gemini returns input language, not detected language (line 224):**
```python
return text, "gemini-2.0-flash-audio", language   # ← `language` is the INPUT param
```
Tier 1 `_transcribe_gemini_audio` is a pure text-generation call with no structured language output. The cascade returns the `language` parameter that was passed in. If `language=None` (auto-detect, which is the default), `detected_lang = None` → `Transcript.language = "auto"`.

In contrast:
- Tier 0 Groq uses `verbose_json` and reads `response.language` (actual detection).
- Tier 2 OpenAI Whisper uses `verbose_json` and reads `response.language` (actual detection).

Only Tier 1 Gemini has this gap. Severity: medium — Groq is the primary and usually succeeds; Gemini is only used when Groq is rate-limited or down.

**DEAD CODE — `_call_whisper_api()` (lines 360–410):**
This legacy method is never called. The active Tier 2 path uses `_transcribe_openai()` (lines 330–356). The legacy method is a full duplicate with an older `prompt` string and segment parsing. Safe to remove but harmless.

**EDGE CASE — `transcribe_url()` loads entire file into memory:**
No streaming; `response.content` loads the full audio bytes. For a 20MB audio file this allocates 20MB of memory on the Railway instance. No size limit check before downloading.

**DESIGN — Groq uses filename `"audio.ogg"` regardless of MIME type (line 259):**
```python
"file": ("audio.ogg", audio_bytes, mime_type),
```
The filename is always `"audio.ogg"` even if `mime_type` is `"audio/mp4"`. Groq (and OpenAI) use MIME type to determine format, not filename, so this is harmless but misleading.

**DESIGN — Bilingual Spanish-Catalan Whisper prompt (line 347):**
The OpenAI Whisper prompt is hardcoded as a mixed Spanish-Catalan sentence to help Whisper detect code-switching. This is intentional and clever — Whisper uses the prompt as a prior to recognize both languages in the same audio.

### Data in / out
- **In:** `file_path` (str) or `url` (str), optional `language` ISO code.
- **Out:** `Transcript(full_text, language, model_used)`.

### Downstream
Used by `_download_evolution_media` (Evolution WA audio) and any other caller passing audio paths. `transcript.language` feeds into `audio_intelligence.process(language=...)`.

---

## 5. Audio Intelligence (`services/audio_intelligence.py`)

### What it does
4-layer LLM pipeline on top of Whisper transcription: (1) raw transcription, (2) clean (remove filler words, fix grammar), (3) extract (intent, entities, action items, emotional tone, topics), (4) synthesize (structured summary). Feature-flagged behind `ENABLE_AUDIO_INTELLIGENCE`.

### Does it actually do it?
Yes. `ENABLE_AUDIO_INTELLIGENCE=true` confirmed in Railway. Each layer uses Gemini (via `GeminiProvider`) with `LAYER_TIMEOUT_SECONDS = 12` per layer.

### Bugs / edge cases

**DESIGN — `MIN_WORDS_FOR_PROCESSING = 30` (line 28):**
Audios with fewer than 30 words bypass all 4 LLM layers and return raw Whisper text. This affects short voice notes (greetings, confirmations like "Sí, perfecto", "Gracias", "Ok te llamo"). These get no summary/intent — the DM agent sees raw Whisper text. This is intentional but worth documenting.

**DESIGN — Module-level flag evaluated at import time:**
```python
ENABLE_AUDIO_INTELLIGENCE = (
    os.getenv("ENABLE_AUDIO_INTELLIGENCE", "false").lower() == "true"
)
```
Changing the env var requires a Railway deploy (restart) for it to take effect. No hot-reload.

**FIXED THIS SESSION — Language now propagated:**
Previously, all 3 LLM prompts (CLEAN_PROMPT, EXTRACT_PROMPT, SUMMARY_PROMPT) had no explicit language instruction. Spanish was the implicit default for prompts and fallback field values ("ninguna", "neutro"). Now each prompt starts with `IDIOMA OBLIGATORIO: ... en {lang_name}` and fallbacks are language-neutral `"-"`.

**REMAINING RISK (upstream):** Even with this fix, if Evolution Webhook receives a Catalan audio and Groq fails → Gemini Tier 1 handles it → `detected_lang = None` → `Transcript.language = "auto"` → `evolution_webhook.py:682–684` forces `"es"` → audio intelligence receives `language="es"` and generates a Spanish summary. The fix in this service is correct but the upstream wrong-language injection from the transcriber cascade is still present (see Bug #1 in Transcriber section).

**EDGE CASE — 12s timeout per layer:**
If all 3 LLM layers (clean, extract, synthesize) hit timeout, the pipeline degrades: `clean_text = raw_text`, `intent = ""`, `summary = ""`. The DM agent sees raw Whisper text. No error is surfaced to the creator.

### Data in / out
- **In:** `raw_text` (str), `language` (str ISO code), `role` ("user"/"assistant").
- **Out:** `AudioIntelligence` dataclass → `.to_metadata()` dict, `.to_legacy_fields()` dict.

### Downstream
`to_metadata()` stored in `msg_metadata["audio_intel"]`. `to_legacy_fields()` sets `transcript_raw`, `transcript_full`, `transcript_summary`. The DM agent reads `msg_metadata.audio_intel.clean_text` (or falls back to `summary`, then raw transcription) when building the conversation history.

---

## 6. Early Save (`_do_early_save`, evolution_webhook.py:467–523)

### What it does
Saves the incoming user message to DB immediately (via `asyncio.to_thread`) before the DM agent processes it. Goal: message appears in frontend dashboard instantly via SSE `new_message` event, without waiting for the ~2s DM agent pipeline.

### Does it actually do it?
Yes — for **existing leads**. For new leads (first message ever), the lead row doesn't exist yet, so `_el = None`, early save returns `False`, no SSE fires. The message is saved later by the lifecycle.

### Bugs / edge cases

**POTENTIAL DUPLICATE — UNIQUE constraint as implicit guard:**
Early save sets `status="sent"` with `platform_message_id=message_id`. The lifecycle in `_process_evolution_message_safe` also saves the message. With Migration 037's `UNIQUE(lead_id, platform_message_id)` index, the second insert raises an `IntegrityError`. The lifecycle wraps DB operations in try/except and logs the error silently. Net result: message saved exactly once (early save wins), lifecycle insert fails silently. This is safe but the lifecycle doesn't distinguish "duplicate insert" from "genuine DB error" — both are logged at the same level.

**EDGE CASE — New lead SSE gap:**
New leads on first message: no early save → no SSE → no immediate dashboard update. The creator sees the new lead appear ~2–5s after the message arrives (after DM agent completes). Acceptable UX but worth documenting.

**EDGE CASE — `status="sent"` hardcoded:**
Early save creates the message with `status="sent"`. The Message model has statuses: `pending_approval`, `sent`, `edited`, `discarded`, `NULL`. `"sent"` is appropriate for user messages.

**DESIGN — SSE call wrapped in bare `except Exception: pass`:**
```python
try:
    from api.routers.events import notify_creator
    await notify_creator(...)
except Exception:
    pass
```
If SSE notification fails, the failure is completely invisible (no log). Should at minimum log at `DEBUG` level.

### Data in / out
- **In:** `sender_number`, `text`, `message_id`, `creator_id`, `msg_metadata`.
- **Out:** DB row `Message(role="user", status="sent")` + SSE `new_message` event.

---

## 7. SSE Notify (`api/routers/events.py`)

### What it does
Server-Sent Events endpoint at `GET /events/{creator_id}?token=...`. Frontend connects via `EventSource`. Auth is JWT or API key passed as query parameter (required by EventSource browser API which doesn't support custom headers). Stores active connections per creator in `_active_connections` (in-memory dict of `asyncio.Queue` lists). `notify_creator()` puts events into all queues for a creator.

### Does it actually do it?
Yes. SSE is used for `new_message`, `new_conversation`, `message_approved` events. Called from evolution_webhook.py, instagram_webhook.py, and copilot lifecycle.

### Bugs / edge cases

**DESIGN — In-memory only, no persistence:**
`_active_connections` lives in the uvicorn process. On Railway restart (deploy, crash, restart), all connections are lost. Events fired during disconnect are gone. Frontend `EventSource` auto-reconnects (browser-native), but missed events are never replayed. The frontend should re-fetch conversation lists on reconnect — this is a frontend concern.

**DESIGN — Hung connection eviction is lazy:**
A connection with a full queue (100 events) is only evicted when a NEW connection arrives for the same creator (line 121–130). A single hung connection (e.g., browser tab suspended) occupies a slot indefinitely until another connection triggers eviction. With `_SSE_MAX_CONNECTIONS_PER_CREATOR = 10`, this could use 10 slots for 10 hung connections from the same creator before any eviction kicks in.

**SECURITY — Token in URL query parameter:**
`token=JWT_OR_API_KEY` appears in:
- Railway/nginx access logs
- Browser history
- HTTP Referer header if page navigates away
- URL bar in browser

This is an accepted tradeoff for `EventSource` (which doesn't support custom headers), but the API key `clonnect_admin_secret_2024` should NOT be used to connect to SSE in production — only per-creator JWT tokens.

**DESIGN — QueueFull drops events silently at call sites:**
All call sites of `notify_creator()` wrap it in `try/except Exception: pass`. When `notify_creator` itself logs `[SSE] Queue full ... dropping event`, that log is visible. But if the `except` at the call site catches the `QueueFull` before it propagates (it doesn't — `QueueFull` is caught inside `notify_creator`), dropped events appear only in the SSE module's own warning. Acceptable but worth monitoring.

**DESIGN — `ping` keepalive every 20s:**
```python
except asyncio.TimeoutError:
    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
```
Prevents proxy/load balancer from closing idle connections. Correct pattern.

### Data in / out
- **In:** HTTP GET with `token` query param.
- **Out:** `text/event-stream` chunked response. Each chunk: `data: {"type": "...", "data": {...}}\n\n`.

---

## Summary Table

| System | Status | Critical Bugs | Design Gaps |
|--------|--------|--------------|-------------|
| Evolution Webhook | Working | LID JID normalization (line 346); profile pic no creator_id filter (line 1094); language forced "es" when Gemini Tier 1 (line 682) | Hardcoded instance map; content dedup drops legit re-sends |
| Instagram Webhook | Working | `lead_id=""` in copilot call (dispatch.py:162); `known_ids` may include None | Background errors swallowed silently |
| Media Download | Working | No permanent URL if Cloudinary fails; no file size guard | IG media not Cloudinary-uploaded |
| Transcriber | Working | Gemini Tier 1 returns input lang not detected (line 224); dead `_call_whisper_api` (line 360) | URL download loads full file into memory |
| Audio Intelligence | Working | Upstream wrong-language still possible via Gemini Tier 1 path | `MIN_WORDS=30` skips short audios; flag restart-only |
| Early Save | Working | Silent duplicate on lifecycle re-insert (benign, UNIQUE guard); SSE fail swallowed silently | New lead SSE gap |
| SSE | Working | — | In-memory only; lazy hung-conn eviction; token in URL |

---

## Priority Fix Recommendations

1. **HIGH — Line 346 (Evolution):** Use `_normalize_wa_phone(remote_jid)` instead of the manual `.replace()` chain. Prevents ghost leads for LID JID users.

2. **HIGH — Transcriber Tier 1 (line 224):** Gemini doesn't detect language. After Gemini transcription, run a lightweight language detection (e.g., `langdetect` or a Gemini prompt `"What language is this text in? Reply with ISO 639-1 code only."`) and return actual detected language instead of input param.

3. **MEDIUM — Line 1094 (Evolution):** Add `Lead.creator_id == _ec.id` to the profile pic update query to prevent cross-creator contamination.

4. **MEDIUM — dispatch.py:162:** Pass actual `lead_id` to `create_pending_response` or confirm that the copilot service correctly resolves it from `follower_id` and stores the real UUID.

5. **LOW — `_call_whisper_api` dead code (transcriber.py:360):** Remove to reduce maintenance surface.

6. **LOW — SSE call site (evolution_webhook.py:516):** Change bare `except Exception: pass` to `except Exception as e: logger.debug("[EarlySSE] notify failed: %s", e)` for observability.
