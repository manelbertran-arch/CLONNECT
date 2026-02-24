# Guia de Testing Manual - Clonnect

## Setup

### 1. Configurar variables de entorno
```bash
export TELEGRAM_BOT_TOKEN=tu_token_de_botfather
export OPENAI_API_KEY=tu_api_key_de_openai
```

### 2. Arrancar el bot
```bash
PYTHONPATH=. python3 core/telegram_adapter.py --mode polling
```

### 3. Abrir Telegram
Buscar: @clonnect_test_bot (o el nombre de tu bot)

---

## Tests a Ejecutar

### Test 1: Saludo
**Escribe:** "Hola"

**Esperado:**
- Respuesta informal con tono de Manel
- Saludo cercano tipo "Ey! Que tal?"
- Pregunta que necesita el usuario

---

### Test 2: Interes Soft
**Escribe:** "Me interesa lo que haces"

**Esperado:**
- Pregunta que necesita el usuario
- Mencion sutil de productos/servicios
- Tono conversacional

---

### Test 3: Interes Fuerte
**Escribe:** "Quiero comprar el curso de automatizacion"

**Esperado:**
- Link directo al curso: https://clonnect.com/curso-automatizacion
- Beneficios principales del curso
- Precio: 297 EUR

---

### Test 4: Objecion Precio
**Escribe:** "Es muy caro para mi"

**Esperado:**
- Handler de objecion "precio"
- Mencion de garantia de 30 dias
- Argumento de ROI (recuperar inversion)

---

### Test 5: Objecion Tiempo
**Escribe:** "No tengo tiempo para hacer un curso"

**Esperado:**
- Handler de objecion "tiempo"
- Mencion de 15 minutos al dia
- Resultados en 2 semanas

---

### Test 6: Pregunta Producto
**Escribe:** "Que incluye la mentoria?"

**Esperado:**
- Lista de beneficios de mentoria:
  - 12 sesiones de 1 hora
  - Acceso directo por WhatsApp
  - Revision de tu negocio
  - Plan de accion personalizado
  - Acceso a todos los cursos
- Precio: 1500 EUR

---

### Test 7: Lead Magnet
**Escribe:** "Tienes algo gratis para empezar?"

**Esperado:**
- Ofrece ebook gratuito
- Link: https://clonnect.com/ebook-gratis
- Descripcion: "10 Automatizaciones que Necesitas Ya"

---

### Test 8: Queja
**Escribe:** "No funciona el link de compra"

**Esperado:**
- Disculpa
- Ofrece ayuda para solucionar
- Posible escalado si es grave

---

### Test 9: Usuario que Vuelve
**Paso 1:** Escribe "Hola, me interesa el curso"
**Paso 2:** Escribe "Cuanto cuesta?"
**Paso 3:** Escribe "Gracias!"

**Esperado:**
- Reconoce que es el mismo usuario
- Respuestas coherentes con la conversacion anterior
- Memoria de lo que se ha hablado

---

### Test 10: Escalacion
**Escribe:** "Es urgente, necesito hablar con alguien"

**Esperado:**
- Detecta keyword "urgente"
- Mensaje de escalacion
- Promete respuesta personal de Manel

---

### Test 11: Pregunta General
**Escribe:** "A que te dedicas?"

**Esperado:**
- Respuesta como Manel
- Mencion de automatizacion y productividad
- Tono cercano e informal

---

### Test 12: Despedida
**Escribe:** "Adios, gracias por la info"

**Esperado:**
- Despedida amable
- Ofrecimiento de ayuda futura
- Cierre tipo "Cualquier cosa me dices!"

---

## Checklist de Validacion

### Tono y Personalidad
- [ ] Respuestas suenan como Manel (no como bot)
- [ ] Tono informal pero profesional
- [ ] Usa "tu" en lugar de "usted"
- [ ] Vocabulario cercano (brutal, mola, flipante)

### Productos
- [ ] Productos mencionados cuando es relevante
- [ ] Precios correctos (297, 1500, 0)
- [ ] Links correctos
- [ ] Beneficios listados correctamente

### Objeciones
- [ ] Objecion "caro" -> garantia 30 dias
- [ ] Objecion "tiempo" -> 15 min/dia
- [ ] Objecion "pensarlo" -> sin presion

### Formato
- [ ] Emojis con moderacion (1-2 por mensaje)
- [ ] Respuestas concisas (2-3 frases)
- [ ] Sin respuestas demasiado largas

### Memoria
- [ ] Reconoce usuario que vuelve
- [ ] Recuerda productos discutidos
- [ ] Historial de conversacion funciona

### Escalacion
- [ ] "urgente" -> escala
- [ ] "reembolso" -> escala
- [ ] "hablar con humano" -> escala

---

## Comandos Utiles

### Ver logs detallados
```bash
PYTHONPATH=. python3 core/telegram_adapter.py --mode polling --log-level DEBUG
```

### Ejecutar tests automaticos
```bash
pytest tests/test_full_flow.py -v
```

### Ver solo tests fallidos
```bash
pytest tests/test_full_flow.py -v --tb=short -x
```

---

## Troubleshooting

### Bot no responde
1. Verificar TELEGRAM_BOT_TOKEN esta configurado
2. Verificar OPENAI_API_KEY esta configurado
3. Ver logs para errores

### Respuestas genericas
1. Verificar que existe data/creators/manel_config.json
2. Verificar que existe data/products/manel_products.json
3. Reiniciar el bot

### Intent incorrecto
1. El clasificador de intents puede mejorar con mas contexto
2. Verificar el mensaje no es ambiguo
3. Probar con mensajes mas claros

### Memoria no funciona
1. Verificar que existe directorio data/followers/
2. Verificar permisos de escritura
3. Los followers se guardan como JSON en data/followers/manel/
