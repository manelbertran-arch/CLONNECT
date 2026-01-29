# Clonnect Runbook - Guía de Operaciones

Este documento describe cómo operar, monitorear y solucionar problemas en Clonnect.

## Índice

1. [Verificar Estado del Sistema](#1-verificar-estado-del-sistema)
2. [Errores Comunes y Soluciones](#2-errores-comunes-y-soluciones)
3. [Reiniciar Servicios](#3-reiniciar-servicios)
4. [Rollback](#4-rollback)
5. [Logs y Diagnóstico](#5-logs-y-diagnóstico)
6. [Comandos Útiles](#6-comandos-útiles)
7. [Contactos de Emergencia](#7-contactos-de-emergencia)

---

## 1. Verificar Estado del Sistema

### Health Check Rápido

```bash
# Backend health
curl https://www.clonnectapp.com/health/live

# Respuesta esperada:
# {"status": "ok", "version": "2026.01.17.v1", "timestamp": "..."}
```

### Verificar Endpoints Críticos

```bash
# API funcionando
curl https://www.clonnectapp.com/docs

# Instagram webhook activo
curl https://www.clonnectapp.com/webhook/instagram?hub.mode=subscribe&hub.verify_token=clonnect_verify_2024

# Dashboard stats
curl -H "X-API-Key: YOUR_ADMIN_KEY" https://www.clonnectapp.com/admin/stats
```

### Verificar Base de Datos

```bash
# Desde Railway CLI
railway logs --filter "database"

# O verificar conexión desde Python
python -c "from api.database import engine; print(engine.execute('SELECT 1').scalar())"
```

---

## 2. Errores Comunes y Soluciones

### Error: "Bot no responde a mensajes"

**Síntomas:** Los leads envían mensajes pero no reciben respuesta.

**Diagnóstico:**
```bash
# 1. Verificar si el bot está pausado
curl -H "X-API-Key: KEY" https://api.../bot/{creator_id}/status

# 2. Verificar rate limiting
curl -H "X-API-Key: KEY" https://api.../admin/stats | jq .rate_limiter

# 3. Ver logs recientes
railway logs --tail 100 | grep -i "error\|exception"
```

**Soluciones:**
- Si `bot_active: false` → Reanudar con `POST /bot/{creator_id}/resume`
- Si rate limited → Esperar o resetear con admin key
- Si error de API → Verificar `GROQ_API_KEY` o `OPENAI_API_KEY`

### Error: "Instagram webhook no funciona"

**Síntomas:** Mensajes de Instagram no llegan al sistema.

**Diagnóstico:**
```bash
# Verificar configuración de webhook en Meta
# 1. Ir a developers.facebook.com
# 2. App > Webhooks > Instagram
# 3. Verificar que la URL y el verify_token son correctos
```

**Soluciones:**
- Verificar `INSTAGRAM_VERIFY_TOKEN` coincide con Meta config
- Verificar `INSTAGRAM_APP_SECRET` está configurado
- Re-suscribirse al webhook desde Meta dashboard

### Error: "Database connection failed"

**Síntomas:** Error 500 en endpoints, logs muestran "connection refused".

**Diagnóstico:**
```bash
# Verificar DATABASE_URL
echo $DATABASE_URL | head -c 50

# Test conexión
python -c "import psycopg2; psycopg2.connect('$DATABASE_URL')"
```

**Soluciones:**
- Verificar que Neon/PostgreSQL está activo
- Verificar credenciales en Railway variables
- Reiniciar servicio Railway

### Error: "LLM API rate limited"

**Síntomas:** Respuestas lentas o errores 429.

**Diagnóstico:**
```bash
# Ver logs de LLM
railway logs | grep -i "groq\|openai\|rate"
```

**Soluciones:**
- Esperar 1 minuto (rate limit temporal)
- Cambiar `LLM_PROVIDER` a otro proveedor
- Verificar plan de API (free tier tiene límites bajos)

---

## 3. Reiniciar Servicios

### Reiniciar Backend (Railway)

```bash
# Desde Railway CLI
railway redeploy

# O desde el dashboard:
# 1. railway.app → Proyecto → Servicio
# 2. Click "Redeploy" o "Restart"
```

### Reiniciar con Variables Actualizadas

```bash
# 1. Actualizar variable en Railway
railway variables set LLM_PROVIDER=openai

# 2. El servicio se reinicia automáticamente
```

### Pausar Bot de Emergencia (Todos los Creadores)

```bash
# ADMIN: Pausar todos los bots
curl -X POST -H "X-API-Key: ADMIN_KEY" \
  https://api.../admin/pause-all?reason=emergencia

# ADMIN: Reanudar todos
curl -X POST -H "X-API-Key: ADMIN_KEY" \
  https://api.../admin/resume-all
```

---

## 4. Rollback

### Rollback en Railway

```bash
# 1. Ver deployments anteriores
railway deployments

# 2. Desde Railway dashboard:
# - Ir a Deployments
# - Seleccionar deployment anterior
# - Click "Rollback to this deployment"
```

### Rollback de Código (Git)

```bash
# 1. Ver commits recientes
git log --oneline -10

# 2. Revertir al commit anterior
git revert HEAD
git push origin main

# 3. Railway auto-deploya
```

### Restaurar Backup de BD

```bash
# 1. Listar backups disponibles
curl -H "X-API-Key: ADMIN_KEY" https://api.../admin/backups

# 2. Restaurar manualmente desde JSON
# (Ver scripts/backup_db.py para instrucciones)
```

---

## 5. Logs y Diagnóstico

### Ver Logs en Railway

```bash
# Últimos 100 logs
railway logs --tail 100

# Logs en tiempo real
railway logs --follow

# Filtrar por palabra
railway logs | grep -i "error"
```

### Logs Importantes

| Log Pattern | Significado |
|------------|-------------|
| `[DM_AGENT]` | Procesamiento de mensajes |
| `[WEBHOOK]` | Recepción de webhooks |
| `[RATE_LIMIT]` | Rate limiting activado |
| `[ESCALATION]` | Lead escalado a humano |
| `[LLM]` | Llamadas a API de LLM |
| `[P0-RETRY]` | Reintentos de operaciones críticas |

### Métricas de Diagnóstico

```bash
# Stats generales
curl -H "X-API-Key: ADMIN_KEY" https://api.../admin/stats

# Estado de creadores
curl -H "X-API-Key: ADMIN_KEY" https://api.../admin/creators

# Alertas recientes
curl -H "X-API-Key: ADMIN_KEY" https://api.../admin/alerts
```

---

## 6. Comandos Útiles

### Backend

```bash
# Verificar sintaxis Python
python -m py_compile api/main.py

# Correr tests
pytest -v --tb=short

# Correr un test específico
pytest tests/test_signals.py -v

# Crear backup manual
python scripts/backup_db.py

# Ver configuración de un creador
curl https://api.../dm/{creator_id}/config
```

### Base de Datos

```bash
# Conectar a PostgreSQL (Neon)
psql $DATABASE_URL

# Queries útiles:
# Ver leads recientes
SELECT username, status, score FROM leads ORDER BY last_contact_at DESC LIMIT 10;

# Ver mensajes de un lead
SELECT role, content, created_at FROM messages WHERE lead_id = 'xxx' ORDER BY created_at;

# Contar mensajes por día
SELECT DATE(created_at), COUNT(*) FROM messages GROUP BY 1 ORDER BY 1 DESC LIMIT 7;
```

### Git

```bash
# Ver último commit
git log -1

# Ver cambios pendientes
git status

# Deshacer cambios locales
git checkout -- .
```

---

## 7. Contactos de Emergencia

### Escalación

| Nivel | Situación | Contacto |
|-------|-----------|----------|
| L1 | Bot no responde | Verificar logs, reiniciar |
| L2 | Error de BD/API | Revisar Railway, Neon |
| L3 | Breach de seguridad | Pausar todo, notificar equipo |

### Servicios Externos

| Servicio | Dashboard | Status Page |
|----------|-----------|-------------|
| Railway | railway.app | status.railway.app |
| Neon (PostgreSQL) | console.neon.tech | neonstatus.com |
| Groq | console.groq.com | status.groq.com |
| Meta (Instagram) | developers.facebook.com | developers.facebook.com/status |

### Alertas Configuradas

- **Telegram Alerts:** Configurado en `TELEGRAM_ALERTS_*`
- **Email Alerts:** Via Resend (`RESEND_API_KEY`)
- **Webhook Alerts:** `ESCALATION_WEBHOOK_URL`

---

## Checklist de Incidente

Cuando ocurre un incidente:

- [ ] Identificar el síntoma (qué está fallando)
- [ ] Verificar health checks
- [ ] Revisar logs recientes
- [ ] Determinar si es necesario pausar bots
- [ ] Aplicar fix o rollback
- [ ] Verificar que el sistema está estable
- [ ] Documentar el incidente y la solución
- [ ] Actualizar runbook si es necesario

---

*Última actualización: 2026-01-17*
