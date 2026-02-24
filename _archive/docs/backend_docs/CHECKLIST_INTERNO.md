# Checklist Interno - Alta de Creador

**Documento interno para el equipo de Clonnect**

---

## Pre-Onboarding

### Verificacion inicial:
- [ ] Creador ha firmado BETA_AGREEMENT
- [ ] Creador tiene cuenta de Instagram Business
- [ ] Creador tiene al menos 1 producto para vender
- [ ] Creador entiende que es una beta con limitaciones

### Datos recopilados:
- [ ] Nombre completo / artistico
- [ ] Handle de Instagram
- [ ] Email de contacto
- [ ] Telegram de contacto (opcional)
- [ ] Descripcion del negocio
- [ ] Publico objetivo

---

## Configuracion Tecnica

### 1. Ejecutar script de onboarding

```bash
cd /path/to/Clonnect-creators
PYTHONPATH=. python3 scripts/onboarding.py
```

Datos a introducir:
- [ ] Creator ID (formato: nombre-creador)
- [ ] Nombre
- [ ] Instagram handle
- [ ] Descripcion del negocio
- [ ] Tono de comunicacion
- [ ] Idioma principal
- [ ] Estilo de venta (soft/medium/direct)

### 2. Configurar productos

Para cada producto:
```bash
# Via API o dashboard
POST /creator/{creator_id}/products
{
    "id": "producto-1",
    "name": "Nombre del Producto",
    "description": "Descripcion breve",
    "price": 97.00,
    "currency": "EUR",
    "payment_link": "https://...",
    "keywords": ["palabra1", "palabra2"]
}
```

Checklist productos:
- [ ] Producto principal configurado
- [ ] Precio correcto
- [ ] Link de pago funcional
- [ ] Keywords relevantes

### 3. Cargar contenido RAG (FAQs)

```bash
# Via API
POST /content/add?creator_id={id}&doc_type=faq
{
    "text": "Pregunta: ...\nRespuesta: ..."
}
```

Contenido a cargar:
- [ ] FAQs basicas (minimo 5)
- [ ] Info de productos
- [ ] Objeciones comunes
- [ ] Politica de devolucion

### 4. Generar API Key

```bash
# Con admin key
POST /auth/keys
{
    "creator_id": "nombre-creador",
    "name": "Key principal"
}
```

- [ ] API key generada
- [ ] API key enviada al creador de forma segura
- [ ] Creador confirma que funciona

### 5. Conectar canal (Instagram/WhatsApp/Telegram)

#### Instagram:
- [ ] Verificar Instagram Business conectado a Facebook Page
- [ ] Configurar webhook en Meta Developer Console
- [ ] Verificar INSTAGRAM_ACCESS_TOKEN valido
- [ ] Test de recepcion de mensaje

#### WhatsApp (opcional):
- [ ] WhatsApp Business API configurada
- [ ] Webhook configurado
- [ ] Test de mensaje

#### Telegram (para testing):
- [ ] Bot creado con @BotFather
- [ ] Token configurado en .env
- [ ] Test de mensaje

---

## Testing

### 6. Test de prueba

Enviar mensajes de prueba:

```
Test 1 - Saludo:
"Hola, como estas?"
Esperado: Saludo personalizado

Test 2 - Interes:
"Me interesa tu curso"
Esperado: Info del producto + link

Test 3 - Precio:
"Cuanto cuesta?"
Esperado: Precio + propuesta de valor

Test 4 - Objecion:
"Es muy caro"
Esperado: Manejo de objecion

Test 5 - Escalacion:
"Quiero hablar contigo directamente"
Esperado: Respuesta de escalacion + notificacion
```

Resultados:
- [ ] Test 1 OK
- [ ] Test 2 OK
- [ ] Test 3 OK
- [ ] Test 4 OK
- [ ] Test 5 OK

### 7. Verificar dashboard

- [ ] Creador puede hacer login
- [ ] Ve sus metricas
- [ ] Ve conversaciones de test
- [ ] Puede pausar/reanudar bot
- [ ] Ve sus productos

---

## Activacion

### 8. Activar bot en produccion

- [ ] Todos los tests pasados
- [ ] Creador da OK para activar
- [ ] Bot activado (is_active = true)
- [ ] Primer mensaje real procesado correctamente

### 9. Monitorear primeras 24h

Revisar cada 4 horas:
- [ ] Hora 0-4: Sin errores
- [ ] Hora 4-8: Sin errores
- [ ] Hora 8-12: Sin errores
- [ ] Hora 12-16: Sin errores
- [ ] Hora 16-20: Sin errores
- [ ] Hora 20-24: Sin errores

Metricas a revisar:
- [ ] Tasa de error < 1%
- [ ] Tiempo de respuesta < 3s
- [ ] Escalaciones justificadas
- [ ] No hay quejas de seguidores

---

## Post-Activacion

### Seguimiento semana 1:
- [ ] Llamada de check-in dia 3
- [ ] Revision de metricas dia 7
- [ ] Ajustes de configuracion si necesario
- [ ] Feedback documentado

### Documentacion interna:
- [ ] Ficha del creador actualizada
- [ ] Notas de configuracion especial
- [ ] Problemas encontrados y solucion
- [ ] Mejoras sugeridas

---

## Datos del Creador

| Campo | Valor |
|-------|-------|
| Creator ID | |
| Nombre | |
| Instagram | |
| Email | |
| Fecha alta | |
| Responsable | |

---

## Notas

_Espacio para notas adicionales durante el proceso de alta_

---

## Firma de Completado

- **Fecha de alta:** _______________
- **Responsable:** _______________
- **Revision por:** _______________

---

*Documento interno - No compartir con creadores*
