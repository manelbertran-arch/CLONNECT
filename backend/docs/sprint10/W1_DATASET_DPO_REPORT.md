# Worker W1 Report — Dataset DPO Clean

**Fecha**: 2026-05-01
**Branch**: `sprint10/w1-dpo-clean-dataset`

---

## Input

- **File**: `data/dpo/trl/dpo_iris_v2.jsonl`
- **Total pairs**: 2,499
- **Format**: `{prompt, chosen, rejected}` (todos los 2,499 pares)

---

## Bugs analizados

| Bug | Descripción | Count | % |
|-----|-------------|-------|---|
| BUG-4 | `prompt=None` | 1,162 | 46.5% |
| BUG-4b | `rejected` = texto COPILOT/sistema | 0 | 0% |
| BUG-4c | near-duplicates chosen≈rejected (Razin 2024) | 1 | 0.04% |

**BUG-4b**: no presente en v2 — o fue corregido antes o el generador no produjo texto de sistema en la columna `rejected`.

---

## Filtros aplicados (en orden)

| Filtro | Removed | % | Justificación |
|--------|---------|---|---------------|
| `prompt_invalid` (None o <3 chars) | 1,236 | 49.5% | Incluye 1,162 None + 74 prompts de solo emoji/emoji ('😍', '❤️', 'Ok') — sin contexto para DPO |
| `chosen_too_long` (>250 chars) | 134 | 5.4% | Respuestas largas no representan el estilo DM de Iris (target: <80 chars) |
| `near_duplicate` (similarity >0.85) | 1 | 0.04% | Aplicado (Razin et al. 2024: likelihood displacement en pairs near-idénticos) |
| `response_too_short` | 0 | 0% | No casos en v2 |
| `rejected_is_copilot` | 0 | 0% | No casos en v2 |
| `identical` | 0 | 0% | No casos en v2 |

---

## Output

- **File**: `data/dpo/trl/dpo_iris_v3_clean.jsonl`
- **Total clean pairs**: **1,128**
- **Retention rate**: **45.1%** (dentro del rango esperado 45-55%)
- **Tamaño**: 276 KB

---

## Quality stats

| Métrica | Valor |
|---------|-------|
| Avg prompt length | 69 chars (σ=201) |
| Avg chosen length | 42 chars (σ=45) |
| Avg rejected length | 60 chars (σ=37) |
| NULL prompts en output | 0 ✓ |

**Observación**: `chosen` (42 chars avg) es más corto que `rejected` (60 chars avg) — patrón esperado. Las respuestas auténticas de Iris son más cortas y directas que las respuestas genéricas del modelo base (que tienden a ser más largas y formales).

---

## Sample inspection (seed=42)

```
Prompt:   "Sent an attachment"
Chosen:   "Ostiaaa😂😂😂"
Rejected: "¡Hola! He recibido tu mensaje y el adjunto. ¿En qué puedo ayudarte hoy?"
→ Correcto: chosen es reacción natural de Iris, rejected es respuesta formal de chatbot

Prompt:   "Vaig fer app qe nomes em vaig apuntar"
Chosen:   "Si digamm el nom"
Rejected: "Hola, ¿podrías recordarme el nombre con el que te apuntaste para la reserva de mañana?"
→ Correcto: chosen es catalan informal, rejected es español formal

Prompt:   "Jo tinc mil agulletes del hit 🤣🤣"
Chosen:   "😂😂😂💪🏾"
Rejected: "¡Hola! Lamento escuchar que tienes agujetas. ¿Hay algo en lo que pueda ayudarte hoy?"
→ Correcto: chosen responde emocionalmente, rejected es asistente genérico
```

---

## Bugs fixed

- ✅ **BUG-4**: prompt=None → filtrado (1,162 pares)
- ✅ **BUG-4b**: rejected=COPILOT → no presente en v2 (0 casos)
- ✅ **BUG-4c**: near-duplicates → filtrado (1 par, similarity=0.985)

---

## Nota sobre dataset on-policy

El archivo `output/sprint9/dpo-onpolicy-qwen3_32b.jsonl` (1,337 pairs) mencionado en el worker prompt **no existe** en el repo. No fue incorporado. El v3_clean se basa únicamente en filtrar v2.

Si el dataset on-policy se genera en el futuro, puede concatenarse con v3_clean para producir un v4 mixto.

---

## Next step

Dataset listo para Fase B re-DPO training con Qwen3-32B.

Script generador: `scripts/finetuning/build_dpo_v3_clean.py`

Para re-generar:
```bash
cd ~/Clonnect/backend
python scripts/finetuning/build_dpo_v3_clean.py
```
