# A2.5 Reproduction Control — Veredicto: AMBIGUO

## Contexto
- P1 OFF baseline (19-abr 22:14, main/74a92cd8): 66.4
- A2.5 POST-hotfix original (19-abr 12:55, 885fe454): 72.6
- Delta observado bruto: -6.2 puntos

## Hipótesis testada
CCEE protocolo estándar 50×3+MT sobre commit 885fe454 ejecutado HOY (20-abr 10:50).

## Resultado triangular

| Medición | Commit | Timestamp | Composite |
|---|---|---|---|
| A2.5 original | 885fe454 | 19-abr mediodía | 72.6 |
| P1 main OFF | 74a92cd8 | 19-abr noche | 66.4 |
| AA repro control | 885fe454 | 20-abr mañana | 68.9 |

Δ repro vs original: -3.7 (sub-umbral 4.0)
Δ P1 vs repro: -2.5 (sub-umbral 4.0)

## Por dimensión

| DIM | orig | P1 | repro | R-P1 |
|---|---|---|---|---|
| B  | 63.5 | 57.8 | 57.2 | -0.6 |
| G5 | 100.0 | 80.0 | 100.0 | +20.0 |
| H  | 82.0 | 72.0 | 78.0 | +6.0 |
| J6 | 90.0 | 100.0 | 100.0 | 0.0 |
| J_new | 72.0 | 72.6 | 70.9 | -1.7 |
| J_old | 54.5 | 29.5 | 54.9 | +25.4 |
| K  | 95.0 | 72.5 | 84.3 | +11.8 |
| S1 | 79.4 | 72.3 | 74.1 | +1.8 |
| S2 | 66.3 | 47.0 | 46.4 | -0.6 |
| S3 | 62.5 | 64.6 | 66.5 | +1.9 |
| S4 | 61.4 | 66.9 | 60.2 | -6.7 |

MT: orig=80.3, P1=73.1, repro=76.9

## Interpretación
**AMBIGUO**: ni pura variance ni pura regresión de código.

- **S2 (Response Quality)**: baja en P1 (47.0) Y repro (46.4) vs original (66.3) — sugiere que la medición original capturó un día de OpenRouter especialmente favorable. Variance real.
- **K (Context Retention)**: orig=95, repro=84.3, P1=72.5 — degradación gradual, posible componente de código (15 merges posteriores).
- **G5 + J_old**: repro=orig≠P1 — sugiere algo en main actual afecta estas métricas.
- **Δ P1-repro = -2.5 pts**: solo 2.5 puntos de main vs mismo commit antiguo. Dentro de ruido razonable para A/B.

## Conclusión práctica
La diferencia P1 vs A2.5 original (-6.2) es principalmente **variance inter-sesión** (~3.7 pts, ~60%) con posible **regresión de código menor** (~2.5 pts, ~40%).

Para el A/B distill: P1 (66.4) vs P2 (mismo protocolo, ON) es el par de referencia válido. La comparación con A2.5 original (72.6) no es confiable como baseline absoluto.

## Próximo paso
Lanzar Worker P2 (USE_DISTILLED_DOC_D=true) para completar el A/B distill.
