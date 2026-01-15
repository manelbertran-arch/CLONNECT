# TRABAJO ACTIVO

## Estado: 🔨 EN PROGRESO

## Tarea actual
Diagnosticar por qué los leads muestran 0 mensajes en el dashboard

## Contexto de Trabajo

### 🎯 TAREA
Diagnosticar y arreglar import de DMs - leads muestran 0 mensajes, scoring incorrecto

### 📁 ARCHIVOS ANALIZADOS
| Archivo | Qué hace | Riesgo |
|---------|----------|--------|
| backend/core/dm_history_service.py | Importa DMs desde Instagram API | Alto - core |
| backend/api/routers/messages.py | API de conversaciones/mensajes | Medio |
| backend/api/services/db_service.py | Query get_conversations_with_counts | Medio |

### 🔗 DEPENDENCIAS
| Archivo | Cómo lo usa |
|---------|-------------|
| oauth.py | Trigger import después de OAuth |
| onboarding.py | Trigger import al terminar onboarding |
| auto_configurator.py | Llama a dm_history_service |

### 🔄 FLUJO COMPLETO
```
OAuth → load_dm_history() → _import_conversation() → Lead + Messages en DB
                                    ↓
Dashboard ← get_conversations_with_counts() ← LEFT JOIN messages
```

### ✅ QUÉ DEBE SEGUIR FUNCIONANDO
- [ ] Bot responde webhooks
- [ ] RAG devuelve chunks
- [ ] Token refresh funciona
- [ ] Dashboard carga leads

## Análisis del Código

### dm_history_service.py (líneas 149-302)
```python
# _import_conversation hace:
1. Busca creator por nombre → Creator.filter_by(name=creator_id)
2. Busca/crea lead → Lead.filter_by(creator_id=creator.id, platform_user_id=follower_id)
3. Por cada mensaje:
   - Determina role (user/assistant) comparando from_id con page_id/ig_user_id
   - Clasifica intent con classify_intent_simple()
   - Crea Message(lead_id=lead.id, ...)
4. Calcula purchase_intent basado en señales
5. Actualiza lead.status basado en score
```

### db_service.py (líneas 191-239)
```python
# get_conversations_with_counts hace:
1. Busca creator por nombre
2. Subquery cuenta mensajes WHERE role='user' GROUP BY lead_id
3. LEFT JOIN leads con subquery
4. Devuelve total_messages de cada lead
```

## Posibles Causas de 0 Mensajes

### Hipótesis 1: Import nunca se ejecutó
- `load_dm_history()` no se llamó durante OAuth/onboarding
- Verificar: ¿Hay logs de "[DMHistory]" en Railway?

### Hipótesis 2: Mensajes se guardaron con lead_id incorrecto
- platform_user_id no matchea entre import y query
- Verificar: Comparar leads vs messages en DB

### Hipótesis 3: Los mensajes existen pero sin role='user'
- Subquery filtra `WHERE role='user'`
- Si todos los mensajes tienen role='assistant', cuenta = 0

### Hipótesis 4: Creator ID mismatch
- dm_history_service usa `creator_id` (nombre string)
- Pero busca Creator por name para obtener UUID

## Próximos pasos
1. Ejecutar queries de diagnóstico en Supabase
2. Analizar resultados
3. Identificar causa raíz
4. Proponer fix específico
