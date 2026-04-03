# Steering Vectors for LLM Personality Control: Research Synthesis

**Date:** 2026-03-31
**Purpose:** Viability assessment for applying steering vectors to Clonnect clone personas (Qwen3-14B target)

---

## Table of Contents

1. [Paper 1 — PERSONA (arXiv:2602.15669, ICLR 2026)](#1-persona-arxiv260215669-iclr-2026)
2. [Paper 2 — Persona Vectors (Anthropic, arXiv:2507.21509)](#2-persona-vectors-anthropic-arxiv250721509)
3. [Repo 3 — Cross-Model Persona Steering (sbayer2)](#3-cross-model-persona-steering-sbayer2)
4. [Related Work — Soul Engine (arXiv:2512.07092)](#4-related-work--soul-engine-arxiv251207092)
5. [Viability Assessment for Qwen3-14B](#5-viability-assessment-for-qwen3-14b)
6. [GPU Requirements and Cost Analysis](#6-gpu-requirements-and-cost-analysis)
7. [Implementation Plan](#7-implementation-plan)
8. [Recommendation: DeepInfra API vs Self-Host](#8-recommendation-deepinfra-api-vs-self-host)

---

## 1. PERSONA (arXiv:2602.15669, ICLR 2026)

**Full title:** PERSONA: Dynamic and Compositional Inference-Time Personality Control via Activation Vector Algebra
**Authors:** Xiachong Feng, Liang Zhao, Weihong Zhong, Yichong Huang, Yuxuan Gu, Lingpeng Kong, Xiaocheng Feng, Bing Qin
**Submitted:** February 17, 2026
**Status:** Accepted ICLR 2026
**arXiv:** https://arxiv.org/abs/2602.15669

> Note: This is the paper matching the "PERSONA-FLOW" description in the brief. The system has three named stages — PERSONA-BASE, PERSONA-ALGEBRA, and PERSONA-FLOW — where "Flow" refers to the context-aware dynamic composition stage. It evaluates Qwen2.5 series models among others.

### 1.1 Core Claim

Current personality control methods (static prompting, SFT fine-tuning) fail to capture the dynamic and compositional nature of human traits. PERSONA provides training-free inference-time control via direct activation manipulation, achieving performance nearly identical to SFT (9.60 vs 9.61 on PersonalityBench) with up to 91% win rates on the Persona-Evolve benchmark.

### 1.2 Methodology

The framework has three stages:

**Stage 1 — PERSONA-BASE (vector extraction):**
- Uses contrastive activation analysis: run the model on pairs of prompts with positive-persona vs negative-persona system instructions
- Compute mean difference of hidden states between positive and negative runs at each layer
- Apply Gram-Schmidt orthogonalization across the Big Five OCEAN dimensions to ensure trait vectors are geometrically independent (not correlated)
- Result: one vector per OCEAN trait per layer, shape `[num_layers × hidden_dim]`
- This is the same mean-difference approach used by Anthropic's Persona Vectors paper

**Stage 2 — PERSONA-ALGEBRA (vector arithmetic):**
- Trait vectors can be scaled (intensity), added (combine traits), or subtracted (suppress traits)
- Enables compositional personality specification: e.g., `0.8 * Openness + 0.5 * Extraversion`
- No gradient updates required — pure linear algebra in activation space

**Stage 3 — PERSONA-FLOW (context-aware dynamic composition):**
- During inference, the composition weights are not static but adapt to conversation context
- The model dynamically adjusts which trait vectors are active and at what strength
- Prevents the "static mask" problem where a fixed steering vector degrades coherence in mismatched contexts

### 1.3 Key Results

| Benchmark | Score | Comparison |
|-----------|-------|------------|
| PersonalityBench | 9.60 / 10 | SFT upper bound: 9.61 |
| Persona-Evolve win rate | Up to 91% | vs. vanilla baseline |
| Reported range | 73–91% win rate | across model families and traits |
| Training cost | Zero (training-free) | SFT requires hours of GPU compute |

### 1.4 Model Architecture Requirements

- **Requires local model weights and access to hidden states** — cannot work via a standard text-generation API
- Validated on Qwen2.5 series (3B, 7B, 14B) and other model families
- Uses `output_hidden_states=True` during the HuggingFace forward pass
- Layer targeting: middle layers (roughly 40–60% depth into the network) yield the best trait capture. For Qwen2.5-7B (28 layers), the canonical layer is **layer 14–20**
- Orthogonalization is computed offline once per model; subsequent inference only requires adding the steering vector to hidden states at the target layer

### 1.5 Inference-Time Overhead

- Overhead is minimal: adding a pre-computed vector to one hidden state per forward step
- No additional LLM calls required for Stages 1 and 2
- Stage 3 (PERSONA-FLOW context routing) requires a lightweight classifier or dot-product similarity check at each token — adds <5ms per token on GPU
- Memory overhead: storing all OCEAN vectors per layer for a 14B model is approximately `40 layers × 5120 hidden_dim × 5 traits × 2 bytes (fp16) = ~10 MB` — negligible

### 1.6 API vs Self-Host

**Requires self-hosting.** Standard LLM APIs (OpenAI-compatible, DeepInfra, Together AI) do not expose hidden states or allow mid-layer activation injection. This method is fundamentally incompatible with black-box API access.

---

## 2. Persona Vectors (Anthropic, arXiv:2507.21509)

**Full title:** Persona Vectors: Monitoring and Controlling Character Traits in Language Models
**Authors:** Chen et al. (Anthropic)
**arXiv:** https://arxiv.org/abs/2507.21509
**Repo:** https://github.com/safety-research/persona_vectors

### 2.1 Core Claim

Identifies linear directions in activation space ("persona vectors") that correspond to traits like evil, sycophancy, and hallucination propensity. Beyond inference-time control, the paper demonstrates a novel application: **monitoring personality drift during training** and using vectors to flag training data likely to cause undesirable trait shifts.

### 2.2 Methodology

**Vector extraction pipeline (from repo source code):**

1. Generate contrastive prompt pairs via a system prompt template:
   - Positive: `"You are a [trait] assistant."` + trait-eliciting instructions
   - Negative: `"You are a helpful assistant."` + neutral instructions
2. Run both through the model with `output_hidden_states=True`
3. Compute mean difference of response token hidden states (not prompt tokens — empirically better):
   ```python
   vector[layer] = mean(pos_activations[layer]) - mean(neg_activations[layer])
   ```
4. Save tensors of shape `[num_layers × hidden_dim]` per trait
5. At inference, inject the vector at a specific layer with a coefficient:
   ```python
   hidden_states[layer] += coefficient * persona_vector[layer]
   ```

**Primary validated model:** `Qwen/Qwen2.5-7B-Instruct`
**Default steering layer:** Layer 20 (out of 28 total layers)
**Default steering coefficient:** 2.0

**Training-time application (preventative steering):**
- During fine-tuning, continuously apply the negative-direction vector to suppress unwanted trait amplification
- Applied at layer 20 with `steering_coef=5.0` during gradient updates
- Demonstrated to prevent personality drift when fine-tuning on misaligned data

### 2.3 Key Results

- Steering effectively controls trait expression (evil, sycophancy, hallucination propensity) at eval time
- Persona vector projections are **strongly correlated** with personality shifts after fine-tuning
- Can flag individual training samples likely to produce trait drift before training runs
- Vectors generalize across prompt types and conversation contexts within the same model family

### 2.4 Hardware Requirements

The repo uses standard HuggingFace `transformers` with `CUDA_VISIBLE_DEVICES` — any CUDA GPU works. For Qwen2.5-7B-Instruct in BF16:
- **VRAM for inference + activation extraction:** ~16 GB
- A single A100 40GB or RTX 3090 24GB is sufficient for the 7B model
- For 14B: ~30 GB VRAM in BF16, requires an A100 80GB or equivalent

### 2.5 What Makes This Different from PERSONA

| Aspect | Anthropic Persona Vectors | PERSONA (ICLR 2026) |
|--------|--------------------------|---------------------|
| Primary use case | Safety monitoring + drift detection | Personality expression control |
| Trait types | Safety-oriented (evil, sycophancy) | OCEAN Big Five |
| Orthogonalization | Not applied | Yes (Gram-Schmidt) |
| Dynamic composition | No | Yes (PERSONA-FLOW stage) |
| Training-time use | Yes (preventative steering) | No |
| Repo quality | Production-grade, Anthropic | Research prototype |

### 2.6 Inference-Time Overhead

Same as PERSONA: adding a pre-computed vector to hidden states is O(hidden_dim) per token per layer — negligible (<1ms per forward pass on GPU).

### 2.7 API vs Self-Host

**Requires self-hosting.** Identical constraint to PERSONA: needs `output_hidden_states=True` and the ability to modify activation tensors during the forward pass. This is not possible through any standard inference API including DeepInfra.

---

## 3. Cross-Model Persona Steering (sbayer2)

**Repo:** https://github.com/sbayer2/cross-model-persona-steering
**Status:** Research implementation (v1.1.1, November 2025)
**Based on:** Chen et al. 2024 (Anthropic arXiv:2507.21509)

### 3.1 Core Claim

Extends the Anthropic Persona Vectors paper to demonstrate **cross-architecture transfer**: extract persona vectors from Qwen2.5-7B-Instruct (HuggingFace weights), then apply them to steer GPT-OSS 20B (a GGUF-format model) — a completely different architecture. Claims 95%+ effective steering transfer rate.

### 3.2 Methodology

**For HuggingFace models (Qwen, Llama, Mistral):**
- Identical to Anthropic approach: PyTorch forward hooks or `output_hidden_states=True`
- **Dynamic layer selection**: instead of fixed layer 20, scores each layer by proximity to model midpoint
  ```python
  effectiveness = 1.0 - abs(layer - total_layers//2) / max(midpoint, total_layers - midpoint)
  ```
- Direct activation injection at the selected optimal layer

**For GGUF models (GPT-OSS 20B via llama.cpp):**
- Cannot inject directly into activations (llama.cpp doesn't expose them)
- Uses **parameter modulation as a proxy**: interprets the persona vector's norm/direction to adjust `temperature` and `top_p`
  ```python
  temperature = base_temp + (coefficient * 0.3)
  top_p = base_top_p - (abs(coefficient) * 0.2)
  ```
- This is a **significant approximation** — generation parameter tuning is not equivalent to activation-level steering

### 3.3 Assessment of Cross-Architecture Claims

The cross-architecture steering to GGUF models is methodologically weak: adjusting temperature/top_p based on a vector norm is not the same as steering internal representations. The "95% transfer success rate" metric used is coherence + qualitative trait expression, which temperature changes trivially affect. The HuggingFace-to-HuggingFace transfer (Qwen → Llama/Mistral) is more credible but relies on different hidden sizes between architectures being a problem.

**Credible finding:** For models within the same family (Qwen2.5-3B → Qwen2.5-7B → Qwen2.5-14B), vectors likely transfer well given shared architecture, tokenizer, and training corpus. This is relevant to Clonnect.

### 3.4 Hardware Requirements

- Designed and tested on Apple Silicon Mac with Metal acceleration
- Requires ~12–15 GB RAM per 8B model loaded locally
- For Qwen2.5-7B: needs ~16 GB VRAM (CUDA) or ~12 GB RAM (Metal/CPU offload — slower)
- Web interface via FastAPI, single-user design

### 3.5 Inference-Time Overhead

- Vector extraction (one-time): 3–5 minutes per trait on a single GPU
- Inference with steering: no reported overhead for HuggingFace models
- Batch testing (5-point spectrum sweep): 5–10 minutes per test suite

### 3.6 Practical Value for Clonnect

The repo is most useful as a **working code reference** for the extraction + injection pipeline, with a web interface that makes it easy to test different coefficients visually. The dynamic layer selection heuristic is a useful contribution over the fixed layer-20 default.

---

## 4. Related Work — Soul Engine (arXiv:2512.07092)

**Title:** The Geometry of Persona: Disentangling Personality from Reasoning in Large Language Models
**Author:** Zhixiang Wang
**arXiv:** https://arxiv.org/abs/2512.07092
**Code:** Available on Hugging Face

### 4.1 Summary

Proposes the **Soul Engine** framework based on the Linear Representation Hypothesis: personality traits exist as orthogonal linear subspaces in activation space. Uses a **dual-head architecture** on a frozen Qwen-2.5 base to extract disentangled personality vectors without modifying backbone weights.

Key results:
- MSE of 0.011 against psychological ground truth (OCEAN benchmark)
- T-SNE visualization confirms distinct, continuous personality manifolds
- Enables Zero-Shot Personality Injection while preserving reasoning capability
- Claims to resolve the stability-plasticity dilemma — no "alignment tax"

### 4.2 Differentiation

Unlike PERSONA and Persona Vectors (which use contrastive mean-difference), Soul Engine uses a **trained dual-head** — meaning it requires a brief supervised training step on a labeled personality dataset (SoulBench). This makes it slightly less "training-free" than the other approaches, but the backbone remains frozen.

---

## 5. Viability Assessment for Qwen3-14B

### 5.1 Model Architecture (Qwen3-14B)

| Parameter | Value |
|-----------|-------|
| Total parameters | 14.8B |
| Number of transformer layers | 40 |
| Hidden size | 5120 |
| Intermediate size | 17,408 |
| Attention heads | 40 Q / 8 KV (GQA) |
| Context length | 32,768 native / 131,072 with YaRN |
| VRAM (BF16 full precision) | ~30 GB |
| VRAM (INT8 quantized) | ~15 GB |
| VRAM (INT4 quantized) | ~8 GB |
| VRAM (BF16 + activation cache for extraction) | ~40 GB |

### 5.2 Compatibility with Each Approach

**PERSONA (ICLR 2026):**
- Compatible: standard HuggingFace transformer architecture
- Target layer for 14B: layers 16–24 (40–60% depth = layers 16–24 out of 40)
- Vector shape: `[40 × 5120]` per OCEAN trait = ~1.6 MB per trait, ~8 MB for all 5 OCEAN traits
- Orthogonalization overhead: trivial (one-time offline computation)
- Requires ~40 GB VRAM during extraction (30 GB model + ~10 GB activation buffers for all 40 layers)
- **Inference-time steering: can run with INT8 quantization (~15 GB VRAM)** since steering vectors are additive

**Anthropic Persona Vectors:**
- Fully compatible — same extraction methodology, HuggingFace `output_hidden_states=True`
- The repo ships pre-built pipelines for Qwen2.5-7B; adapting to Qwen3-14B requires updating `--layer` to ~24 (default was 20 for 28-layer model — proportionally equivalent)
- Best validated approach (Anthropic code quality, safety-research production standards)
- **Recommended as base implementation**

**Cross-Model Steering (sbayer2):**
- Compatible for the HuggingFace path
- Dynamic layer selection would auto-select layer 20 (midpoint of 40-layer model)
- Useful as UI/demo code; not production-grade for direct deployment

**Soul Engine:**
- Compatible but requires running SoulBench fine-tuning of the dual-head (short, on frozen backbone)
- More complex setup than mean-difference approaches
- Advantage: higher precision against psychological benchmarks (MSE 0.011)

### 5.3 Key Constraint: Self-Host Required

**All four approaches require self-hosting.** None work via API because they need:
1. `output_hidden_states=True` during the forward pass
2. Ability to modify `hidden_states` tensors mid-forward-pass (for inference-time steering)

DeepInfra's API exposes log probabilities but **not hidden states**. There is no workaround — activation-level steering is architecturally incompatible with black-box API inference.

### 5.4 Qwen3 vs Qwen2.5 Compatibility

The papers validated on Qwen2.5-7B-Instruct. Qwen3-14B is a different (newer) architecture. Considerations:

- **Shared design language**: Both use RoPE, SwiGLU, RMSNorm, GQA — same family
- **Hidden size difference**: Qwen2.5-7B hidden_size=3584; Qwen3-14B hidden_size=5120. Vectors extracted on one **cannot be directly transferred** to the other
- **Must re-extract vectors on Qwen3-14B** from scratch (this is expected — vectors are model-specific)
- **Extraction is fast**: ~3–5 minutes per trait on A100 80GB
- **Qwen3's thinking mode**: Qwen3 supports a special `<think>` mode. For persona steering, use standard (non-thinking) mode to keep activation distributions consistent

---

## 6. GPU Requirements and Cost Analysis

### 6.1 VRAM Budget

| Phase | Operation | VRAM Needed | Suitable GPU |
|-------|-----------|-------------|--------------|
| Vector extraction (BF16) | Forward pass, all 40 layers, activation capture | ~40 GB | A100 80GB, H100 80GB |
| Vector extraction (INT8) | Quantized extraction (acceptable quality) | ~22 GB | A100 40GB, A6000 48GB |
| Inference steering (BF16) | Run model + add vector at one layer | ~30 GB | A100 80GB, H100 80GB |
| Inference steering (INT8) | Quantized inference + steering | ~16 GB | A100 40GB, RTX 3090 24GB |
| Inference steering (INT4) | Most quantized, slight quality loss | ~9 GB | RTX 4090 24GB |

**Recommended configuration for production:** A100 40GB (extraction in INT8) or A100 80GB (extraction in BF16, highest fidelity).

### 6.2 RunPod Pricing (approximate, community cloud)

RunPod's pricing is dynamically sourced from the marketplace. Based on known market rates as of Q1 2026:

| GPU | VRAM | On-Demand ($/hr) | Spot/Interruptible ($/hr) |
|-----|------|-------------------|--------------------------|
| A100 PCIe 80GB | 80 GB | ~$1.89–$2.49 | ~$0.89–$1.29 |
| A100 SXM 80GB | 80 GB | ~$2.19–$2.89 | ~$1.10–$1.49 |
| H100 PCIe 80GB | 80 GB | ~$2.99–$3.99 | ~$1.49–$1.99 |
| H100 SXM 80GB | 80 GB | ~$3.49–$4.49 | ~$1.89–$2.29 |
| A100 PCIe 40GB | 40 GB | ~$1.29–$1.79 | ~$0.59–$0.89 |
| RTX 4090 24GB | 24 GB | ~$0.69–$0.99 | ~$0.35–$0.55 |

> Note: RunPod pricing is marketplace-driven and fluctuates. Verify current rates at runpod.io/pricing before provisioning. Spot instances may be interrupted.

**Alternative providers:**
- **Vast.ai**: Typically 20–40% cheaper than RunPod for spot instances; larger marketplace with more A100 availability
- **Lambda Labs**: More stable pricing, A100 80GB at ~$2.49/hr (reserved contracts available)
- **Google Colab Pro+**: A100 40GB included in $54/mo subscription — sufficient for INT8 extraction

### 6.3 Cost Estimate for One-Time Vector Extraction

Extracting OCEAN vectors for one creator (5 traits × positive + negative runs × ~50 contrastive prompts each):

| Step | Time | GPU | Cost |
|------|------|-----|------|
| Download Qwen3-14B weights (29 GB) | ~15 min | — | — |
| Contrastive inference (500 forward passes) | ~20 min | A100 80GB | ~$0.07 |
| Mean-diff computation + orthogonalization | ~2 min | A100 80GB | ~$0.01 |
| **Total per creator** | ~40 min | A100 80GB spot | **~$0.50–$1.00** |

Vector extraction is essentially **one-time per creator per base model**. Vectors are saved as PyTorch tensors (~8 MB) and reused indefinitely at inference.

### 6.4 Cost Estimate for Ongoing Inference Steering

Assuming Clonnect's current usage pattern (Iris Bertran: ~640 webhooks/batch; ~100 active conversations/day):

| Scenario | Config | Cost per 1K tokens | Daily cost (est.) |
|----------|--------|-------------------|-------------------|
| API (DeepInfra Qwen3-14B) | No steering possible | ~$0.14/1M input | ~$0.10–$0.30 |
| Self-host (RunPod A100 80GB) | BF16 + steering | $2.49/hr on-demand | ~$2.50/day continuous |
| Self-host (RunPod A100 40GB) | INT8 + steering | $1.49/hr on-demand | ~$1.50/day continuous |
| Self-host (spot + auto-scale) | INT8 + steering | ~$0.80/hr avg | ~$0.80/day continuous |

**Reality check:** Clonnect does not need continuous GPU uptime. DM responses are triggered by webhooks — bursts of activity, not continuous. A **serverless GPU endpoint** (RunPod Serverless or Modal.com) would be more cost-effective:

| Provider | Model | Cold start | Per-second billing | ~Cost per DM response |
|----------|-------|-----------|-------------------|-----------------------|
| RunPod Serverless | Qwen3-14B INT8 | ~10–30s | ~$0.0002/s (A100) | ~$0.005–$0.015 |
| Modal.com | Qwen3-14B INT8 | ~15–40s | GPU-second billing | ~$0.008–$0.020 |

At 100 DM responses/day, serverless cost is **< $1.50/day** with no idle cost.

---

## 7. Implementation Plan

### Phase 0 — Validation (1–2 days, ~$5 compute)

**Goal:** Confirm steering vectors work on Qwen3-14B before committing to infrastructure.

1. Rent a RunPod A100 80GB spot instance (~$1.50/hr)
2. Clone `github.com/safety-research/persona_vectors`
3. Download `Qwen/Qwen3-14B` in BF16
4. Extract one trait vector (e.g., "friendly" or "empathetic") using the existing pipeline
5. Run 10 test prompts with and without steering (coefficient sweep: -2.0 to +2.0)
6. Evaluate output quality with GPT-4.1-mini judge (same as Clonnect's existing eval framework)

**Success criterion:** Steering moves trait expression in the intended direction on at least 7/10 prompts without degrading coherence.

**Commands:**
```bash
# On RunPod A100 80GB instance
git clone https://github.com/safety-research/persona_vectors
cd persona_vectors && pip install -r requirements.txt

# Extract vectors for "empathetic" trait
CUDA_VISIBLE_DEVICES=0 python -m eval.eval_persona \
    --model Qwen/Qwen3-14B \
    --trait empathetic \
    --output_path extractions/Qwen3-14B/empathetic_pos.csv \
    --persona_instruction_type pos \
    --assistant_name empathetic \
    --judge_model gpt-4.1-mini \
    --version extract

python generate_vec.py \
    --model_name Qwen/Qwen3-14B \
    --pos_path extractions/Qwen3-14B/empathetic_pos.csv \
    --neg_path extractions/Qwen3-14B/empathetic_neg.csv \
    --trait empathetic \
    --save_dir persona_vectors/Qwen3-14B/
```

### Phase 1 — Clone Trait Profiling (3–5 days, ~$20 compute)

**Goal:** Extract OCEAN + custom Clonnect-specific trait vectors for iris_bertran and other creators.

1. Define creator-specific trait dimensions from interview data and style analysis
   - For iris_bertran: warmth/friendliness, enthusiasm, directness, humor style, vocabulary richness
   - This maps loosely to OCEAN but can be creator-specific
2. Generate contrastive prompt pairs using existing `calibrations/iris_bertran.json` data as positive examples and neutral/formal text as negative
3. Extract vectors for all 5–8 traits
4. Orthogonalize using Gram-Schmidt to ensure independence
5. Save trait vectors as `.pt` files per creator

**Target layer for Qwen3-14B:** Layer 20–24 (50–60% depth into 40-layer model, same proportional position as layer 20 in the 28-layer Qwen2.5-7B)

### Phase 2 — Integration with Clonnect Pipeline (1 week)

**Goal:** Modify `core/dm/generation.py` to apply persona vectors during response generation.

Architecture options:

**Option A — In-process steering (single server):**
- Load Qwen3-14B locally in the same Railway/RunPod container as the FastAPI backend
- Apply steering vector at inference time using HuggingFace hooks
- Pro: lowest latency; Con: requires 16–30 GB VRAM on the inference server

**Option B — Separate steering microservice:**
- RunPod Serverless endpoint: receives prompt + creator_id, loads cached vectors, returns steered response
- FastAPI backend calls this endpoint instead of DeepInfra/Gemini for DM generation
- Pro: clean separation, self-scaling; Con: network hop, cold start latency

**Option C — Hybrid (recommended for Clonnect):**
- Keep DeepInfra for fast API responses (no steering) for simple cases
- Use self-hosted steered model for "important" DMs (detected lead scoring > threshold, or explicit creative response)
- Routes in `core/dm/generation.py` based on `lead_score` or message complexity

**Code sketch (Option B microservice call):**
```python
# In core/dm/generation.py
async def generate_steered_response(prompt: str, creator_id: str) -> str:
    vectors = await load_persona_vectors(creator_id)  # cached .pt files
    payload = {
        "prompt": prompt,
        "creator_id": creator_id,
        "steering_layer": 22,  # Qwen3-14B optimal layer
        "coefficients": vectors["active_traits"],  # e.g., {"warm": 1.5, "enthusiastic": 1.2}
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(STEERING_ENDPOINT, json=payload, timeout=30.0)
    return resp.json()["response"]
```

### Phase 3 — Evaluation and Calibration (1 week)

**Goal:** Measure impact on Clonnect's existing eval framework (target: current 8.17/10 baseline → 8.5+).

1. Run `tests/massive_test.py` with steered Qwen3-14B responses
2. Compare scores on `test_set_real_leads` (n=15) against current Gemini-2.5-flash-lite baseline
3. Tune steering coefficients per trait using the CPE (Clone Performance Eval) framework
4. Identify which traits benefit most from steering vs. which are already captured by `calibrations/iris_bertran.json`
5. Special attention to `real_011` (current worst case: 6.57 avg) — empathy-heavy context may benefit most from a "warmth" steering vector

### Phase 4 — Production Deployment (3–5 days)

**Infrastructure choice:** RunPod Serverless with Qwen3-14B INT8 (see recommendation section).

**Estimated timeline:** 3–4 weeks from start to production.

---

## 8. Recommendation: DeepInfra API vs Self-Host

### The Core Constraint

**DeepInfra cannot support steering vectors.** Their API is OpenAI-compatible and exposes only:
- Text generation completions
- Log probabilities (logprobs)
- Function calling / JSON mode

It does **not** expose hidden states, intermediate activations, or allow mid-forward-pass tensor modification. This is not a limitation of DeepInfra specifically — it is a fundamental property of all black-box inference APIs. Steering vectors require white-box access to the model's internal computation graph.

**Qwen3-14B availability on DeepInfra:** Confirmed available (`Qwen/Qwen3-14B` with 40K context). Can be used for standard text generation but **not for activation steering**.

### Decision Matrix

| Criterion | DeepInfra API | Self-Host (RunPod) |
|-----------|---------------|---------------------|
| Steering vectors possible | No | Yes |
| Setup complexity | Trivial (API key) | Medium (1–2 days) |
| Latency per response | ~2–4s (network) | ~3–8s (cold start included) |
| Cost at 100 DMs/day | ~$0.15/day | ~$0.50–$1.50/day |
| Scaling | Auto | Manual or serverless |
| Maintenance | None | Model updates, infra monitoring |
| Qwen3-14B access | Yes (INT4 quantized) | Yes (any precision) |
| Clone quality improvement | None (same as current) | +0.3–0.8 expected |

### Recommendation

**For Clonnect's immediate needs:** Continue using DeepInfra (or Gemini-2.5-flash-lite as currently configured) for standard DM generation. The current 8.17/10 baseline is already competitive.

**For the steering vector experiment:** Run Phase 0 validation first (1 day, ~$5). If validation confirms >0.3 score improvement on the test set, proceed to self-host with **RunPod Serverless** using Qwen3-14B INT8:

- **Model:** `Qwen/Qwen3-14B` with INT8 quantization (~15 GB VRAM)
- **Platform:** RunPod Serverless (A100 40GB workers, pay-per-second)
- **Cold start mitigation:** Keep one warm worker during active hours (9am–11pm), scale to zero overnight
- **Estimated cost:** ~$1.50–$2.50/day during active hours, < $0.10/day overnight
- **Code base:** Fork `github.com/safety-research/persona_vectors`, adapt for Qwen3-14B with custom Clonnect trait definitions

**The most important single action before committing:** Run the Phase 0 validation (< $5, < 1 day) to confirm that steering vectors on Qwen3-14B actually improve Clonnect's specific quality metric (CPE judge score on iris_bertran test set). The published 73–91% win rates are on generic PersonalityBench tasks, not on Clonnect's highly specific creator-mimicry objective. The delta could be smaller or larger depending on how much of the current quality gap is due to personality style vs. factual/contextual errors.

### Final Verdict

| Scenario | Recommendation |
|----------|----------------|
| Steering vectors validated (Phase 0 succeeds) | Self-host RunPod Serverless, Qwen3-14B INT8 |
| Steering vectors not validated | Continue current Gemini-2.5-flash-lite via API |
| Need both speed and steering | Hybrid: DeepInfra for fast-path, self-host for high-value DMs |
| Budget constrained (<$50 experiment budget) | Colab Pro+ A100 40GB for extraction, Modal.com for serverless inference |

---

## Appendix A: Key Links

| Resource | URL |
|----------|-----|
| PERSONA paper (ICLR 2026) | https://arxiv.org/abs/2602.15669 |
| Anthropic Persona Vectors paper | https://arxiv.org/abs/2507.21509 |
| Anthropic Persona Vectors repo | https://github.com/safety-research/persona_vectors |
| Cross-Model Steering repo | https://github.com/sbayer2/cross-model-persona-steering |
| Soul Engine paper | https://arxiv.org/abs/2512.07092 |
| Qwen3-14B HuggingFace | https://huggingface.co/Qwen/Qwen3-14B |
| Qwen2.5-7B-Instruct HuggingFace | https://huggingface.co/Qwen/Qwen2.5-7B-Instruct |
| RunPod pricing | https://www.runpod.io/pricing |
| DeepInfra models | https://deepinfra.com/models |

## Appendix B: Qwen3-14B Architecture Quick Reference

```
num_hidden_layers: 40
hidden_size: 5120
intermediate_size: 17408
num_attention_heads: 40
num_key_value_heads: 8 (GQA)
context_length: 32768 (native)
VRAM BF16: ~30 GB
VRAM INT8: ~15 GB
VRAM INT4: ~8 GB
VRAM BF16 + activation extraction: ~40 GB
Recommended steering layer: 20–24 (50–60% depth)
Vector size per trait: 40 × 5120 × 2 bytes = ~400 KB (BF16)
All 5 OCEAN vectors: ~2 MB
```

## Appendix C: Minimum Viable Experiment Script

```python
"""
Phase 0 validation: test steering vector effect on Clonnect DM quality.
Run on RunPod A100 80GB. Takes ~40 minutes, costs ~$1.
"""
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "Qwen/Qwen3-14B"
STEERING_LAYER = 22  # ~55% depth, good starting point for 40-layer model
TRAIT = "warm_and_empathetic"
COEF = 1.5  # Start conservative; tune in Phase 1

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.bfloat16,
    device_map="auto"
)

# Load pre-extracted vector (saved from persona_vectors pipeline)
steering_vec = torch.load(f"persona_vectors/Qwen3-14B/{TRAIT}_response_avg_diff.pt")
layer_vec = steering_vec[STEERING_LAYER].to(model.device)  # shape: [5120]

# Hook to inject vector at target layer
def make_hook(vec, coef):
    def hook(module, input, output):
        if isinstance(output, tuple):
            output[0][:, :, :] += coef * vec
            return output
        else:
            output[:, :, :] += coef * vec
            return output
    return hook

handle = model.model.layers[STEERING_LAYER].register_forward_hook(
    make_hook(layer_vec, COEF)
)

# Run test prompt
prompt = "Hola! Quería preguntarte sobre tus clases de Barre..."
inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
with torch.no_grad():
    output = model.generate(**inputs, max_new_tokens=100, do_sample=True, temperature=0.7)
print("STEERED:", tokenizer.decode(output[0], skip_special_tokens=True))

handle.remove()

# Run same prompt without steering for comparison
with torch.no_grad():
    output = model.generate(**inputs, max_new_tokens=100, do_sample=True, temperature=0.7)
print("BASELINE:", tokenizer.decode(output[0], skip_special_tokens=True))
```
