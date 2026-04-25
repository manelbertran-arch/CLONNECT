# Review Sesión 4 — Hyperparameters QLoRA

**Reviewer:** Claude
**Fecha:** 2026-04-25
**Doc revisado:** `04_hyperparameters_qlora.md`
**Branch worker:** `research/hyperparams-sft`

---

## Resumen ejecutivo

🔴 **CRITICAL (versión inicial).** Doc tenía fallo lógico serio: ignoraba hallazgos de Sesión 1 y concluía que hyperparameters Sprint 6 fueron correctos cuando NO sabemos si lo fueron (masking probablemente roto).

**Post-correcciones: ✅ Cerrado.** Worker integró DOS fallos Sprint 6, alineó con hallazgo Gemma-4, diferió DPO a Sprint 8, y añadió sweep validation proactivo.

---

## Verificaciones realizadas

### ✅ Citas verificadas REALES

| Cita | Status |
|---|---|
| QLoRA (arXiv:2305.14314, Dettmers 2023) | ✅ Verificada |
| arXiv:2512.15634 (Rathore 2025, "How Much is Too Much?") | ✅ Verificada |
| Unsloth docs | ✅ Verificada |
| Lightning AI LoRA experiments | ✅ Verificada |

---

## 🔴 Errores serios (versión inicial pre-correcciones)

### Error #1 — α=2r presentado como conclusión QLoRA

Worker dijo *"alpha=2r validado empíricamente como óptimo"* citando Lightning AI.

**Paper QLoRA original (Dettmers 2023) usa literalmente:** `r=64, α=16` (α/r = 0.25). NO α=2r.

α=2r es **heurística posterior**, no conclusión QLoRA paper. Worker mezclaba fuentes.

### Error #2 — r=16 citando QLoRA (que usa r=64)

Inconsistencia interna. Paper canon usa r=64. Worker mantenía r=16 citando QLoRA.

### Error #3 — "100% atribuible a calidad del dataset" era INSOSTENIBLE

🔴🔴 **ESTA ERA LA CONCLUSIÓN MÁS GRAVE DEL DOC.**

Razones por las que era falsa:

1. **Sesión 1 demostró que Gemma-4 NO tiene `{% generation %}` keywords**. `assistant_only_loss=True` en Sprint 6 probablemente NO funcionó como esperado.
2. **La loss inicial 10.64 puede explicarse por masking roto**, no por dataset.
3. Si masking estaba roto, **NO podemos concluir que hyperparameters fueron óptimos** — entrenaron en loss surface incorrecta.
4. **Worker NO mencionaba los hallazgos de Sesión 1.** Falta de coordinación.

### Error #4 — Worker NO mencionaba DPO en absoluto

- Sesión 1 (TurnWise caveat): "preference-tuning preserva single-turn"
- Sesión 3 (adversarial): "DPO chosen/rejected preferido"
- **Sesión 4: silencio total sobre DPO**

Si Sprint 7 hace DPO, hyperparameters cambian radicalmente (LR SFT 2e-4 → LR DPO 5e-6, factor 40×).

### Error #5 — Mini-sweep solo si falla = enfoque conformista

Sprint 7 tendrá dataset radicalmente distinto. Hyperparameters óptimos para Sprint 6 (sobre dataset ruidoso single-turn) no necesariamente óptimos para nuevo dataset.

### Error #6 — "1 epoch > 2 epochs" mal-aplicado

Lightning AI dice esto para **instruction tuning general**. Para persona específica con dataset pequeño y curado, 2-3 epochs puede funcionar mejor. Unsloth confirma "1-3 epochs recomendado" — el rango es 1-3, no fijo en 1.

---

## ✅ Estado post-correcciones (6 correcciones aplicadas)

| # | Corrección | Status |
|---|---|---|
| 1 | Consistencia con Sesión 1: "DOS fallos Sprint 6 (dataset + masking)" — conclusión "100% dataset" eliminada | ✅ |
| 2 | α=2r marcado como heurística posterior, no setting QLoRA original | ✅ |
| 3 | DPO diferido a Sprint 8 (decisión explícita y justificada) | ✅ |
| 4 | Sweep proactivo 3 configs antes de full training añadido | ✅ |
| 5 | Epochs revisado: 1-2 epochs para dataset curado <15k | ✅ |
| 6 | r=16 mantenido con justificación honesta (compromiso recursos, no paper canon) | ✅ |

### Decisión final post-corrección: r=16, α=32, LR=2e-4, 1-2 epochs + sweep validation

```
Config A (Sprint 6 corregido): r=16, LR=2e-4, 1 epoch
Config B (más capacity):       r=32, LR=1e-4, 2 epochs
Config C (mínima capacity):    r=8,  LR=2e-4, 3 epochs
→ Sweep en val set ANTES de full training
```

---

## Implicaciones para Sprint 7

- Verificar masking Gemma-4 ANTES de evaluar hyperparameters
- DPO diferido a Sprint 8 — Sprint 7 es SFT-only
- Sweep proactivo en 3 configs sobre validation set
- Loss inicial esperada Sprint 7: 1.5–2.5 (vs 10.64 Sprint 6 con masking roto)

---

## Cross-references

- **Sesión 1:** Hallazgo crítico Gemma-4 masking — ahora integrado ✅
- **Sesión 3:** DPO — diferido explícitamente a Sprint 8 ✅
- **Integration Log:** Patrón "sesiones sin cross-checking" detectado y corregido
