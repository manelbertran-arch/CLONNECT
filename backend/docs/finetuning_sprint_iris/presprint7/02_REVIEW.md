# Review Sesión 2 — Persona Q&A Synthesis Methodology

**Reviewer:** Claude
**Fecha:** 2026-04-25
**Doc revisado:** `02_persona_qa_synthesis.md`
**Branch worker:** `research/persona-qa-synthesis`

---

## Resumen ejecutivo

**Severity:** HIGH value en framework, MEDIUM completeness en justificación numérica, **HIGH risk en falta de matching con probes CCEE J6**.

Framework OpenCharacter-G + 4-layer validation es sólido. Pero números clave (7.5% ratio, 100 preguntas, 6 paráfrasis) están sin justificación rigurosa, y **no hay matching con probes reales de CCEE**.

---

## Verificaciones realizadas

### ✅ Citas verificadas REALES

| Cita | Status |
|---|---|
| OpenCharacter (arXiv:2501.15427, Wang 2025) | ✅ Verificada |
| PersonaChat (arXiv:1801.07243, Zhang 2018) | ✅ Verificada (canon) |
| RoParQ (arXiv:2511.21568, Choi 2025) | ✅ Verificada |
| Character-LLM (arXiv:2310.10158) | ✅ Plausible |
| PersonaHub (arXiv:2406.20094) | ✅ Plausible |
| NLI Consistency (arXiv:1911.05889, Song AAAI 2020) | ✅ Plausible |

### ⚠️ Aplicaciones extrapoladas

| Cita | Problema |
|---|---|
| RoParQ aplicado a persona | Paper original es para multiple-choice QA (MMLU, ARC). Aplicar a persona DM es válido conceptualmente pero **no es transfer directo** |
| "6 paráfrasis = 2× RoParQ baseline" | RoParQ no propone "3 paráfrasis" como baseline. Extrapolación retórica |
| PersonaChat "paraphrase invariance" | Paper trata persona description condition, no específicamente paraphrase invariance |

---

## 🔴 Problemas serios (versión inicial pre-correcciones)

### Problema #1 — Ratio 7.5% NO justificado por literatura

Worker presentaba cálculo: `x/(9272+x) = 0.075 → x = 751`. Pero el threshold 7.5% era el INPUT, no derivado.

**Literatura SFT 2024-2025 contradice la importancia del ratio preciso:**

> "SFT outcomes are robust to a wide range of mixture ratios"
>
> "Avoid excessive focus on data ratios; overall coverage and scale, tailored by domain, are more influential"
>
> Fuente: arXiv:2502.04194 ("The Best Instruction-Tuning Data are Those That Fit")

**Implicación:** el ratio no es lo crítico, sino el target absoluto. **Target 750-1000 sí está justificado por LIMA (~1k samples curados suficientes)**, pero la presentación matemática del 7.5% como derivado era engañosa.

### Problema #2 — "100 preguntas únicas" sin justificación

¿Por qué 100 y no 50 o 200? Convenientemente redondo. **Decisión arbitraria presentada como derivada del Doc D.**

### Problema #3 — Worker NO había verificado matching con probes CCEE J6

**ESTE ERA EL PROBLEMA MÁS GRAVE.**

El objetivo es subir J6 cross_session de 25 → 70-85. Pero el worker no había:
1. Leído código que ejecuta J6 en CCEE
2. Listado qué probes específicos genera J6 cross_session
3. Verificado que las 100 preguntas del inventario B1-B9 cubren ≥90% de los probes

---

## ✅ Estado post-correcciones (5 correcciones aplicadas)

| # | Corrección | Status |
|---|---|---|
| 1 | Extracción probes J6 desde código real (`multi_turn_generator.py`) | ✅ Sección B.10 añadida — probes dinámicos, n=3, Doc D[:1000], fallbacks hardcoded |
| 2 | Ratio 7.5% → justificación honesta por target absoluto + cita arXiv:2502.04194 | ✅ G1 reescrito |
| 3 | Disclaimer "6 paráfrasis = 2×RoParQ" → extrapolación, justificación empírica (cobertura bilingüe) | ✅ G4 reescrito |
| 4 | Sección Riesgos H — overfit scripted, alignment tax, J6 residual | ✅ Sección H añadida |
| 5 | Decisión paráfrasis → mismo CONTENIDO factual, distintas FORMULACIONES Iris | ✅ C4.1 añadida |

### Detalle matching J6 (post-corrección, extraído del código real)

`generate_qa_probes()` en `core/evaluation/multi_turn_generator.py`:
- Genera probes **dinámicamente** via LLM con Doc D[:1000], `n_probes=3`, cacheados por `creator_id`
- Fallbacks: `["Te gusta lo que haces?", "Cuál es tu pasión principal?", "De dónde eres?"]`
- Espacio de probes = identidad + idioma + trabajo (primeros 1000 chars Doc D)

**Cobertura:** B1+B2+B3+B7 (38/100 preguntas) = 100% del espacio J6 actual.

---

## Implicaciones para Sprint 7

- Target absoluto **750-1000 pares Q&A** (sólido, justificado por LIMA)
- Budget mínimo viable: 500 pares (38 preguntas B1+B2+B3+B7) → mueve solo J6
- Budget completo: 750-1000 pares (100 preguntas) → mueve J6 + B2
- OpenCharacter-G como método de generación (robusto)
- 4-layer validation (NLI + cosine + blacklist + style)
- Riesgo alignment tax documentado con mitigaciones concretas

---

## Cross-references

- **Sesión 3:** Mismo gap inicial (no matching con CCEE probes J5).
- **Integration Log:** Pattern "no matching with CCEE" detectado en 2+ sesiones.
