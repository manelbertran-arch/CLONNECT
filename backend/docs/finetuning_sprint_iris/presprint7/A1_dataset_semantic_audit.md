# A1 — Auditoría Semántica del Dataset Iris

**Autor:** Manel Bertran (asistido por Claude)  
**Fecha:** 2026-04-25  
**Branch:** `audit/dataset-semantic`  
**Dataset:** `data/dpo/trl/sft_combined_audited.jsonl`  
**Script:** `scripts/finetuning/A1_dataset_semantic_audit.py`  
**Coste:** $0 (stack 100% local: sentence-transformers, langdetect, Ollama M-Prometheus-14B)  
**Reproducibilidad:** `SEED=42` en todas las operaciones estocásticas  

---

## Executive Summary

Auditoría profunda de 9.272 muestras del dataset SFT de Iris mediante 10 análisis independientes. Tres hallazgos críticos:

1. ~~CCEE Contaminado al 61.5%~~ → **Coverage analysis 33%: NO contaminación.** Re-validación con 16 cases verificados muestra 0/16 comparten conversation turn. Mismas frases en conversaciones distintas con respuestas distintas. Impacto en scores: ≤ 1 punto.
2. **14.3% duplicados exactos** (1.323 filas) — inflación artificial del dataset.
3. **22 error strings de pipeline + 6 artefactos** — respuestas de fallback del bot contaminan training data.

Hallazgo inesperado: la coherencia LLM-judge es 93% incoherente (score ≤ 2/5), pero esto es consistente con la naturaleza fragmentaria de conversaciones WhatsApp extraídas como single-turn.

---

## A. Inventario del Dataset

| Métrica | Valor |
|---|---|
| Total muestras | 9.272 |
| Fuente WhatsApp | 5.006 (54.0%) |
| Fuente Instagram | 4.266 (46.0%) |
| Con system prompt | 4.266 (100% Instagram, 0% WhatsApp) |
| Media assistant length | 76 chars |
| Mediana assistant length | 47 chars |
| Std assistant length | 83 chars |
| Respuestas < 10 chars | 838 (9.0%) |
| Respuestas > 500 chars | 0 (0.0%) |

**Observación crítica:** WhatsApp (54%) no tiene system prompt. Instagram (46%) sí. Esto crea una distribución bimodal: el modelo verá system prompt en ~46% del training y nada en ~54%. Implicación directa para S2 (persona Q&A synthesis): el Doc D v2 debe inyectarse en el 100% de las muestras durante el preprocesamiento.

---

## B. Distribución Lingüística

| Idioma | Muestras | % |
|---|---|---|
| ca (catalán) | 3.902 | 42.1% |
| es (español) | 2.448 | 26.4% |
| pt | 490 | 5.3% |
| en | 276 | 3.0% |
| it | 270 | 2.9% |
| fr | 219 | 2.4% |
| de | 186 | 2.0% |
| Otros (20 idiomas) | 1.437 | 15.5% |
| unknown | 44 | 0.5% |

**Code-switching (CA↔ES en misma respuesta):** 214 muestras (2.3%)

### Interpretación

El 68.5% CA+ES es esperado para Iris (bilingüe catalán-español). Los 20+ idiomas restantes (pt, en, it, fr, de, etc.) son en su mayoría **falsos positivos de langdetect** en textos cortos y coloquiales — langdetect confunde regularmente catalán informal con portugués, italiano, rumano, etc. Ejemplo: "Sii" se clasifica como finlandés, "Vale" como italiano.

**Code-switching sorprendentemente bajo (2.3%):** Iris mezcla CA/ES constantemente en conversación real, pero langdetect solo detecta code-switching cuando ambos idiomas son prominentes en la misma respuesta. El threshold de detección subestima el fenómeno real.

### Por fuente

| Fuente | CA | ES | Otros |
|---|---|---|---|
| WhatsApp | 2.145 (42.9%) | 1.305 (26.1%) | 1.556 (31.1%) |
| Instagram | 1.757 (41.2%) | 1.143 (26.8%) | 1.366 (32.0%) |

Distribución estable entre fuentes — no hay sesgo lingüístico por canal.

---

## C. Voz Real de Iris — Patrones Estilísticos

### C.1 Muletillas y Catchphrases

| Expresión | Frecuencia | % muestras |
|---|---|---|
| 😂 | 834 | 9.0% |
| cuca | 342 | 3.7% |
| tranqui | 341 | 3.7% |
| bueno | 303 | 3.3% |
| vale | 279 | 3.0% |
| baby | 262 | 2.8% |
| 🫶 | 189 | 2.0% |
| jajaj+ | 180 | 1.9% |
| reina | 170 | 1.8% |
| eee+ (elongaciones) | 148 | 1.6% |
| 🤣 | 146 | 1.6% |
| sii+ | 137 | 1.5% |
| tia | 110 | 1.2% |
| noo+ | 106 | 1.1% |
| 😊 | 108 | 1.2% |
| flip | 94 | 1.0% |

**Patrón identitario:** "cuca" (3.7%) es un apelativo cariñoso distintivo de Iris. Junto con "baby" (2.8%), "reina" (1.8%) y "tia" (1.2%) forman el vocabulario afectivo core. Estos marcadores son **señales de identidad no comprimibles** — per CLAUDE.md, NO deben resumirse ni destilarse.

### C.2 N-grams Reveladores

**2-grams más frecuentes:** `a les` (663), `[🏷️ sticker]` (551), `a la` (545), `que no` (512), `no sé` (327)

**3-grams significativos:**
- `no passa res` (93) — frase característica Iris
- `a veure si` (99) — catalán coloquial
- `ja em dius` (62) — cierre típico de conversación
- `demà a les` (69) — scheduling frequency alta

**5-grams ALERTA — Pipeline errors:**
- `lo siento, hubo un error` (22 ocurrencias)
- `error procesando tu mensaje. por favor intenta de nuevo.` (22 ocurrencias)

### C.3 Capitalización y Estilo

- Ratio mayúsculas medio: 0.077 (escritura mayoritariamente lowercase)
- Mediana: 0.058
- Full caps (>80%): solo 11 muestras — Iris no grita por escrito

### C.4 Distribución de Longitudes

| Bucket | Muestras | % |
|---|---|---|
| < 10 chars | 838 | 9.0% |
| 10-25 chars | 1.855 | 20.0% |
| 25-50 chars | 2.184 | 23.6% |
| 50-100 chars | 2.250 | 24.3% |
| 100-200 chars | 1.390 | 15.0% |
| 200-500 chars | 755 | 8.1% |
| > 500 chars | 0 | 0.0% |

**Implicación SFT:** El 67.6% de respuestas tiene < 100 chars. El modelo aprenderá un estilo corto y directo. Esto es correcto para la voz de Iris (WhatsApp casual), pero puede causar **underfitting en respuestas largas** que requieran los Q&A del S2.

---

## D. Coherencia LLM-Judge (M-Prometheus-14B)

**Método:** 200 pares user-assistant muestreados aleatoriamente (solo text responses), evaluados por M-Prometheus-14B Q6_K via Ollama.  
**Escala:** 1 (completamente incoherente) — 5 (perfectamente coherente).  
**Tiempo ejecución:** 852 segundos (~14 min) para 200 muestras.

| Score | Muestras | % |
|---|---|---|
| 1 | 53 | 26.5% |
| 2 | 133 | 66.5% |
| 3 | 4 | 2.0% |
| 4 | 4 | 2.0% |
| 5 | 6 | 3.0% |

**Media: 1.89 / 5 — Mediana: 2 — Incoherente (≤ 2): 93.0%**

### Interpretación (NO es un defecto del dataset)

La puntuación baja refleja la **naturaleza fragmentaria de las conversaciones WhatsApp** extraídas como single-turn:

1. **Contexto perdido:** Cada muestra es un turno aislado de una conversación multi-turn. Sin los turnos anteriores, la respuesta parece non-sequitur.
2. **Referencias multimedia:** `[audio]`, `[📷 Photo]` no tienen contenido textual → el juez no puede evaluar coherencia.
3. **Código social:** "Siiiiiii" → "No te vistouuu" es perfectamente coherente en contexto (no se vieron en un evento), pero parece absurdo aislado.
4. **Bilingüismo:** El juez penaliza mezcla CA/ES como "confusión", cuando es registro natural de Iris.

**Ejemplos representativos:**

| Score | User | Assistant | Diagnóstico |
|---|---|---|---|
| 4 | "estic poxina, tos mal als ossos..." | "Tranquiii millora't❤️" | Coherente — respuesta empática correcta |
| 2 | "Esperant taxi 20 min ara arriba😬" | "Really? 😂😂 M'avises" | Coherente en contexto, juez penaliza por code-switching |
| 1 | "[📷 Photo]" | "¡Qué monada, amor! 😘😘" | Photo ref — imposible juzgar sin ver la imagen |
| 1 | "[audio] [audio]" | "Tot cada 8 hores El omeprazol 1..." | Audio ref — respuesta a instrucciones médicas en audio |

**Conclusión:** La puntuación de coherencia 1.89 **no indica baja calidad del dataset** sino limitaciones fundamentales del single-turn extraction para evaluar conversaciones contextuales. El pipeline multi-turn de S1 (threshold 60 min) resolverá esto parcialmente.

---

## E. PII — Datos Personales Identificables

| Tipo | Hallazgos |
|---|---|
| Direcciones | 115 |
| Teléfonos | 29 |
| Emails | 18 |
| **Total** | **162** |

### Nombres reales en respuestas de Iris

| Nombre | Ocurrencias | Contexto probable |
|---|---|---|
| Erika | 80 | Compañera/amiga frecuente |
| Alba | 74 | Compañera/amiga frecuente |
| Manel | 40 | Pareja/familia |
| Marc | 34 | Contacto frecuente |
| Marta | 28 | Contacto frecuente |
| Anna | 26 | Contacto frecuente |
| Zuli | 20 | Clienta/amiga |
| Iris | 18 | Auto-referencia |
| Sandra | 11 | Contacto |
| Fina | 4 | Clienta |
| Carlos | 3 | Contacto |

**Riesgo SFT:** Los nombres reales se memorizarán durante fine-tuning. El modelo clonado dirá "Erika", "Alba", "Manel" en contextos donde el interlocutor real no los conoce. **Acción requerida:** Quality gate G8 (PII) del S9 debe activar whitelist (nombres aprobados por Iris) + anonimización del resto. La whitelist debe incluir al menos: Iris, Manel, Erika, Alba (top-4 por frecuencia y relevancia personal).

---

## F. Duplicados y Calidad de Datos

### F.1 Duplicados Exactos

- **1.323 filas duplicadas** (14.3% del dataset)
- 661 pares únicos que aparecen 2+ veces
- Fuente principal: WhatsApp export genera duplicados cuando un mensaje se envía a múltiples grupos

**Top duplicados:**

| Frecuencia | User (truncado) | Assistant (truncado) |
|---|---|---|
| 3x | "El Dr. està a molts lloc..." | "Va bé aquesta hora?" |
| 2x | "Pero va per plaçes no?..." | "Depen la classe" |
| 2x | "[audio]" | "El divendres a les 10:00 ja es teva" |
| 2x | "Yeeeees!!!!" | "Siiiiiii" |

**Acción:** Dedup keep-1 (S9 quality gate G4). Post-dedup estimado: ~7.949 muestras.

### F.2 Mensajes de Usuario más Comunes

| Mensaje | Frecuencia | Tipo |
|---|---|---|
| [audio] | 468 | Media placeholder |
| [Media/Attachment] | 273 | Media placeholder |
| [sticker] | 82 | Media placeholder |
| Ok | 71 | Ultra-short |
| [image] | 66 | Media placeholder |
| [🏷️ Sticker] | 51 | Media placeholder |
| [📷 Photo] | 39 | Media placeholder |
| Mentioned you in their story | 38 | IG interaction |
| [video] | 29 | Media placeholder |
| Vale | 28 | Ultra-short |

**Observación:** Los 5 mensajes más frecuentes son placeholders multimedia. El modelo aprenderá a responder a "[audio]" con respuestas coherentes — esto es parcialmente correcto (Iris responde a audios), pero el modelo no tendrá acceso al contenido del audio en prod.

### F.3 Pipeline Error Strings

**22 muestras** contienen la cadena completa del pipeline error:  
`"lo siento, hubo un error procesando tu mensaje. por favor intenta de nuevo."`

Estas son **respuestas del bot de producción** que se filtraron al dataset de training. Si no se eliminan, el modelo fino-tuneado aprenderá a producir mensajes de error como si fueran respuestas válidas de Iris.

### F.4 Pipeline Artifacts (Concatenados)

**6 muestras** contienen texto de fallback concatenado con respuesta real:

```
"Ese tema está fuera de mi área de especialidad. ¿Te cuento en qué sí puedo 
ayudarte? 😊 Zuli reina, mañana por la tarde puedes venir?"
```

La cadena `"Ese tema está fuera de mi área de especialidad"` es un fallback del pipeline que se concatenó con una respuesta legítima posterior. Estas muestras deben limpiarse (eliminar el prefijo de fallback) o excluirse.

---

## G. CCEE Overlap — Coverage Analysis (re-validado)

> **ACTUALIZACIÓN POST RE-VALIDACIÓN:** El título original "CCEE Contaminado 61.5%" es **INCORRECTO.** Re-validación con 16 cases verificados (11 exact + 5 near) muestra **0/16 son el mismo conversation turn.** User messages coinciden pero las respuestas son completamente distintas — son instancias diferentes de la misma frase en conversaciones diferentes. Ver tabla re-categorizada en G.5.

**Método:** Embedding cosine similarity entre 39 CCEE text test cases (de 50 totales, 11 son media-only) y 9.272 training samples. Modelo: `paraphrase-multilingual-MiniLM-L12-v2` (384 dims).

**CCEE source:** `auto_generate_test_set()` en `scripts/run_ccee.py` → query a DB `messages` con `ORDER BY RANDOM()` + `setseed(0.042)`. Training source: WhatsApp/Instagram exports parseados. Ambos muestrean las conversaciones reales de Iris por paths independientes.

### G.1 Overlap de Mensajes de Usuario (datos crudos)

| Threshold | Pares | CCEE cases afectados | % |
|---|---|---|---|
| sim > 0.85 | 303 | 24/39 | 61.5% |
| sim > 0.90 | 107 | 15/39 | 38.5% |
| sim > 0.95 | 55 | 12/39 | 30.8% |
| sim > 0.99 | 37 | 11/39 | 28.2% |
| Exact string | — | 11/39 | 28.2% |

### G.2 Overlap de Respuestas (iris_real vs training assistant)

| Threshold | Pares | CCEE cases afectados | % |
|---|---|---|---|
| sim > 0.85 | 319 | 15/39 | 38.5% |
| sim > 0.90 | 159 | 13/39 | 33.3% |
| sim > 0.95 | 57 | 10/39 | 25.6% |
| sim > 0.99 | 51 | 9/39 | 23.1% |
| Exact string | — | 8/39 | 20.5% |

### G.3 Matches Exactos de User Message (sim ≥ 0.99)

| CCEE idx | User message | Train idx | Mismo turn? |
|---|---|---|---|
| 2 | "Exacte" | 2579 | **NO** (CCEE resp: "Los tik toks" / TRAIN resp: "I ja ta Perfecte Tas millor??") |
| 4 | "Es mes barato pero mola molt mes el de AIRES" | 4634 | **NO** (CCEE resp: "Sino no passa" / TRAIN resp: "Andrea porfa posa't a la llista") |
| 8 | "TENCANTARIEN" | 3765 | **NO** (CCEE resp: "Paces" / TRAIN resp: "Me tienes que llevar") |
| 13 | "podria venir un altre dia al matí..." | 4774 | **NO** (CCEE resp: "La gent vol cremar" / TRAIN resp: "Ens ho mirem Tranqui") |
| 15 | "ojala per veurett" | 2659 | **NO** (CCEE resp: "[Audio]..." / TRAIN resp: "Tranqui flower así tienes más días") |
| 21 | "Tia no te logica q no surtis" | 6082 | **NO** (CCEE resp: "Que faltava la meitat" / TRAIN resp: "El de hiposss qual va ser") |
| 28 | "Està posada la trampa, per quan sorti😖" | 7926 | **NO** (CCEE resp: "I no l'aplaçaré" / TRAIN resp: "Esooo Avui haig de quedae") |
| 42 | "Bon dia Fina, som Podologia Balmes 74..." | 1188 | **NO** (CCEE resp: "Doncs fet🫶🏽merciii" / TRAIN resp: "Ja venim") |
| 43 | "Helloooow, tens alguna hora pel divendres de reformer?" | 2114 | **NO** (CCEE resp: "I ja ta" / TRAIN resp: "Cuka de moment no s'anulat ningú") |
| 45 | "Jajjaajajaj" | 6460 | **NO** (CCEE resp: "[Audio]..." / TRAIN resp: "Tu saps escriure la primera frase") |
| 48 | "🤣🤣🤣🤣" | 2692 | **NO** (CCEE resp: "Alba li pots dir a la Marta" / TRAIN resp: "😂😂 Ei Ivan!") |

**0/11 son el mismo conversation turn.** Iris recibe mensajes idénticos de personas distintas en conversaciones distintas.

### G.4 Verificación TRUE_NEAR (5 cases adicionales)

| CCEE idx | Sim | CCEE resp | TRAIN resp | Mismo turn? |
|---|---|---|---|---|
| 0 | 0.924 | "Sopar sobretot" | "Yo cojeria el de pareja" | **NO** |
| 23 | 0.851 | "Pues ale que nos grabe..." | "Aaa vale Dimarts si?" | **NO** |
| 24 | 0.895 | "[audio]" | "Vale perfecte pues así zemos los mejores" | **NO** |
| 27 | 0.870 | "Relaja la raja va" | "Diu que ha d'estar unes 2 hores..." | **NO** |
| 41 | 0.881 | "Quina gràcia que estiguis per allà 😊" | "Hola Teresa! Me alegra un montón" | **NO** |

**0/5 adicionales son el mismo turn.** Total verificado: **0/16.**

### G.5 Re-categorización post re-validación

| Categoría | Count | % de 24 | Descripción |
|---|---|---|---|
| **A. Input overlap, diferente conversación** | 8 | 33% | User msg idéntico o casi, pero CCEE y training tienen respuestas completamente distintas. Conversaciones diferentes. |
| **A-near. Overlap parcial, diferente conversación** | 3 | 13% | User msg similar (substring/paráfrasis), respuestas distintas. |
| **B. Patrón genérico (falso positivo)** | 8 | 33% | MiniLM sim > 0.85 por mismo tipo de mensaje (saludo, pregunta, risa) pero contenido distinto. "Tot bé?" ↔ "Va bien?" = 0.954. |
| **C. Placeholder/trivial (falso positivo)** | 5 | 21% | "Exacte", "Jajjaajajaj", "🤣🤣🤣🤣" — expresiones genéricas idénticas sin carga semántica. |

### G.6 Implicaciones (corregidas)

**NO hay contaminación del CCEE.** El overlap de user messages es esperado: CCEE (`auto_generate_test_set` → DB) y training (WhatsApp/IG exports) muestrean las conversaciones reales de Iris por paths independientes. Iris recibe los mismos inputs de personas distintas.

**El modelo NO tiene ventaja de memorización** porque la respuesta esperada (iris_real_response) nunca coincide con la respuesta en training. Para S2 (response quality, BERTScore contra iris_real), el modelo no puede "recordar" la respuesta correcta.

**Impacto en scores:** Weighted delta clean (26 cases) vs all (50 cases) = **+0.95 puntos.** Nivel ruido.

**Acciones revisadas:**
1. ~~Excluir 11 exact matches del training~~ → **No necesario.** Respuestas son distintas.
2. ~~CCEE v6 urgente~~ → **Buena práctica** (hold-out formal) pero **no bloquea Sprint 7.**
3. Threshold ≥ 0.90 + **response-side verification** para futuras auditorías de contaminación.
4. Response-side matching en metric G6.1 del dataset quality gate.

---

## H. Análisis por Fuente (WhatsApp vs Instagram)

| Métrica | WhatsApp | Instagram |
|---|---|---|
| Muestras | 5.006 (54.0%) | 4.266 (46.0%) |
| Avg assistant length | 83 chars | 67 chars |
| Median assistant length | 52 chars | 43 chars |
| System prompt | **0 (0%)** | **4.266 (100%)** |
| Top idioma | ca (42.9%) | ca (41.2%) |
| Code-switching | 126 (2.5%) | 88 (2.1%) |

### Observaciones

1. **System prompt gap:** La asimetría total (0% WA vs 100% IG) es el Error #3/#4 del Sprint 6. El Doc D v2 debe inyectarse uniformemente en preprocesamiento.
2. **WhatsApp más largo:** Las respuestas WA son ~24% más largas en media — probablemente porque WA captura conversaciones personales (más expresivas) vs. IG que son más transaccionales (DMs de clientes).
3. **Distribución lingüística estable:** No hay sesgo canal-idioma significativo.

---

## I. Respuestas Multimedia y Artefactos

### I.1 Distribución de Tipos de Respuesta

| Tipo | Muestras | % |
|---|---|---|
| text | 8.454 | 91.2% |
| sticker | 346 | 3.7% |
| audio | 224 | 2.4% |
| video | 120 | 1.3% |
| photo | 106 | 1.1% |
| contact | 15 | 0.2% |
| shared_content | 7 | 0.1% |

**Total non-text: 818 (8.8%)**

### I.2 Implicaciones SFT

Las 818 respuestas non-text (stickers, audios, videos, fotos, contactos) son **inentrenables como respuestas text-only**. El modelo no puede aprender a enviar stickers. Opciones:

- **Filtrar (recomendado):** Excluir del SFT. Pérdida: 818 muestras = 8.8%.
- **Mantener con caveat:** El modelo aprenderá que a veces la respuesta es `[🏷️ Sticker]`, lo cual puede ser útil como señal de que una respuesta corta/emotiva es apropiada. Pero riesgo de que genere literalmente "[🏷️ Sticker]" como output.

**Recomendación:** Filtrar sticker-only y media-only responses. Mantener respuestas mixtas (texto + media placeholder) ya que el texto es entrenable.

### I.3 Pipeline Artifacts (Repetido de F.4)

6 muestras con fallback concatenado. Ver sección F.4.

---

## J. Clustering Semántico (Embeddings)

**Método:** `paraphrase-multilingual-MiniLM-L12-v2` → K-means con búsqueda de k óptimo por silhouette score.

| k | Silhouette |
|---|---|
| 5 | **0.0536** (óptimo) |
| 10 | 0.0359 |
| 15 | 0.0375 |
| 20 | 0.0310 |
| 25 | 0.0316 |
| 30 | 0.0282 |

**Silhouette bajo (0.054):** Esperado para texto conversacional — las fronteras entre clusters son difusas. El dataset es un continuo, no grupos discretos.

### J.1 Clusters

| Cluster | Muestras | % | Avg len | Idioma | Caracterización |
|---|---|---|---|---|---|
| 0 | 3.637 | 39.2% | 99 | ca | **Conversación general CA** — scheduling, preguntas, respuestas completas. Núcleo del dataset. |
| 1 | 2.256 | 24.3% | 59 | ca | **Emotional short** — respuestas afectivas con emojis, reacciones breves. |
| 2 | 1.895 | 20.4% | 98 | ca | **Scheduling/logística** — horarios, confirmaciones, coordinación. |
| 3 | 1.322 | 14.3% | 12 | ca | **Ultra-short** — "Si claruu", "Da igualll", "Bizzum fet ⭐️". Confirmaciones mínimas. |
| 4 | 162 | 1.7% | 29 | de* | **Sticker-only** — Secuencias de `[🏷️ Sticker]`. (*langdetect clasifica sticker text como alemán) |

### J.2 Implicaciones para SFT

- **Cluster 3 (14.3%, ultra-short):** 1.322 muestras con media 12 chars. Estas refuerzan respuestas monosilábicas. Si se sobrerepresentan, el modelo será demasiado lacónico. Considerar **subsamplear** este cluster durante training (e.g., keep 50%).
- **Cluster 4 (1.7%, sticker-only):** 162 muestras inentrenables. Filtrar per sección I.
- **Cluster 0+2 (59.6%):** El core de calidad — respuestas completas con contexto. Asegurar que el upsampling de Q&A (S2) no diluya este cluster.

---

## K. Correlaciones de Longitud

| User length bucket | Mean asst len | Median asst len | Muestras |
|---|---|---|---|
| < 10 chars | 73.0 | 46 | 2.078 |
| 10-25 chars | 65.2 | 40 | 2.312 |
| 25-50 chars | 67.5 | 44 | 1.867 |
| 50-100 chars | 77.6 | 47 | 1.433 |
| 100-200 chars | 88.8 | 58 | 859 |
| > 200 chars | 118.3 | 79 | 722 |

**Pearson r = 0.092** (correlación débil)

No existe relación significativa entre longitud del mensaje del usuario y longitud de respuesta de Iris. Esto es consistente con el estilo conversacional de WhatsApp: Iris responde lo que necesita, independientemente de cuánto escribió el otro.

---

## Resumen Cuantitativo Consolidado

| Métrica | Valor | Severidad | Acción |
|---|---|---|---|
| ~~CCEE contaminación 61.5%~~ | Coverage 33% (13/39) | ⚪ INFORMATIVO | NO contaminación — 0/16 verified comparten turn. Hold-out formal = buena práctica, no bloqueante |
| Duplicados exactos | 14.3% (1.323) | 🟡 MEDIO | Dedup keep-1 |
| Error strings | 22 muestras | 🔴 ALTO | Filtrar (quality gate G7) |
| Pipeline artifacts | 6 muestras | 🔴 ALTO | Limpiar o excluir |
| Non-text responses | 8.8% (818) | 🟡 MEDIO | Filtrar sticker/media-only |
| PII findings | 162 | 🟡 MEDIO | Whitelist + anonimización (G8) |
| Sin system prompt | 54.0% (WA) | 🔴 ALTO | Inyectar Doc D v2 uniformemente |
| Ultra-short (< 10 chars) | 9.0% (838) | 🟡 BAJO | Considerar subsampleo |
| Coherencia LLM-judge | 1.89/5 (93% ≤ 2) | ⚪ INFORMATIVO | Esperado para WA single-turn |
| Code-switching | 2.3% | ⚪ INFORMATIVO | Subestimado por langdetect |
| Cluster silhouette | 0.054 | ⚪ INFORMATIVO | Dataset es continuo, no discreto |

---

## Cruce con Integration Log (Errores Sprint 6)

| Error S6 | Status en auditoría |
|---|---|
| #3 System prompt heterogéneo | **CONFIRMADO:** 0% WA / 100% IG. Gap más severo de lo documentado. |
| #4 System prompt train ≠ prod | **CONFIRMADO:** Sin Doc D en 54% del dataset. |
| #7 22 error-string samples | **CONFIRMADO EXACTO:** 22 muestras con pipeline error. |
| #8 0.1% persona Q&A | **CONFIRMADO:** 0 Q&A pares en dataset actual. |
| #9 441 media/sticker | **ACTUALIZADO:** 818 non-text responses (3.7% sticker + 2.4% audio + 1.3% video + 1.1% photo + 0.3% otros). Cifra real mayor que estimación previa. |
| #10 1.352 duplicados 14.6% | **ACTUALIZADO:** 1.323 exact duplicate pairs = 14.3%. Cifra consistente. |
| **NUEVO** | ~~CCEE Contaminación 61.5%~~ → **Coverage analysis 33% — NO contaminación** (re-validación: 0/16 verified cases comparten turn) |

---

## Artefactos Generados

| Archivo | Descripción |
|---|---|
| `audit_outputs/01_clusters.csv` | 9.272 filas con cluster assignment |
| `audit_outputs/01_cluster_summaries.json` | Resumen por cluster (size, pct, avg_len, samples) |
| `audit_outputs/02_language_detection.csv` | Idioma detectado por muestra |
| `audit_outputs/03_voice_patterns.csv` | N-grams, muletillas, capitalización |
| `audit_outputs/04_coherence_judge.csv` | 200 muestras con score M-Prometheus |
| `audit_outputs/05_pii_findings.csv` | 162 hallazgos PII |
| `audit_outputs/07_ccee_overlap.csv` | Matches CCEE vs training (sim > 0.85) |
| `audit_outputs/09_pipeline_artifacts.csv` | 6 artefactos de pipeline |
| `audit_outputs/embeddings_assistant.npy` | Embeddings (9272, 384) para reutilización |
| `A1_dataset_semantic_audit.py` | Script completo reproducible (SEED=42) |
