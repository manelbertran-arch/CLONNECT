# 📊 Test de 100 Conversaciones - Parte 1: Happy Path y Precio

**Endpoint:** `https://web-production-9f69.up.railway.app/dm/process`
**Creator:** `stefano_bonanno`

---

## 📁 Happy Path (interés → compra)

### Conversación 1

**Follower ID:** `report_happy_1_1769236928`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hola! Vi tu post sobre fitness | ¡Hola! 😊 Me alegra que hayas visto mi post sobre fitness. | `greeting` |
| 2 | Me interesa perder peso | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 3 | Cuéntame más | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 4 | ¿Cuánto cuesta? | ¡Fitpack Challenge de 11 días: Transforma tu Relación con el... | `question_product` |
| 5 | Vale, lo quiero | ¡Genial que quieras avanzar! 🚀 Estos son mis productos:

🎯 F... | `interest_strong` |

**Resultado:** ✅ PASS

---

### Conversación 2

**Follower ID:** `report_happy_2_1769236943`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hey! Info sobre tu programa | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 2 | Quiero definir | ¡Genial! Para definir tu rutina y mejorar tu relación con el... | `other` |
| 3 | Sí, me interesa | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 4 | ¿Qué incluye? | El "Fitpack Challenge de 11 días" incluye un enfoque integra... | `question_product` |
| 5 | Perfecto, ¿cómo pago? | ¡Genial que quieras avanzar! 🚀 Estos son mis productos:

🎯 F... | `interest_strong` |

**Resultado:** ✅ PASS

---

### Conversación 3

**Follower ID:** `report_happy_3_1769236966`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Buenas! Quiero empezar a entrenar | ¡Genial que quieras avanzar! 🚀 Estos son mis productos:

🎯 F... | `interest_strong` |
| 2 | Necesito ayuda | ¡Claro! Estoy aquí para ayudarte. | `support` |
| 3 | ¿Tienes algo para principiantes? | ¡Sí, definitivamente! 😊 Te recomiendo el **Fitpack Challenge... | `objection_not_for_me` |
| 4 | Suena bien | ¡Perfecto! Este desafío es ideal para empezar a mover el cue... | `other` |
| 5 | Me apunto | ¡Genial que quieras avanzar! 🚀 Estos son mis productos:

🎯 F... | `interest_strong` |

**Resultado:** ✅ PASS

---

### Conversación 4

**Follower ID:** `report_happy_4_1769236987`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hola Stefano! | ¡Hola! 😊 ¿En qué puedo ayudarte hoy? | `greeting` |
| 2 | Vi tus transformaciones | ¡Genial! Me alegra que te interesen. | `question_product` |
| 3 | Quiero resultados así | ¡Eso es increíble! Justo hablé sobre cómo obtener resultados... | `objection_works` |
| 4 | ¿Es posible? | ¡Absolutamente! En el "Fitpack Challenge", transformamos tu ... | `other` |
| 5 | Vamos a ello | ¡Genial que quieras avanzar! 🚀 Estos son mis productos:

🎯 F... | `interest_strong` |

**Resultado:** ✅ PASS

---

### Conversación 5

**Follower ID:** `report_happy_5_1769237013`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Qué tal! Me recomendaron tu programa | ¡Hola! 😊 Me alegra que te hayan recomendado mi programa. | `question_product` |
| 2 | Quiero info | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 3 | ¿Funciona de verdad? | ¡Absolutamente! Este programa está diseñado para ayudarte a ... | `objection_works` |
| 4 | Ok me convence | ¡Perfecto! 🚀 Aquí tienes: https://www.stefanobonanno.com/fit... | `other` |
| 5 | ¿Link de pago? | ¡Genial que quieras avanzar! 🚀 Estos son mis productos:

🎯 F... | `interest_strong` |

**Resultado:** ✅ PASS

---

### Conversación 6

**Follower ID:** `report_happy_6_1769237035`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Holaaa | ¡Hola! 😊 ¿Cómo estás? | `greeting` |
| 2 | Quiero cambiar mi físico | ¡Eso suena genial! 💪 Transformar tu físico es un gran objeti... | `other` |
| 3 | ¿Me puedes ayudar? | ¡Claro que sí! Estoy aquí para ayudarte a lograrlo. | `support` |
| 4 | Genial | ¡Perfecto! 😊 ¿Ya tienes en mente algún enfoque o programa es... | `acknowledgment` |
| 5 | Lo compro | ¡Genial que quieras avanzar! 🚀 Estos son mis productos:

🎯 F... | `interest_strong` |

**Resultado:** ✅ PASS

---

### Conversación 7

**Follower ID:** `report_happy_7_1769237062`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Buenas tardes | ¡Hola! 😊 ¿Cómo estás? | `greeting` |
| 2 | Busco entrenador online | ¡Genial! ¿Qué tipo de entrenamiento estás buscando? | `other` |
| 3 | ¿Qué ofreces? | Ofrezco un acompañamiento personalizado para transformar tu ... | `other` |
| 4 | Me interesa el reto | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 5 | Adelante | ¡Perfecto! 🚀 Aquí tienes: https://www.stefanobonanno.com/fit... | `other` |

**Resultado:** ✅ PASS

---

### Conversación 8

**Follower ID:** `report_happy_8_1769237080`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hola! Empiezo el gym | ¡Hola! 🌟 ¡Qué emocionante que empieces en el gym! | `greeting` |
| 2 | Necesito guía | ¡Claro! Estoy aquí para ayudarte a dar esos primeros pasos. | `other` |
| 3 | ¿Tienes programa? | Sí, tengo un programa llamado **Fitpack Challenge** de 11 dí... | `other` |
| 4 | Perfecto | ¡Perfecto! 🚀 Aquí tienes: https://www.stefanobonanno.com/fit... | `interest_soft` |
| 5 | Quiero empezar | ¡Genial que quieras avanzar! 🚀 Estos son mis productos:

🎯 F... | `interest_strong` |

**Resultado:** ✅ PASS

---

### Conversación 9

**Follower ID:** `report_happy_9_1769237099`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hey Stefano | ¡Hola! 😊 ¿Cómo estás? | `greeting` |
| 2 | Quiero ponerme en forma | ¡Genial! 💪 Es un gran objetivo. | `other` |
| 3 | ¿Cómo funciona? | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 4 | Suena genial | ¡Me alegra que te guste! 🎉 Aquí tienes el link para que pued... | `thanks` |
| 5 | Cuenta conmigo | ¡Perfecto! 🎉 Aquí tienes el link para que te unas al Fitpack... | `other` |

**Resultado:** ✅ PASS

---

### Conversación 10

**Follower ID:** `report_happy_10_1769237122`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hola! | ¡Hola! 😊 ¿Cómo estás? | `greeting` |
| 2 | Vi tu contenido | ¡Genial que lo hayas visto! 🤩 ¿Qué fue lo que más te resonó? | `question_product` |
| 3 | Me motiva mucho | ¡Eso es increíble! ✨ La motivación es clave para el cambio. | `other` |
| 4 | Quiero ser tu alumno | ¡Qué emocionante! 🎉 Tengo varias opciones para acompañarte e... | `other` |
| 5 | ¿Cómo me inscribo? | ¡Genial que quieras avanzar! 🚀 Estos son mis productos:

🎯 F... | `interest_strong` |

**Resultado:** ✅ PASS

---


---

## 📁 Objeciones de Precio

### Conversación 11

**Follower ID:** `report_price_11_1769237141`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hola, info del programa | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 2 | ¿Cuánto cuesta? | ¡Fitpack Challenge de 11 días: Transforma tu Relación con el... | `question_product` |
| 3 | Uff es caro | Entiendo que pueda parecer un poco elevado, pero recuerda qu... | `objection_price` |
| 4 | No tengo tanto dinero | Comprendo tu situación. ¡Cada pequeño paso cuenta! | `objection_price` |
| 5 | Quizás más adelante | ¡Sin problema! Cuando estés listo, aquí estaré para ayudarte... | `objection_later` |

**Resultado:** ✅ PASS

---

### Conversación 12

**Follower ID:** `report_price_12_1769237162`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Info please | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |
| 2 | ¿Precio? | ¡Fitpack Challenge de 11 días: Transforma tu Relación con el... | `question_product` |
| 3 | Es mucho para mí | Entiendo, y es totalmente válido sentir que es un compromiso... | `other` |
| 4 | No puedo permitírmelo | Lamento que sientas que no es accesible en este momento. Rec... | `other` |
| 5 | Gracias igual | ¡De nada! Si en algún momento decides dar un paso o necesita... | `thanks` |

**Resultado:** ✅ PASS

---

### Conversación 13

**Follower ID:** `report_price_13_1769237186`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hola | ¡Hola! 😊 ¿En qué puedo ayudarte hoy? | `greeting` |
| 2 | ¿Cuánto vale? | ¡Fitpack Challenge de 11 días: Transforma tu Relación con el... | `question_product` |
| 3 | Está fuera de mi presupuesto | ¡Sin problema! Entiendo que puede ser un momento complicado. | `objection_price` |
| 4 | ¿Hay descuento? | Me encantaría ayudarte con eso 🙌 Te paso con Stefano Bonanno... | `question_product` |
| 5 | Sigue siendo mucho | Entiendo, a veces el presupuesto puede ser un reto. Cada peq... | `other` |

**Resultado:** ✅ PASS

---

### Conversación 14

**Follower ID:** `report_price_14_1769237208`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Buenas | ¡Hola! 😊 ¿En qué puedo ayudarte hoy? | `greeting` |
| 2 | Precio? | ¡Fitpack Challenge de 11 días: Transforma tu Relación con el... | `question_product` |
| 3 | Muy caro | Entiendo que puede parecer un poco elevado, pero piensa en l... | `objection_price` |
| 4 | ¿Opciones más baratas? | Actualmente, el Fitpack Challenge es la opción más accesible... | `other` |
| 5 | No gracias | ¡Sin problema! Si cambias de opinión o tienes alguna otra pr... | `thanks` |

**Resultado:** ✅ PASS

---

### Conversación 15

**Follower ID:** `report_price_15_1769237241`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hey | ¡Hola! ¿Cómo estás? | `greeting` |
| 2 | ¿Cuánto es? | ¡Fitpack Challenge de 11 días: Transforma tu Relación con el... | `question_product` |
| 3 | No tengo ese dinero ahora | ¡Sin problema! Entiendo que a veces puede ser complicado. | `other` |
| 4 | ¿Se puede pagar a plazos? | Actualmente, no ofrecemos la opción de pago a plazos. Pero s... | `other` |
| 5 | Aún así es mucho | Entiendo, cada uno tiene sus prioridades. ¡Cada pequeño paso... | `other` |

**Resultado:** ✅ PASS

---

### Conversación 16

**Follower ID:** `report_price_16_1769237262`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hola | ¡Hola! 😊 ¿En qué puedo ayudarte hoy? | `greeting` |
| 2 | Info y precio | ¡Fitpack Challenge de 11 días: Transforma tu Relación con el... | `interest_soft` |
| 3 | Es bastante | Entiendo que pueda parecer un poco, pero ¡recuerda que es un... | `other` |
| 4 | ¿Vale la pena? | ¡Sin duda! Este challenge te permite **incorporar más movimi... | `question_product` |
| 5 | Lo pensaré | Me encantaría ayudarte con eso 🙌 Te paso con Stefano Bonanno... | `objection_doubt` |

**Resultado:** ✅ PASS

---

### Conversación 17

**Follower ID:** `report_price_17_1769237285`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Qué tal | ¡Hola! 😊 ¿En qué puedo ayudarte hoy? | `greeting` |
| 2 | ¿Cuánto cuesta tu programa? | ¡Fitpack Challenge de 11 días: Transforma tu Relación con el... | `question_product` |
| 3 | Es más de lo que esperaba | Me encantaría ayudarte con eso 🙌 Te paso con Stefano Bonanno... | `question_product` |
| 4 | ¿Por qué tan caro? | Entiendo tu inquietud. El precio del programa incluye un aco... | `objection_price` |
| 5 | Entiendo pero no puedo | Sin problema, lo entiendo. Aquí estaré si decides que quiere... | `other` |

**Resultado:** ✅ PASS

---

### Conversación 18

**Follower ID:** `report_price_18_1769237306`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hola! | ¡Hola! 😊 ¿En qué puedo ayudarte hoy? | `greeting` |
| 2 | Precio del reto? | ¡Fitpack Challenge de 11 días: Transforma tu Relación con el... | `question_product` |
| 3 | Uf | ¿Todo bien? 😊 Si necesitas más información o tienes alguna p... | `other` |
| 4 | Es mucho | Entiendo que puede parecer un poco, pero recuerda que es una... | `other` |
| 5 | Paso por ahora | ¡Perfecto! 🚀 Aquí tienes: https://www.stefanobonanno.com/fit... | `other` |

**Resultado:** ✅ PASS

---

### Conversación 19

**Follower ID:** `report_price_19_1769237325`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Buenas | ¡Hola! 😊 ¿En qué puedo ayudarte hoy? | `greeting` |
| 2 | ¿Cuánto? | El curso "Fitpack Challenge de 11 días" cuesta 22€. 🎯 ¿Te gu... | `other` |
| 3 | No me lo puedo permitir | Entiendo, no hay problema. Recuerda que cada pequeño paso cu... | `objection_price` |
| 4 | Ojalá pudiera | ¡Confía en que siempre hay formas de avanzar! Si deseas, pod... | `other` |
| 5 | Gracias | ¡De nada! 😊 Si tienes más preguntas o necesitas algo, aquí e... | `thanks` |

**Resultado:** ✅ PASS

---

### Conversación 20

**Follower ID:** `report_price_20_1769237362`

| # | Usuario | Bot | Intent |
|---|---------|-----|--------|
| 1 | Hey | ¡Hola! 😊 ¿En qué puedo ayudarte hoy? | `greeting` |
| 2 | ¿Precio? | ¡Fitpack Challenge de 11 días: Transforma tu Relación con el... | `question_product` |
| 3 | Demasiado | Entiendo, a veces puede parecer un poco alto. Pero recuerda ... | `other` |
| 4 | ¿Algo gratis? | Actualmente no tengo contenido gratuito disponible, pero ten... | `lead_magnet` |
| 5 | Ok | ¡Claro! Te cuento sobre Fitpack Challenge de 11 días: Transf... | `interest_soft` |

**Resultado:** ✅ PASS

---


---

