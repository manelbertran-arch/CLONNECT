# Contenido Dimension Analysis — DPRF Iteration 2

## 10 Worst Contenido Scores (from LLM-judge baseline_v2)

| ID | Type | Score | Error Type | Root Cause |
|----|------|-------|-----------|------------|
| conv_015 | lead_caliente | 1 | (a) hallucination | Bot invented "perrito muerto" — lead talked about work/shopping |
| conv_004 | saludo | 1 | (b) wrong response | Bot said "no me ha llegado nada" — lead sent attachment, GT is reaction "Ostiaaa😂😂😂" |
| conv_014 | lead_caliente | 1 | (c) generic | Bot response OK-ish but judge scored 1 — likely judge error (bot="A ti, cariño" vs GT="De nada, cariño") |
| conv_016 | lead_caliente | 2 | (b) wrong response | Lead said "VINC SÚPER RAPID" (arriving fast), bot treated as product interest |
| conv_017 | audio | 3 | (d) no info | Lead sent sticker, bot just "Jajajajajajajaja" with no context |
| conv_003 | saludo | 4 | (c) generic | "Que te trae por Buenos Aires?" — formal/generic vs GT's "Que haces babyyyy? 😘" |
| conv_008 | precio | 4 | (b) wrong response | Lead said "abril a les 13:00" (scheduling), bot responded "Abril, cariño, ¿qué pasa" |
| conv_001 | personal | 5 | (c) generic | "no te preocupes, te ayudo yo" — generic vs GT referencing specific "bambas" |
| conv_002 | saludo | 5 | (c) generic | "Hola Irene Què tal" — flat vs GT's "Mare meva Irene! Quina gràcia!! 😍" |
| conv_007 | precio | 5 | (b) wrong response | Lead shared workshop link, bot "Gràcies x el link" vs GT's enthusiasm about workshop |

## Error Distribution

| Error Type | Count | % |
|-----------|-------|---|
| (a) Hallucination | 1 | 10% |
| (b) Wrong response / ignores question | 4 | 40% |
| (c) Generic / no personality | 4 | 40% |
| (d) No info available | 1 | 10% |

## Root Causes

### (a) Hallucination (conv_015)
The GPT-4o-mini fallback invented "perrito muerto" when Gemini failed.
**Already fixed**: Gemini retry + anti-hallucination guard on fallback.

### (b) Wrong response (conv_004, conv_016, conv_008, conv_007)
The LLM misinterprets the lead's message:
- conv_004: "Sent an attachment" → bot thinks nothing arrived
- conv_016: "VINC SÚPER RAPID" means "I'm coming super fast" → bot treats as product name
- conv_008: "abril a les 13:00" → scheduling reference misread
- conv_007: Workshop link shared → bot thanks for link instead of reacting with enthusiasm

**Root cause**: The LLM doesn't have enough conversational context to understand
Catalan slang and abbreviated messages. History is there (20 msgs) but the LLM
doesn't always parse context correctly.

### (c) Generic (conv_003, conv_001, conv_002, conv_014)
The LLM generates a valid but personality-less response:
- Uses formal phrases instead of Iris's vocabulary
- Doesn't reference specifics from the conversation
- Missing emojis and code-switching

**Root cause**: Doc D rules exist but get diluted in long prompts.

### (d) No info (conv_017)
Lead sent a sticker after audio conversation about collaboration.
Bot just laughed — couldn't infer what the sticker meant.
**This is acceptable** — stickers have no text content.
