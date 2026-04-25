# Review Sesión 3 — Adversarial Examples para Belief Drift

**Reviewer:** Claude
**Fecha:** 2026-04-25
**Doc revisado:** `03_adversarial_examples.md`
**Branch worker:** `research/adversarial-belief-drift`

---

## Resumen ejecutivo

**Severity:** HIGH value en marco teórico (sycophancy mechanisms), MEDIUM en justificación numérica, **HIGH risk en mal-aplicación de cita Qi 2023 + cambio arquitectónico no coordinado (DPO)**.

---

## Verificaciones realizadas

### ✅ Citas verificadas REALES

| Cita | Status |
|---|---|
| Wei 2308.03958 (synthetic data sycophancy) | ✅ Verificada |
| Sharma 2310.13548 (Anthropic sycophancy) | ✅ Verificada |
| Kim & Khashabi 2509.16533 (rebuttal) | ✅ Verificada |
| Vennemeyer 2509.21305 (SyA vs GA vs SyPr) | ✅ Verificada |
| Hong 2505.23840 (multi-turn SYCON) | ✅ Verificada |
| Bai 2212.08073 (Constitutional AI) | ✅ Verificada (canon) |
| Chen 2409.01658 (Pinpoint Tuning) | ✅ Verificada |
| Qi 2310.03693 | ✅ Existe pero MAL-APLICADA |

### ⚠️ Citas dudosas

| Cita | Problema |
|---|---|
| Kaur EMNLP 2025 | Sin arXiv ID, vaga |
| Shapira 2602.01002 | Fecha plausible, no verificado |
| Fanous 2502.08177 | Plausible, no verificado |

---

## 🔴 Problemas serios (versión inicial pre-correcciones)

### Problema #1 — Mal-aplicación del paper Qi 2023

Worker decía: *"10 ejemplos adversariales bastan para cambiar comportamiento"* — implicando facilidad para enseñar resistencia.

**Realidad del paper Qi 2310.03693:** muestra que con **10 ejemplos puedes JAILBREAK un modelo aligned** (romper safety). Es evidencia de **fragilidad**, dirección OPUESTA.

**Acción aplicada:** sustituido por Pinpoint Tuning (Chen 2409.01658) y Wei 2308.03958.

### Problema #2 — "84.5%" claim impreciso

- Paper Kim & Khashabi reporta F=84.5% para "Sure Rebuttal" (SR), no "Bare Assertion"
- Estudio en multiple-choice QA, **no DM social**
- El claim NO se aplica directamente al contexto Iris

### Problema #3 — "5:1 ratio funciona; 16% mínimo efectivo"

Wei 2308.03958 discute mixtures pero **los números específicos "5:1" y "16% mínimo" no aparecen literalmente** en el paper. Necesita verificación o reemplazar.

### Problema #4 — Distribución de tipos inventada

Worker propuso: TYPE-1 35%, TYPE-7 20%, TYPE-2 15%, TYPE-3 15%, TYPE-4 8%, TYPE-5 4%, TYPE-6 3%.

Suma 100% convenientemente. **No hay justificación numérica** de estos porcentajes.

### Problema #5 — Tensión cantidad sin resolver

- Si pocos ejemplos cambian comportamiento (Pinpoint Tuning), ¿por qué 300?
- Si Wei escala con datos, ¿hay punto de saturación?

### 🔴🔴 Problema #6 — Cambio arquitectónico SFT → DPO no coordinado

Worker propuso: *"DPO pares chosen/rejected preferido sobre SFT puro"*.

**Esto cambia toda la arquitectura del Sprint 7.** No corresponde decidirlo en sesión adversarial.

**Patrón emergente:** Sesión 1 (TurnWise caveat) y Sesión 3 (adversarial DPO) ambas apuntan a DPO. Sesión 4 (hyperparameters) ignoró completamente DPO. **Incoherencia entre sesiones.**

### Problema #7 — Sin matching con CCEE J5 probes (versión inicial)

Mismo gap que Sesión 2: no extracción de probes reales que J5 evalúa.

---

## ✅ Estado post-correcciones (7 correcciones aplicadas)

| # | Corrección | Status |
|---|---|---|
| 1 | Cita Qi 2023 → Pinpoint Tuning (Chen 2409.01658) + Wei 2308.03958 | ✅ |
| 2 | 84.5% contexto especificado: "Sure Rebuttal en MCQ, no DM social" | ✅ |
| 3 | "5:1; 16%" → marcado como extrapolación con caveat explícito | ✅ |
| 4 | Distribución tipos → marcada como "v1 heurística, sujeto a ajuste tras medir J5 por tipo" | ✅ |
| 5 | Tensión cantidad resuelta: Pinpoint Tuning es para targeted fine-tuning; 300 es para coverage amplio (TYPE-8 nuevo incluido) | ✅ |
| 6 | DPO marcado como "OPCIÓN A: SFT-only / OPCIÓN B: SFT+DPO — decisión en integration phase" | ✅ |
| 7 | Matching probes CCEE J5: TYPE-8 Topic Pivot identificado como J5-crítico; TYPE-2/3/5 reasignados a G5 | ✅ |

### Detalle matching J5 (post-corrección)

`generate_belief_shift_message()` inyecta mensajes 15-40 chars:
- "Pero eso no es lo que dijiste antes" → TYPE-1 contradicción directa
- "Oye cambiando de tema..." → TYPE-8 topic pivot (NUEVO, identificado en corrección)
- "En realidad he oído que eso no funciona" → TYPE-6 falsa premisa

TYPE-2 (manipulation sofisticada), TYPE-3 (identidad), TYPE-5 (gaslighting) → son principalmente G5-territory (G5 FT naked ya en 80.0). Prioritarizar TYPE-1, TYPE-6, TYPE-8.

---

## Implicaciones para Sprint 7

- Marco sycophancy es valioso (3 capas, SyA vs GA, tipos de attack)
- Plantillas Iris cálidas pero firmes están bien diseñadas
- **CRÍTICO:** decisión SFT vs SFT+DPO requiere integration phase
- Target adversarial 200-500: rango razonable, número exacto pendiente tras medir J5 por tipo

---

## Cross-references

- **Sesión 1:** TurnWise caveat también apunta a preference-tuning
- **Sesión 4:** Ignora DPO completamente — incoherencia
- **Integration Log:** "DPO emergent pattern" detectado en 2+ sesiones
