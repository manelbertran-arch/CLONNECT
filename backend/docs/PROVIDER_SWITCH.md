# Provider Switch Guide

How to change the LLM provider for DM response generation.

## Current Setup

| Setting | Value |
|---------|-------|
| Primary provider | Gemini (Flash-Lite) |
| Fallback provider | OpenAI (GPT-4o-mini) |
| Model | `gemini-2.5-flash-lite` |
| Cost | ~$0.000226/msg |
| Latency | ~600ms |

## Available Providers

### 1. Gemini Flash-Lite (current default)

```bash
# Already configured — this is the default
railway variables set GEMINI_MODEL=gemini-2.5-flash-lite
```

- Cheapest option ($0.075/M input, $0.30/M output)
- Fastest (600ms avg)
- No fine-tuning available — relies on prompt engineering
- Safety filter blocks ~5% of responses (falls back to GPT-4o-mini)

### 2. Together.ai (for fine-tuning + inference)

```bash
railway variables set TOGETHER_API_KEY=<key>
railway variables set TOGETHER_MODEL=clonnect/iris-qwen32b-dpo-v1
railway variables set LLM_PRIMARY_PROVIDER=together
```

- Fine-tuning: CPT/SFT/DPO on Qwen3-32B with QLoRA
- Inference: $0.18/M input, $0.18/M output (serverless)
- Latency: ~800ms (cold start ~2s)
- Run fine-tune: `python scripts/run_finetune_qwen32b.py --stage all`

### 3. DeepInfra (LoRA adapter hosting)

```bash
railway variables set DEEPINFRA_API_KEY=<key>
railway variables set DEEPINFRA_MODEL=clonnect/iris-qwen32b-dpo-v1
railway variables set LLM_PRIMARY_PROVIDER=deepinfra
```

- Hosts LoRA adapters on top of base models (no merging needed)
- $0.27/M input, $0.27/M output (serverless)
- Deploy: `bash scripts/deploy_to_deepinfra.sh together <job_id>`
- OpenAI-compatible API (drop-in replacement)

### 4. Fireworks.ai (serverless LoRA)

```bash
railway variables set FIREWORKS_API_KEY=<key>
railway variables set FIREWORKS_MODEL=accounts/clonnect/models/iris-qwen32b-dpo-v1
railway variables set LLM_PRIMARY_PROVIDER=fireworks
```

- Serverless LoRA — adapter loaded on-demand, no dedicated GPU
- $0.20/M input, $0.20/M output
- Deploy: `bash scripts/deploy_to_fireworks.sh ./lora_adapter`
- Fastest LoRA inference (~400ms with warm adapter)

### 5. OpenAI GPT-4o-mini (fallback only)

```bash
# Already configured as fallback — no action needed
railway variables set OPENAI_API_KEY=<key>
```

- Used automatically when Gemini fails (safety filter, rate limit)
- $0.15/M input, $0.60/M output
- No fine-tuning for voice cloning (no LoRA support)
- Higher quality but 2x more expensive and slower

## How to Switch

### Switch to fine-tuned model

```bash
# 1. Set the provider and model
railway variables set LLM_PRIMARY_PROVIDER=together
railway variables set TOGETHER_MODEL=clonnect/iris-qwen32b-dpo-v1

# 2. Verify (wait for Railway redeploy ~60s)
curl -s https://www.clonnectapp.com/health | python3 -m json.tool
```

### Rollback to Gemini

```bash
# Instant rollback — just change the env var
railway variables set LLM_PRIMARY_PROVIDER=gemini

# Verify
curl -s https://www.clonnectapp.com/health
```

### A/B test (route percentage)

Not yet implemented. Current options:
- Switch 100% to new provider, monitor LLM-judge scores
- If scores drop, rollback immediately
- Run `tests/measure_llm_judge.py` before and after switch

## Env Vars Reference

| Variable | Description | Required |
|----------|-------------|----------|
| `LLM_PRIMARY_PROVIDER` | `gemini` / `together` / `deepinfra` / `fireworks` | No (default: gemini) |
| `GEMINI_MODEL` | Gemini model name | For gemini provider |
| `GOOGLE_API_KEY` | Gemini API key | For gemini provider |
| `TOGETHER_API_KEY` | Together.ai API key | For together provider |
| `TOGETHER_MODEL` | Together model identifier | For together provider |
| `DEEPINFRA_API_KEY` | DeepInfra API key | For deepinfra provider |
| `DEEPINFRA_MODEL` | DeepInfra model identifier | For deepinfra provider |
| `FIREWORKS_API_KEY` | Fireworks.ai API key | For fireworks provider |
| `FIREWORKS_MODEL` | Fireworks model identifier | For fireworks provider |
| `OPENAI_API_KEY` | OpenAI API key (fallback) | Always (fallback) |

## Cost Comparison (per message, ~3K tokens in, ~50 tokens out)

| Provider | Input cost | Output cost | Total/msg | Latency |
|----------|-----------|-------------|-----------|---------|
| Gemini Flash-Lite | $0.000225 | $0.000015 | **$0.000240** | 600ms |
| Together (Qwen-32B) | $0.000540 | $0.000009 | **$0.000549** | 800ms |
| Fireworks (LoRA) | $0.000600 | $0.000010 | **$0.000610** | 400ms |
| DeepInfra (LoRA) | $0.000810 | $0.000014 | **$0.000824** | 700ms |
| OpenAI GPT-4o-mini | $0.000450 | $0.000030 | **$0.000480** | 1100ms |

Fine-tuned models (Together/DeepInfra/Fireworks) cost 2-3x more per message
but should produce higher quality responses, reducing copilot rejection rate.
The net cost may be lower if the approval rate improves significantly.
