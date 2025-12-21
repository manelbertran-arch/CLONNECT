# Guia de Onboarding para Creadores

**Bienvenido a Clonnect Creators!**

Esta guia te ayudara a configurar tu clon de IA para responder DMs automaticamente.

---

## 1. Antes de Empezar

### Que necesitas preparar:

**Informacion basica:**
- [ ] Tu nombre artistico / marca
- [ ] Tu handle de Instagram (@tuhandle)
- [ ] Descripcion de tu negocio (1-2 parrafos)
- [ ] Tu publico objetivo

**Tu estilo de comunicacion:**
- [ ] 3-5 adjetivos que te describen (cercano, profesional, divertido...)
- [ ] Expresiones o muletillas que usas frecuentemente
- [ ] Nivel de emojis (ninguno, moderado, muchos)
- [ ] Idioma(s) en que quieres responder

**Tus productos/servicios:**
- [ ] Nombre de cada producto
- [ ] Descripcion breve (2-3 frases)
- [ ] Precio
- [ ] Link de pago (Stripe, Hotmart, etc.)
- [ ] Palabras clave relacionadas

**FAQs:**
- [ ] Las 10 preguntas mas frecuentes que recibes
- [ ] Las respuestas que sueles dar

---

## 2. Como Funciona el Bot

### El flujo basico:

```
Seguidor envia DM
       |
       v
Bot detecta idioma e intent
       |
       v
Busca producto relevante
       |
       v
Genera respuesta personalizada
       |
       v
Envia respuesta automatica
```

### Tipos de mensajes que entiende:

| Intent | Ejemplo | Respuesta |
|--------|---------|-----------|
| Saludo | "Hola!" | Saludo personalizado |
| Interes | "Me interesa tu curso" | Info + link de pago |
| Precio | "Cuanto cuesta?" | Precio + valor |
| Duda | "No se si es para mi" | Resolver objecion |
| Soporte | "Tengo un problema" | Pedir detalles |
| Escalacion | "Quiero hablar contigo" | Avisar que contactaras |

### Respuestas automaticas:
- El bot responde en 1-3 segundos
- Las respuestas son cortas (2-3 frases)
- Usa tu tono y estilo configurado
- Nunca revela que es una IA

---

## 3. Que Puede Hacer el Bot

### SI puede:
- Responder preguntas sobre tus productos
- Detectar interes y ofrecer links de pago
- Manejar objeciones comunes (precio, tiempo, dudas)
- Detectar idioma y responder en el mismo
- Derivar conversaciones a ti cuando es necesario
- Guardar historial de cada seguidor

### NO puede:
- Procesar pagos directamente
- Leer imagenes o audios
- Acceder a info externa en tiempo real
- Responder preguntas muy especificas no configuradas
- Mentir o inventar informacion

---

## 4. Como Ver tus Metricas

### Dashboard principal:
1. Accede a tu dashboard con tu API key
2. Ve la seccion "Metricas"

### Metricas disponibles:
- **Mensajes totales:** Total de DMs procesados
- **Leads:** Seguidores con interes detectado
- **Leads calientes:** Score >= 70% de compra
- **Tasa de respuesta:** % de mensajes respondidos
- **Escalaciones:** Conversaciones derivadas a ti

### Categorias de leads:
- **Caliente (rojo):** Muy interesado, alta probabilidad de compra
- **Tibio (amarillo):** Interesado pero con dudas
- **Frio (gris):** Consulta general, bajo interes

---

## 5. Como Pausar el Bot

### Desde el Dashboard:
1. Sidebar izquierdo
2. Seccion "Control del Bot"
3. Click en "Pausar Bot"
4. El bot dejara de responder inmediatamente

### Desde la API:
```bash
POST /bot/{tu_creator_id}/pause
```

### Cuando pausar:
- Vacaciones o ausencias largas
- Lanzamiento en vivo donde quieres responder tu
- Problemas tecnicos reportados
- Cuando quieras revisar conversaciones manualmente

### Reanudar:
Click en "Activar Bot" o `POST /bot/{id}/resume`

---

## 6. Contacto con Soporte

### Dudas de configuracion:
- Email: soporte@clonnect.com
- Telegram: @ClonnectSupport

### Reportar problemas:
- El bot responde algo incorrecto
- Un seguidor se queja
- Errores tecnicos

### Proceso:
1. Pausa el bot si es urgente
2. Envia captura del problema
3. Indica tu creator_id
4. Describe que esperabas vs que paso

### Tiempos de respuesta:
- Urgente (bot respondiendo mal): < 1 hora
- Normal: < 24 horas
- Consultas generales: < 48 horas

---

## 7. Tips para Mejores Resultados

### Productos:
- Usa descripciones claras y concisas
- Incluye palabras clave que usan tus seguidores
- Actualiza precios cuando cambien

### Tono:
- Se especifico con tu estilo
- Da ejemplos de frases que usarias
- Indica que NO dirias nunca

### FAQs:
- Anade las preguntas reales que recibes
- Actualiza con preguntas nuevas cada semana
- Incluye objeciones comunes

### Monitoreo:
- Revisa el dashboard diariamente al inicio
- Lee las conversaciones escaladas
- Ajusta configuracion segun feedback

---

## 8. Primeros Pasos

### Semana 1:
1. Completar onboarding con el equipo
2. Configurar productos y tono
3. Activar bot en modo test
4. Revisar primeras conversaciones

### Semana 2:
1. Ajustar respuestas segun feedback
2. Anadir FAQs que falten
3. Activar en produccion
4. Monitorear metricas

### Semana 3+:
1. Revision semanal de metricas
2. Actualizar productos si hay cambios
3. Reportar cualquier problema
4. Compartir feedback con el equipo

---

## Checklist de Lanzamiento

- [ ] Perfil de creador configurado
- [ ] Al menos 1 producto activo
- [ ] Tono y estilo definidos
- [ ] FAQs basicas anadidas
- [ ] Test de conversacion exitoso
- [ ] API key guardada de forma segura
- [ ] Dashboard accesible
- [ ] Canal de soporte conocido

---

**Listo para empezar?**

Contacta con tu account manager para agendar la sesion de onboarding.

*Clonnect Creators - Tu clon de IA para responder DMs*
