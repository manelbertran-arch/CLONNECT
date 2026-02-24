# Stefan Response Length Analysis

**Date:** 2026-02-07
**Data source:** PostgreSQL production database (2,967 messages)
**Creator:** stefano_bonanno (UUID: 5e5c2364-c99a-4484-b986-741bb84a11cf)

---

## Executive Summary

The assumption that Stefan "always responds short (~31 chars)" is **INCORRECT**.

Analysis of 2,967 real sent assistant messages reveals that Stefan's response length varies **up to 5x** depending on conversation context:

- **Shortest:** Interest signals (median 10 chars) -- just acknowledges
- **Longest:** Objection handling (median 53 chars) -- persuades with detail
- **Baseline:** General conversation (median 23 chars)

The length controller has been updated from a flat target of 38 chars to context-adaptive rules derived from this analysis.

---

## Global Statistics

| Metric | Value |
|--------|-------|
| Total messages analyzed | 2,967 |
| Average length | 30.8 chars |
| Median length | 22.0 chars |
| Min length | 1 char |
| Max length | 705 chars |
| Standard deviation | 38.5 chars |

---

## Statistics by Context

| Context | N | Avg Chars | Median | Min | Max | StdDev | Emoji% | Question% |
|---------|---|-----------|--------|-----|-----|--------|--------|-----------|
| otro | 2386 | 31.3 | 23 | 1 | 569 | 33.5 | 18.3% | 12.9% |
| inicio_conversacion | 161 | 33.3 | 20 | 4 | 663 | 73.9 | 39.1% | 16.1% |
| pregunta_general | 121 | 26.7 | 17 | 3 | 405 | 40.9 | 11.6% | 6.6% |
| agradecimiento | 72 | 38.4 | 22 | 5 | 705 | 84.1 | 44.4% | 13.9% |
| story_mention | 55 | 22.4 | 18 | 1 | 80 | 14.2 | 20.0% | 3.6% |
| pregunta_producto | 50 | 22.0 | 21 | 6 | 55 | 13.0 | 24.0% | 12.0% |
| casual | 39 | 21.9 | 18 | 2 | 73 | 15.7 | 17.9% | 12.8% |
| pregunta_precio | 29 | 28.1 | 22 | 6 | 162 | 28.6 | 31.0% | 6.9% |
| interes | 24 | 16.6 | 10 | 4 | 61 | 13.0 | 8.3% | 16.7% |
| saludo | 21 | 19.4 | 17 | 5 | 44 | 9.8 | 9.5% | 19.0% |
| objecion | 9 | 67.7 | 53 | 10 | 277 | 83.2 | 0.0% | 0.0% |

---

## Percentile Breakdown

| Context | N | P5 | P10 | P25 | P50 | P75 | P90 | P95 | P99 |
|---------|---|-----|-----|-----|-----|-----|-----|-----|-----|
| otro | 2386 | 7 | 10 | 14 | 23 | 37 | 60 | 80 | 156 |
| inicio_conversacion | 161 | 6 | 8 | 13 | 20 | 29 | 51 | 63 | 662 |
| pregunta_general | 121 | 4 | 6 | 9 | 17 | 29 | 56 | 75 | 101 |
| agradecimiento | 72 | 9 | 10 | 15 | 22 | 32 | 51 | 102 | 705 |
| story_mention | 55 | 6 | 8 | 14 | 18 | 28 | 28 | 61 | 80 |
| pregunta_producto | 50 | 6 | 7 | 12 | 21 | 30 | 43 | 48 | 55 |
| casual | 39 | 4 | 6 | 9 | 18 | 33 | 42 | 50 | 73 |
| pregunta_precio | 29 | 6 | 8 | 14 | 22 | 32 | 46 | 51 | 162 |
| interes | 24 | 6 | 6 | 8 | 11 | 23 | 34 | 36 | 61 |
| saludo | 21 | 9 | 11 | 13 | 17 | 22 | 31 | 42 | 44 |
| objecion | 9 | 10 | 10 | 12 | 53 | 71 | 277 | 277 | 277 |

---

## Length Distribution (Histogram)

### otro (n=2386) -- baseline behavior
```
  0- 10:  307 (12.9%) ######
 11- 20:  722 (30.3%) ###############
 21- 30:  532 (22.3%) ###########
 31- 50:  486 (20.4%) ##########
 51- 80:  223 ( 9.3%) ####
 81-120:   78 ( 3.3%) #
121-200:   28 ( 1.2%)
201-500:    7 ( 0.3%)
501-999:    3 ( 0.1%)
```

### story_mention (n=55) -- tight, concentrated range
```
  0- 10:    8 (14.5%) #######
 11- 20:   22 (40.0%) ####################
 21- 30:   22 (40.0%) ####################
 31- 50:    0 ( 0.0%)
 51- 80:    3 ( 5.5%) ##
```

### interes (n=24) -- shortest, 50% under 10 chars
```
  0- 10:   12 (50.0%) #########################
 11- 20:    6 (25.0%) ############
 21- 30:    3 (12.5%) ######
 31- 50:    2 ( 8.3%) ####
 51- 80:    1 ( 4.2%) ##
```

### objecion (n=9) -- widest spread, bimodal
```
  0- 10:    2 (22.2%) ###########
 11- 20:    1 (11.1%) #####
 31- 50:    1 (11.1%) #####
 51- 80:    3 (33.3%) ################
 81-120:    1 (11.1%) #####
201-500:    1 (11.1%) #####
```

---

## Example Real Messages

### Objection Handling (longest context -- median 53 chars)
| Stefan's Response | Chars | Lead Said |
|---|---|---|
| "No creo que sea caro, puede parecerte costoso pero es el valor que aportamos con todo lo que brindamos: terraza, breathw..." | 277 | "Es un poco caro" |
| "En el proximo circulo comentaremos el tema del liderazgo y como se esta gestando esto" | 85 | "pero tbn si toca, pq luego vi q eran los lideres y..." |

### Interest Signals (shortest context -- median 10 chars)
| Stefan's Response | Chars | Lead Said |
|---|---|---|
| "Daleee" | 6 | "O lo dibujamos y collash!!" |
| "Jajaja" | 6 | "Asiii te quiero ver en historias!" |
| "Tengo taller el viernes 18 de julio!" | 36 | "Pero quiero hacerlo" |

### Story Mentions (tight range 8-28 chars)
| Stefan's Response | Chars | Lead Said |
|---|---|---|
| "Lo mismo para ti Fanny! Estaremos cruzandonos en este 2026" | 61 | "Mentioned you in their story" |
| "Oliiii" | 6 | "Mentioned you in their story" |

---

## Adaptive Length Rules (implemented)

```python
CONTEXT_LENGTH_RULES = {
    "objecion":           {"target": 53, "soft_min": 10, "soft_max": 277, "hard_max": 277},
    "pregunta_precio":    {"target": 22, "soft_min":  8, "soft_max":  46, "hard_max": 162},
    "pregunta_producto":  {"target": 21, "soft_min":  7, "soft_max":  43, "hard_max":  55},
    "pregunta_general":   {"target": 17, "soft_min":  6, "soft_max":  56, "hard_max": 101},
    "saludo":             {"target": 17, "soft_min": 11, "soft_max":  31, "hard_max":  44},
    "agradecimiento":     {"target": 22, "soft_min": 10, "soft_max":  51, "hard_max": 705},
    "interes":            {"target": 10, "soft_min":  6, "soft_max":  34, "hard_max":  61},
    "story_mention":      {"target": 18, "soft_min":  8, "soft_max":  28, "hard_max":  80},
    "casual":             {"target": 18, "soft_min":  6, "soft_max":  42, "hard_max":  73},
    "inicio_conversacion":{"target": 20, "soft_min":  8, "soft_max":  51, "hard_max": 663},
    "otro":               {"target": 23, "soft_min": 10, "soft_max":  60, "hard_max": 569},
}
```

---

## Key Proof: Length Varies by Context

| Metric | Value |
|--------|-------|
| Shortest median context | interes = 10 chars |
| Longest median context | objecion = 53 chars |
| **Ratio** | **5.3x difference** |

This definitively proves that a flat length target is inappropriate. The bot must adapt its response length to the conversation context, just as Stefan does naturally.

---

## Files Modified

| File | Change |
|------|--------|
| `services/length_controller.py` | Replaced flat config with context-adaptive `CONTEXT_LENGTH_RULES`. Added `classify_lead_context()` and `get_length_guidance_prompt()`. Maintained backward compatibility. |
| `core/dm_agent_orchestrated_v4.py` | Updated delay check from old type names to new context names. |
| `core/dm_agent_orchestrated_v3.py` | Updated delay check from old type names to new context names. |
| `tests/test_length_controller.py` | Rewritten to test new context-adaptive system. |
| `scripts/stefan_length_analysis.py` | Analysis script (connects to PostgreSQL via Railway). |
| `scripts/stefan_length_distribution.py` | Percentile distribution analysis script. |

---

## New API

### `classify_lead_context(lead_message) -> str`
Classifies what the lead said into a context category. Returns one of:
`saludo`, `pregunta_precio`, `pregunta_producto`, `pregunta_general`, `objecion`, `interes`, `agradecimiento`, `story_mention`, `casual`, `inicio_conversacion`, `otro`

### `get_length_guidance_prompt(lead_message) -> str`
Generates an LLM prompt instruction with context-appropriate length guidance. Example output:
```
[Length: You're handling an objection - explain value convincingly. Target ~53 chars (range 10-277). Complete sentences always win over length targets.]
```

### `enforce_length(response, lead_message, context=None) -> str`
Adaptive enforcement: uses context-aware hard_max + 1.5x headroom. Never truncates mid-sentence.

### `detect_message_type(lead_message) -> str`
Backward-compatible alias for `classify_lead_context()`.
