# Worker B Report — Sprint 2: prod secundario (judge + extraction + audio)

## Cambios

### `services/llm_judge.py` — site #3
- `JUDGE_MODEL` default: `gpt-4o-mini` → `Qwen/Qwen3-30B-A3B`
- `_call_judge()`: URL `api.openai.com` → `api.deepinfra.com/v1/openai`
- API key: `OPENAI_API_KEY` → `DEEPINFRA_API_KEY`
- Error log: `logger.error` → `logger.warning` (degradación, no crítico)

### `core/personality_extraction/llm_client.py` — site #4
- `call_openai_extraction()`: eliminado cuerpo OpenAI, ahora delega a `call_gemini_extraction()`
- `extract_with_llm()`: eliminado bloque fallback OpenAI
- Gemini ya era primario; el fallback nunca se activaba en producción

### `ingestion/transcriber.py` — site #5
- `_transcribe_openai()` eliminado (-34 líneas)
- `_call_whisper_api()` legacy eliminado (-53 líneas)
- `__init__`: eliminado `self.api_key` y warning OpenAI
- Cascade: Groq → Gemini → `return "", "none", language` (DM agent maneja vacío)

## Variables Railway
- `CLONE_SCORE_JUDGE_MODEL=Qwen/Qwen3-30B-A3B` (opcional, default ya en código)
- `DEEPINFRA_API_KEY` ya existe en Railway

## Coste eliminado
- ~$14/mes potencial (CloneScore judge, si ENABLE_CLONE_SCORE=true)
- $0.006/min potencial (Whisper-1 fallback)
