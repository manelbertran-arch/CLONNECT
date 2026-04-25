# Review Sesión 1 — Multi-turn Dataset Construction

**Reviewer:** Claude (double-check riguroso vs fuentes primarias)
**Fecha:** 2026-04-25
**Doc revisado:** `01_multi_turn_construction.md`
**Branch worker:** `research/multi-turn-construction`

---

## Resumen ejecutivo

**Severity general:** HIGH value, MEDIUM completeness inicial → cerrada con HIGH value tras correcciones del worker.

El doc aporta 2 hallazgos extremadamente valiosos (TurnWise method + bug TRL #3781) que solo justifican la sesión. Tras correcciones, el doc está en buen estado para Sprint 7.

---

## Verificaciones realizadas

### ✅ Citas verificadas REALES

| Cita | Status | Notas |
|---|---|---|
| TurnWise (arXiv:2603.16759) | ✅ Verificada | Graf et al. UW + Allen AI, March 2026. Claim "+12% mejora con 10k MT" es exacto |
| TRL Issue #3781 | ✅ Verificada | Bug crítico real: `assistant_only_loss=True` + `use_liger_kernel=True` → silent failure |
| Chua 2024 (60min boundary) | ✅ Verificada (post-corrección) | Blog Medium June 20, 2024 — no arxiv pero fuente real |
| Pleus-Braun 2023 | ✅ Verificada (post-corrección) | LinkedIn Pulse June 18, 2023 (year corregido de 2024 a 2023) |

### 🔴 Bugs adicionales detectados que worker NO mencionó inicialmente

| Issue | Bug | Estado |
|---|---|---|
| TRL #3728 | `assistant_only_loss=True` + `packing=True` → silent failure | Cerrado, FIX requerido |
| TRL #3927 | `assistant_only_loss=True` + sequence > `max_length` → silent failure | Abierto |
| TRL #3768 | `assistant_only_loss=True` + `IterableDataset` → crash | Cerrado |

### 🔴🔴 HALLAZGO CRÍTICO — Gemma-4 chat template

Según HuggingFace docs oficiales:
> "assistant_only_loss requires the chat template to include `{% generation %}` and `{% endgeneration %}` keywords. For known model families (e.g. Qwen3), TRL automatically patches the template. For other models, check that your chat template includes these keywords."

**Verificación del worker (post-corrección):** Gemma-4 chat template **NO contiene** `{% generation %}` keywords.

**Implicaciones:**
1. En Sprint 6, `assistant_only_loss=True` probablemente NO funcionó como esperado
2. La loss inicial 10.64 puede explicarse por masking roto (entrenó sobre toda la secuencia)
3. C3 leakage (modelo emite Doc D content) es coherente con haber visto Doc D como output, no como context
4. **Confirma con evidencia técnica la hipótesis "chat template mismatch" del post-mortem Sprint 6**

---

## Estado correcciones tras review

| Punto | Status |
|---|---|
| 1. Gemma-4 `{% generation %}` verification | ✅ Añadida en A.6 con código + 3 mitigaciones |
| 2. Bugs TRL adicionales (#3728, #3927, #3768) | ✅ Añadidos como tabla |
| 3. Justificación numérica target 1,600-2,400 | ✅ 565 leads × 6 convs × 50% filtrado = ~1,695 |
| 4. Citas Chua/Pleus | ✅ URLs exactas, year corregido en Pleus |
| 5. TurnWise +12.8 con caveat | ✅ "SFT degrada single-turn (IFEval, MMLU). Preference-tuning (+9.2) preserva single-turn" |

---

## Implicaciones para Sprint 7

### Forbidden flags (NO usar en train_modal.py Sprint 7)

```python
# ❌ NO permitido (causan silent failures con assistant_only_loss=True)
SFTConfig(
    use_liger_kernel=True,    # Bug #3781
    packing=True,              # Bug #3728
    # IterableDataset           # Bug #3768
)

# ⚠️ Verificar antes
assert all(len(tokenizer.apply_chat_template(s["messages"])) <= max_length
           for s in dataset)  # Bug #3927
```

### Pre-flight check obligatorio

```python
from transformers import AutoTokenizer
t = AutoTokenizer.from_pretrained("unsloth/gemma-4-31B-it")
has_gen = "{% generation %}" in t.chat_template
print("Gemma4 generation keywords:", has_gen)
# Si False → aplicar patch manual o usar DataCollatorForCompletionOnlyLM
```

### Decisión arquitectónica abierta

**TurnWise caveat:** SFT con MT data degrada single-turn. Preference-tuning preserva.

→ **Sprint 7 podría requerir SFT base + DPO refinement** (ver Integration Log)

---

## Acciones pendientes

Ninguna en este doc. Cerrado con corrección completa.

---

## Cross-references

- **Sesión 4 (hyperparameters):** Ignora este hallazgo de masking roto. Conclusión "100% culpa del dataset" es insostenible. Ver `04_REVIEW.md`.
- **Integration Log:** Patrón emergente "DPO" inicia aquí (TurnWise caveat).
