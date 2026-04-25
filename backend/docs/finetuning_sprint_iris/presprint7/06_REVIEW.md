# Review Sesión 6 — Chat template Gemma4-31B alignment (I6)

**Fecha review:** 2026-04-25
**Documento revisado:** 06_chat_template_gemma4.md
**Branch original:** research/chat-template-gemma4
**Veredicto:** 🟢🟢 EXCELENTE (HIGHEST value del presprint en Wave 1)

---

## Resumen ejecutivo

Sesión 6 diagnostica y resuelve el bug central de Sprint 6 (chat template mismatch) con evidencia técnica sólida y validación oficial Google AI Docs. Cambio mínimo (3 líneas de código), impacto máximo (resuelve C3 leakage + degradación J6 + degradación H1).

---

## Validación con fuentes primarias

### ✅✅ Decisión Opción C VALIDADA por Google AI Docs

Fuente: Gemma 4 model card / prompt formatting (https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4)

> "When fine-tuning larger Gemma models with a dataset that does not include thinking, you can achieve better results by adding the empty channel to your training prompts."

Esto es **literalmente la Opción C del worker.** Google mismo recomienda este fix.

### ✅ Comportamiento Gemma-4-31B confirmado

Fuente: Google AI model card

> "For all models except for the E2B and E4B variants, if thinking is disabled, the model will still generate the tags but with an empty thought block: <|channel>thought\n<channel|>[Final answer]"

Confirma diagnóstico: el modelo SIEMPRE genera CHANNEL_PREFIX, incluso con thinking desactivado.

### ✅ Template oficial Gemma-4-31B-it confirmado

Fuente: HuggingFace Discussion #53

```jinja
{%- if add_generation_prompt -%}
    {{- '<|turn>model\n' -}}
    {%- if not enable_thinking | default(false) -%}
        {{- '<|channel>thought\n<channel|>' -}}
    {%- endif -%}
{%- endif -%}
```

Confirma exactamente el diagnóstico del mismatch.

---

## Errores críticos detectados pre-corrección

### EC-1: Cálculo de probabilidad incorrecto (magnitud 10×)

Worker decía:
> "loss 10.64 ≈ asignar p=0.00024 por token"

Cálculo correcto:
- exp(-10.64) = 2.4×10⁻⁵ = 0.000024
- Worker reportó 0.00024 (error 10×)

Implicación: error de magnitud que mal-interpreta gravedad real del bug Sprint 6.

### EC-2: Cita Google AI Docs ausente del documento original

La cita "add the empty channel to your training prompts" es la validación oficial más fuerte. No estaba en el doc original.

### EC-3: Sin tabla alertas go/no-go

Worker no proporcionaba criterios cuantitativos para abort/continue durante training Sprint 7.

### EC-4: Workaround Unsloth strip_thinking ausente

HF Discussion #1 documenta que strip_thinking macro stripea target turns. Sin workaround, Opción C podría fallar silenciosamente.

### EC-5: Sin coordinación con Sesión 5 (loss inicial)

Sesión 5 decía "loss inicial OK Gemma-4: 12.4-12.6" → INCORRECTO.
Sesión 6 dice "loss inicial 1.5-2.5" → CORRECTO.

Sin reconciliación documentada, contradicción persiste.

---

## Correcciones aplicadas (5)

| # | Corrección | Status |
|---|---|---|
| 1 | Probabilidad: 0.00024 → 2.4×10⁻⁵ + explicación nats | ✅ Aplicada |
| 2 | Tabla alertas go/no-go (steps 1/10/50/100) | ✅ Aplicada |
| 3 | Quote Google AI Docs en Sección D.2 | ✅ Aplicada |
| 4 | Reconciliación con Sesión 5 documentada | ✅ Aplicada |
| 5 | Workaround strip_thinking en A.4 | ✅ Aplicada |

---

## Hallazgos técnicos clave

### Bug Sprint 6 root cause

| Contexto | Secuencia vista por modelo |
|---|---|
| Training labels | `<\|turn>model\n{respuesta}` |
| Inference serving | `<\|turn>model\n<\|channel>thought\n<channel\|>` → genera |

Mismatch causa: C3 leakage, J6 -8.2, H1 -18, loss 10.64.

### Fix Sprint 7 (3 líneas)

```python
# ANTES
response_part = "<|turn>model\n"
# DESPUÉS
CHANNEL_PREFIX = "<|channel>thought\n<channel|>"
response_part = "<|turn>model\n<|channel>thought\n<channel|>"
# + añadir CHANNEL_PREFIX a cada turn assistant en formatting_prompts_func
```

### Loss esperada Sprint 7

| Step | Umbral | Acción |
|---|---|---|
| 1 | > 12.0 | 🔴 ABORT — setup error |
| 10 | > 4.0 | 🟠 REVISAR dataset prep |
| 50 | > 5.0 | 🔴 ALERTA masking |
| 100 | > 8.0 | 🔴 ABORT — mismo bug Sprint 6 |
| Final | 0.8-1.5 | ✅ Saludable |

---

## Pre-flights Sprint 7 derivados

- `verify_sprint7_alignment.py` — 5 checks G1-G5 antes de training
- `verify_sprint6_masking.py` — reproduce bug Sprint 6 (regression test)

---

## Coherencia cross-sesión

- ✅ Coherente con S1 (Gemma-4 sin keywords {% generation %})
- ✅ Coherente con S5 post-corrección (loss 1.5-2.5)
- ✅ Coherente con S7 (relevante solo si Gemma4 gana evaluación; si Qwen3 gana, fix de S6 es histórico)

---

## Implicaciones cross-Sesión 7

Si gate Sesión 7 invertido decide Qwen3:
- TRL auto-patch resuelve masking automáticamente
- Chat template `<|im_start|>` es simple, sin tokens nuevos
- **Toda la complejidad de Sesión 6 deja de aplicar**
- Sesión 6 pasa a ser documentación histórica del bug Sprint 6

Si gate decide Gemma4:
- Sesión 6 es fundamental
- 3 líneas + scripts pre-flight obligatorios
- Workaround strip_thinking activo

---

## Severity final

🟢🟢 HIGHEST value Wave 1.

Resuelve bug central Sprint 6 con fix minimal validado oficialmente.
