# Clonnect Creators - Acuerdo de Beta Privada

**Version 1.0 - Diciembre 2024**

---

## 1. Que es la Beta Privada

La beta privada de Clonnect Creators es un programa exclusivo donde creadores de contenido seleccionados pueden probar nuestro sistema de IA para automatizar respuestas a DMs antes del lanzamiento publico.

### Objetivo de la beta
- Validar el funcionamiento del sistema en escenarios reales
- Recopilar feedback de creadores para mejorar el producto
- Identificar y corregir errores antes del lanzamiento
- Ajustar el tono y respuestas de la IA

---

## 2. Limitaciones y Posibles Errores

### La IA puede:
- Ocasionalmente malinterpretar el contexto de un mensaje
- Generar respuestas que no coincidan exactamente con tu tono
- Tener latencia en momentos de alta demanda
- No entender expresiones muy locales o jerga especifica

### La IA NO puede:
- Procesar imagenes, audios o videos (solo texto)
- Acceder a informacion en tiempo real externa
- Realizar pagos o transacciones por ti
- Garantizar conversiones de venta

### Disponibilidad
- El servicio puede tener interrupciones para mantenimiento
- Durante la beta, no hay SLA garantizado
- Posibles reinicios del sistema para actualizaciones

---

## 3. Datos que Recopilamos

### Datos de conversacion:
- Mensajes recibidos de seguidores (texto)
- Respuestas generadas por la IA
- Intents detectados (tipo de mensaje)
- Scores de intencion de compra

### Datos de uso:
- Numero de mensajes procesados
- Tiempos de respuesta
- Tasa de escalacion a humano
- Metricas de engagement

### Datos de configuracion:
- Tu perfil de creador
- Productos configurados
- Preferencias de tono y estilo

### NO recopilamos:
- Contrasenas o credenciales
- Informacion financiera personal
- Datos de seguidores fuera de las conversaciones

---

## 4. Como Solicitamos Proteger tus Datos

Implementamos:
- Encriptacion en transito (HTTPS)
- Almacenamiento seguro con acceso limitado
- Logs de auditoria para acceso a datos
- Opcion de anonimizacion de datos

---

## 5. Tus Derechos (GDPR)

Tienes derecho a:

### Acceso
Solicitar una copia de todos los datos que tenemos sobre ti y tus seguidores.

### Rectificacion
Corregir cualquier dato incorrecto.

### Eliminacion
Solicitar el borrado completo de tus datos ("derecho al olvido").

### Portabilidad
Recibir tus datos en formato estructurado (JSON).

### Oposicion
Oponerte al procesamiento de tus datos en cualquier momento.

---

## 6. Como Solicitar Borrado de Datos

### Opcion 1: Desde el Dashboard
1. Accede a tu dashboard
2. Ve a Configuracion > Privacidad
3. Click en "Solicitar borrado de datos"
4. Confirma la solicitud

### Opcion 2: Via API
```bash
DELETE /gdpr/{creator_id}/delete/{follower_id}
```

### Opcion 3: Contacto directo
Envia un email a: soporte@clonnect.com
Asunto: "Solicitud GDPR - Borrado de datos"
Incluye: Tu creator_id y que datos quieres eliminar

### Tiempo de respuesta
- Solicitudes procesadas en maximo 72 horas
- Confirmacion por email una vez completado

---

## 7. Contacto para Problemas

### Soporte Tecnico
- Email: soporte@clonnect.com
- Telegram: @ClonnectSupport
- Horario: Lunes a Viernes, 9:00 - 18:00 CET

### Reportar Bugs
- Email: bugs@clonnect.com
- Incluir: Descripcion del problema, pasos para reproducir, capturas si es posible

### Emergencias
Si el bot esta respondiendo de forma inapropiada:
1. Pausar el bot desde el dashboard inmediatamente
2. Contactar via Telegram para respuesta rapida

---

## 8. Aceptacion de Terminos

Al participar en la beta privada de Clonnect Creators, aceptas:

- [ ] Entiendo que es un producto en desarrollo y puede tener errores
- [ ] Me comprometo a reportar bugs y dar feedback constructivo
- [ ] Autorizo el uso de mis datos de conversacion para mejorar el servicio
- [ ] Puedo solicitar el borrado de mis datos en cualquier momento
- [ ] No compartire acceso a mi cuenta con terceros

---

**Fecha de aceptacion:** _______________

**Nombre del creador:** _______________

**Creator ID:** _______________

---

*Clonnect Creators - Tu clon de IA para responder DMs*
