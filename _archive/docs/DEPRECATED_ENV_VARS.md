# Deprecated Environment Variables — Railway Cleanup

**Date:** 2026-02-19
**Context:** After migrating from Scout FT v2 (DeepInfra) to Gemini Flash-Lite cascade,
several environment variables are no longer used in the active DM pipeline.

## Variables to DELETE from Railway

| Variable | Old Provider | Status | Notes |
|----------|-------------|--------|-------|
| `DEEPINFRA_API_KEY` | DeepInfra (Scout FT) | DEAD | Entire `deepinfra_provider.py` unused |
| `DEEPINFRA_API_URL` | DeepInfra | DEAD | Hardcoded in unused module |
| `DEEPINFRA_TIMEOUT` | DeepInfra | DEAD | |
| `DEEPINFRA_INCLUDE_REASONING` | DeepInfra | DEAD | |
| `DEEPINFRA_NO_FALLBACK` | DeepInfra | DEAD | |
| `GROQ_API_KEY` | Groq (old fallback) | DEAD | Old Scout fallback, not called |
| `ANTHROPIC_API_KEY` | Anthropic | DEAD | Configured in Settings but never used |
| `USE_SCOUT_MODEL` | Scout flag | DEAD | Set in dm_agent_v2.py:133 but never read |
| `SCOUT_MODEL` | Scout model ID | DEAD | Only in unused deepinfra_provider.py |
| `SCOUT_LORA_ADAPTER` | Scout LoRA | DEAD | Only in unused deepinfra_provider.py |
| `SCOUT_PROVIDER` | Scout routing | DEAD | Only in unused deepinfra_provider.py |
| `LLM_PROVIDER` | LLM routing | DEAD | Logged at startup but pipeline is hardcoded |

## Variables to KEEP

| Variable | Provider | Status | Used By |
|----------|---------|--------|---------|
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Google Gemini | ACTIVE | `gemini_provider.py` — Primary DM model |
| `OPENAI_API_KEY` | OpenAI | ACTIVE | `gemini_provider.py` fallback + embeddings |
| `EVOLUTION_API_URL` | Evolution API | ACTIVE | `evolution_api.py` — WhatsApp |
| `EVOLUTION_API_KEY` | Evolution API | ACTIVE | `evolution_api.py` — WhatsApp |
| `TELEGRAM_ALERTS_BOT_TOKEN` | Telegram | ACTIVE | `core/alerts.py` — Alert system |
| `TELEGRAM_ALERTS_CHAT_ID` | Telegram | ACTIVE | `core/alerts.py` — Alert system |

## Dead Code Files (can be deleted later)

- `backend/core/providers/deepinfra_provider.py` — entire module unused
- `backend/core/llm.py` — old GroqClient/AnthropicClient classes, never instantiated
- `backend/services/llm_service.py` — old LLM abstraction, unused
