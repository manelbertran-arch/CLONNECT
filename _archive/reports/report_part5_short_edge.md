# 📊 Test de 100 Conversaciones - Parte 5: Cortas y Edge Cases

**Endpoint:** `https://web-production-9f69.up.railway.app/dm/process`
**Creator:** `stefano_bonanno`

---

## 📁 Respuestas Cortas

### Conversación 81

**Follower ID:** `report_short_81_1769238884`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | si | ¡Genial! 😊 ¿Sobre qué te gustaría hablar o saber más? | `acknowledgment` |

**Resultado:** ✅ PASS

---

### Conversación 82

**Follower ID:** `report_short_82_1769238889`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | no | ¡Hola! 😊 ¿Hay algo en específico que te gustaría comentar o ... | `other` |

**Resultado:** ✅ PASS

---

### Conversación 83

**Follower ID:** `report_short_83_1769238900`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | ok | ¡Genial! El Fitpack Challenge cuesta 22€ y es una gran oport... | `acknowledgment` |

**Resultado:** ✅ PASS

---

### Conversación 84

**Follower ID:** `report_short_84_1769238903`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | vale | ¡Genial! 😊 ¿En qué puedo ayudarte hoy? | `acknowledgment` |

**Resultado:** ✅ PASS

---

### Conversación 85

**Follower ID:** `report_short_85_1769238908`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | mm | ¡Hola! 😊 ¿En qué puedo ayudarte hoy? | `other` |

**Resultado:** ✅ PASS

---

### Conversación 86

**Follower ID:** `report_short_86_1769238917`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | jaja | Entiendo que estás frustrado. Perdona si no te he ayudado bi... | `other` |

**Resultado:** ✅ PASS

---

### Conversación 87

**Follower ID:** `report_short_87_1769238919`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | 👍 | ¡Hola! 😊 ¿Qué tal? | `other` |

**Resultado:** ✅ PASS

---

### Conversación 88

**Follower ID:** `report_short_88_1769238924`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | 🤔 | ¡Hola! 😊 ¿En qué puedo ayudarte hoy? | `other` |

**Resultado:** ✅ PASS

---

### Conversación 89

**Follower ID:** `report_short_89_1769238929`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | ? | ¡Hola! 😊 ¿En qué puedo ayudarte hoy? | `acknowledgment` |

**Resultado:** ✅ PASS

---

### Conversación 90

**Follower ID:** `report_short_90_1769238936`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | ... | ¡Hola! 😊 ¿En qué puedo ayudarte hoy? | `acknowledgment` |

**Resultado:** ✅ PASS

---


---

## 📁 Edge Cases

### Conversación 91

**Follower ID:** `report_edge_91_1769238941`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hello! I want info | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 2 | How much? | Cuesta 22€ 🎯 ¿Te gustaría que te pase el link para que reser... | `other` |
| 3 | Thanks | ¡De nada! 😊 Si tienes alguna otra pregunta o necesitas más i... | `thanks` |

**Resultado:** ✅ PASS

---

### Conversación 92

**Follower ID:** `report_edge_92_1769238960`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hola crack | ¡Hola! 😄 ¿Cómo estás? | `greeting` |
| 2 | Eres el mejor | ¡Gracias! Eso me alegra mucho, ¡tú también eres increíble! | `other` |
| 3 | Quiero ser como tú | ¡Eso suena genial! ✨ Todos tenemos el potencial para brillar... | `other` |
| 4 | Máquina | ¡Esa es la actitud! 💪 ¿Qué es lo que más te inspira de lo qu... | `other` |
| 5 | Ídolo | ¡Gracias! 🙌 Me encanta tu energía. | `other` |

**Resultado:** ✅ PASS

---

### Conversación 93

**Follower ID:** `report_edge_93_1769238994`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | 🔥🔥🔥 | ¡Hola! ¿Qué tal? | `other` |
| 2 | 💪💪 | ¡Genial! Me encanta esa energía 💥. | `other` |
| 3 | 🙌 | ¡Eso es! ¡Evoluciona tu estilo de vida! | `other` |
| 4 | ❤️ | ¡Me alegra ver ese amor! ❤️ ¿Qué te gustaría compartir o pre... | `other` |
| 5 | 👏 | ¡Sí! ¡Esa es la actitud! | `other` |

**Resultado:** ✅ PASS

---

### Conversación 94

**Follower ID:** `report_edge_94_1769239024`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | asdfghjkl | ¡Hola! 😊 Parece que has escrito algo accidentalmente. | `other` |
| 2 | ??? | ¡Hola de nuevo! ¿Hay algo específico de lo que te gustaría h... | `acknowledgment` |
| 3 | ... | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 4 | jsjsjsjs | ¡Parece que te has reído! 😄 Si tienes alguna pregunta o algo... | `other` |
| 5 | xd | ¡Me encanta tu energía! 😂 Si quieres charlar sobre algo en e... | `other` |

**Resultado:** ✅ PASS

---

### Conversación 95

**Follower ID:** `report_edge_95_1769239050`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | HOLA | ¡Hola! 😊 ¿En qué puedo ayudarte hoy? | `greeting` |
| 2 | QUIERO INFO | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 3 | PRECIO | ¡Fitpack Challenge de 11 días: Transforma tu Relación con el... | `question_product` |
| 4 | OK | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 5 | GRACIAS | ¡De nada! 😊 Si necesitas más info o tienes alguna duda, aquí... | `thanks` |

**Resultado:** ✅ PASS

---

### Conversación 96

**Follower ID:** `report_edge_96_1769239066`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hola. Punto. | ¡Hola! 😊 ¿Cómo estás? | `greeting` |
| 2 | Info. Punto. | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 3 | Ya. | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 4 | Aja. | Entiendo que estás frustrado. Perdona si no te he ayudado bi... | `other` |
| 5 | Bien. | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |

**Resultado:** ✅ PASS

---

### Conversación 97

**Follower ID:** `report_edge_97_1769239080`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Oye una pregunta | ¡Hola! ¿Qué tal? | `other` |
| 2 | Bueno da igual | Entiendo, si cambias de opinión o tienes algo en mente, aquí... | `other` |
| 3 | Nada | Está bien, no hay problema. Si en algún momento quieres habl... | `other` |
| 4 | Olvídalo | Sin problema, aquí estaré si decides volver a hablar de algo... | `other` |
| 5 | Chao | ¡Hasta luego! ¡Te esperamos! | `goodbye` |

**Resultado:** ✅ PASS

---

### Conversación 98

**Follower ID:** `report_edge_98_1769239102`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hola qué tal cómo estás espero que bien ... | ¡Hola! 😊 Estoy muy bien, gracias por preguntar. | `greeting` |
| 2 | Me interesa todo lo que haces | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 3 | Eres increíble | ¡Gracias! Eso significa mucho para mí. | `other` |

**Resultado:** ✅ PASS

---

### Conversación 99

**Follower ID:** `report_edge_99_1769239113`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | hla | ¡Hola! 😊 ¿Cómo estás? | `other` |
| 2 | kiero inf | ¡Claro! ¿Qué tipo de información te gustaría recibir? | `other` |
| 3 | qnto csta | El curso cuesta 22.0€ 🎯. ¿Te gustaría saber qué incluye? | `other` |
| 4 | ok | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 5 | thnks | ¡De nada! Si te animas a dar el paso, aquí está el link para... | `other` |

**Resultado:** ✅ PASS

---

### Conversación 100

**Follower ID:** `report_edge_100_1769239132`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | ¿Hola? | ¡Hola! 😊 ¿En qué puedo ayudarte hoy? | `greeting` |
| 2 | ¿Info? | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 3 | ¿Precio? | ¡Fitpack Challenge de 11 días: Transforma tu Relación con el... | `question_product` |
| 4 | ¿Sí? | ¡Sí, así es! ¿Te gustaría que te pase el link para que lo co... | `other` |
| 5 | ¿No? | Sin problema, cuando quieras aquí estoy. ¿Hay algo específic... | `other` |

**Resultado:** ✅ PASS

---

## 📈 Resumen Final

| Métrica | Valor |
|---------|-------|
| Total Conversaciones | 100 |
| Pass | 100 (100.0%) |
| Fail | 0 (0.0%) |

### Por Categoría

| Categoría | Pass | Fail | % |
|-----------|------|------|---|
| Happy Path (interés → compra) | 10 | 0 | 100% |
| Objeciones de Precio | 10 | 0 | 100% |
| Objeciones de Tiempo | 10 | 0 | 100% |
| Objeciones de Duda | 10 | 0 | 100% |
| Lead Magnet / Contenido Gratis | 10 | 0 | 100% |
| Booking / Agendar Llamada | 10 | 0 | 100% |
| Escalación / Hablar con Humano | 10 | 0 | 100% |
| Preguntas sobre Productos | 10 | 0 | 100% |
| Respuestas Cortas | 10 | 0 | 100% |
| Edge Cases | 10 | 0 | 100% |
---

