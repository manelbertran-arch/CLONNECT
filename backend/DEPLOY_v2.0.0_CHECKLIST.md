# DEPLOY v2.0.0 - CHECKLIST BETA

## Fecha: 2024-01-24
## Versión: v2.0.0 (Detector de Contenido Sensible)

---

## 1. PRE-DEPLOY ✅

### Código
- [x] Tests proyecto: 830 passed, 15 failed (preexistentes)
- [x] Tests sensibles: 7/7 PASS
- [x] Test masivo: 50/50 PASS
- [x] Sintaxis Python: OK
- [x] Imports: OK
- [x] Archivos requeridos: OK

### Git
- [x] Branch: main
- [x] Tag: v2.0.0
- [x] Pushed to origin

---

## 2. FUNCIONALIDAD NUEVA

### Detector de Contenido Sensible
| Tipo | Acción | Prioridad |
|------|--------|-----------|
| SELF_HARM | Escalar + recursos crisis + notificar | CRÍTICA |
| THREAT | Escalar + notificar creador | ALTA |
| PHISHING | Bloquear respuesta | ALTA |
| SPAM | No responder (silencio) | MEDIA |
| EATING_DISORDER | Contexto empático LLM | MEDIA |
| MINOR | No presionar venta | MEDIA |
| ECONOMIC_DISTRESS | Empatía | BAJA |

### Archivos Nuevos
```
core/sensitive_detector.py    - 350 líneas
```

### Modificaciones
```
core/dm_agent.py              - +167 líneas
```

---

## 3. DEPLOY RAILWAY

### Comando
```bash
# Railway detecta automáticamente el push a main
# O manualmente:
railway up
```

### Variables de Entorno (ya configuradas en Railway)
- [x] LLM_PROVIDER
- [x] CLONNECT_ADMIN_KEY
- [x] GROQ_API_KEY
- [x] DATABASE_URL
- [x] INSTAGRAM_ACCESS_TOKEN
- [x] TELEGRAM_BOT_TOKEN

---

## 4. POST-DEPLOY VERIFICACIÓN

### Health Check
```bash
curl https://[RAILWAY_URL]/health/live
# Expected: {"status": "ok"}
```

### Test Endpoint DM
```bash
curl -X POST https://[RAILWAY_URL]/dm/stefano \
  -H "Content-Type: application/json" \
  -d '{"sender_id": "test_beta", "message": "Hola, me interesa"}'
```

### Test Contenido Sensible (CUIDADO - Solo testing)
```bash
# SELF_HARM - Debe escalar
curl -X POST https://[RAILWAY_URL]/dm/stefano \
  -H "Content-Type: application/json" \
  -d '{"sender_id": "test_sensitive", "message": "A veces me hago daño"}'
# Expected: Respuesta con recursos de crisis

# SPAM - Debe ignorar
curl -X POST https://[RAILWAY_URL]/dm/stefano \
  -H "Content-Type: application/json" \
  -d '{"sender_id": "test_spam", "message": "Check my profile bit.ly/spam"}'
# Expected: response_text = ""
```

---

## 5. MONITOREO BETA

### Logs a Observar
```
[SENSITIVE] SELF_HARM detected    → Escalado funcionando
[SENSITIVE] THREAT detected       → Amenazas detectadas
[SENSITIVE] PHISHING detected     → Bloqueo activo
[SENSITIVE] SPAM detected         → Spam filtrado
```

### Métricas Clave
- Ratio de detección de contenido sensible
- Escalaciones por tipo
- Falsos positivos (revisar manualmente)

---

## 6. ROLLBACK (si es necesario)

```bash
git checkout v1.8.0-variation
git push origin main --force
railway up
```

O en Railway:
1. Ir a Deployments
2. Seleccionar deploy anterior
3. Redeploy

---

## 7. COMUNICACIÓN A STEFANO

### Mensaje Sugerido:
```
🚀 CLONNECT v2.0.0 - BETA DESPLEGADO

Nueva funcionalidad crítica de SEGURIDAD:
- Detección automática de autolesiones → Escalado inmediato
- Detección de amenazas → Notificación
- Bloqueo de phishing
- Filtrado de spam

El bot ahora es más seguro para usuarios vulnerables.

Por favor, revisa los escalados de las próximas 24-48h
para validar que no hay falsos positivos.

Rollback disponible a v1.8.0 si hay problemas.
```

---

## 8. APROBACIÓN

- [ ] Deploy ejecutado
- [ ] Health check OK
- [ ] Test endpoint OK
- [ ] Stefano notificado
- [ ] Monitoreo activo 24h

**Responsable:** _______________
**Fecha deploy:** _______________
