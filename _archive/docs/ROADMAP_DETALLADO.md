# Clonnect Refactoring Roadmap - Ultra Detallado

> Documento maestro del proceso de refactoring
> Última actualización: 2026-01-28

---

## 1. CONTEXTO: ¿Por qué estamos haciendo esto?

### 1.1 Problema detectado

Clonnect funciona, pero el código tiene **deuda técnica crítica**:

```
┌─────────────────────────────────────────────────────────────────┐
│                    ESTADO ACTUAL DEL CÓDIGO                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  backend/api/main.py          ████████████████████  7,198 líneas│
│  backend/core/dm_agent.py     █████████████████████ 7,463 líneas│
│  backend/api/routers/onboarding.py  ████████████   4,546 líneas│
│  backend/api/routers/admin.py       ██████████     3,642 líneas│
│                                                                 │
│  Target por archivo: <500 líneas (máximo 800)                   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  print() statements:    1,635   (target: 0)                     │
│  bare except clauses:   20+     (target: 0)                     │
│  Audit Score:           42/80   (target: 62/80)                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Consecuencias de no actuar

- **Bugs difíciles de encontrar**: 7,000 líneas = imposible de debuggear
- **Onboarding lento**: Nuevos devs tardan semanas en entender
- **Features lentos**: Cada cambio toca demasiado código
- **Tests imposibles**: No se puede testear un monolito

### 1.3 Objetivo final

```
ANTES                              DESPUÉS
──────                             ───────
main.py (7,198 líneas)    →        main.py (<500) + 6 routers
dm_agent.py (7,463 líneas) →       dm_agent.py (<800) + 5 services
542 print()               →        0 print(), todo logging
20+ bare except           →        0 bare except
Score 42/80               →        Score 62/80
```

---

## 2. ESTRATEGIA: ¿Cómo lo hacemos?

### 2.1 Principio fundamental

```
╔═══════════════════════════════════════════════════════════════╗
║  NUNCA ROMPER LO QUE FUNCIONA                                 ║
║                                                               ║
║  - Cambios pequeños (baby steps)                              ║
║  - Test después de cada cambio                                ║
║  - Commit frecuente                                           ║
║  - Rollback fácil si algo falla                               ║
╚═══════════════════════════════════════════════════════════════╝
```

### 2.2 Fases del refactoring

```
┌──────────────────────────────────────────────────────────────────┐
│                        FASES DEL REFACTORING                      │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  PHASE 0 ──► PHASE 1 ──► PHASE 2 ──► PHASE 3                     │
│  Quick Fixes  main.py    dm_agent    Audience                    │
│  (sin riesgo) (extraer)  (extraer)   Intelligence                │
│                                                                   │
│  ████░░░░░░   ░░░░░░░░   ░░░░░░░░    ░░░░░░░░                    │
│  ~5% done     0%         0%          0%                          │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. PHASE 0: Quick Fixes (ACTUAL)

### 3.1 Objetivo

Mejorar calidad SIN cambiar lógica. Riesgo: **MÍNIMO**.

### 3.2 Task 0.1: Reemplazar print() → logging

#### ¿Por qué?
- `print()` no tiene niveles (debug, info, error)
- `print()` no tiene timestamps
- `print()` no se puede filtrar en producción
- Los logs se pierden

#### ¿Cómo se ejecuta?

**Paso 1**: Encontrar prints en un archivo
```bash
grep -n "print(" backend/api/services/screenshot_service.py
```

**Paso 2**: Añadir imports al inicio del archivo
```python
import logging
logger = logging.getLogger(__name__)
```

**Paso 3**: Reemplazar cada print
```python
# ANTES
print(f"Processing user {user_id}")

# DESPUÉS
logger.info(f"Processing user {user_id}")
```

**Paso 4**: Elegir nivel correcto
```python
logger.debug(...)   # Para desarrollo, verbose
logger.info(...)    # Operaciones normales
logger.warning(...) # Algo inesperado pero no crítico
logger.error(...)   # Errores que necesitan atención
```

**Paso 5**: Verificar sintaxis
```bash
python3 -m py_compile backend/api/services/screenshot_service.py
```

**Paso 6**: Commit
```bash
git add backend/api/services/screenshot_service.py
git commit -m "refactor: replace print() with logging in screenshot_service.py"
```

#### Progreso actual

| Archivo | Prints | Convertidos | Status |
|---------|--------|-------------|--------|
| screenshot_service.py | 15 | 15 | ✅ DONE |
| llm.py | 8 | 8 | ✅ DONE |
| dm_agent.py | ~200 | 0 | 🔴 PENDING |
| main.py | ~150 | 0 | 🔴 PENDING |
| onboarding.py | ~80 | 0 | 🔴 PENDING |
| admin.py | ~50 | 0 | 🔴 PENDING |
| otros archivos | ~39 | 0 | 🔴 PENDING |
| **TOTAL** | **~542** | **23** | **~5%** |

#### Orden de ejecución

```
1. Archivos pequeños primero (menos riesgo)
   └── services/*.py, utils/*.py

2. Archivos medianos
   └── routers/admin.py, routers/onboarding.py

3. Archivos grandes al final
   └── main.py, dm_agent.py
```

### 3.3 Task 0.2: Fix bare except clauses

#### ¿Por qué?
```python
# MALO - captura TODO, incluso Ctrl+C
try:
    do_something()
except:
    pass

# BUENO - específico
try:
    do_something()
except ValueError as e:
    logger.error(f"Invalid value: {e}")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
```

#### ¿Cómo encontrarlos?
```bash
grep -rn "except:" backend/ --include="*.py" | grep -v "except "
```

#### Progreso
- Status: 🔴 NO INICIADO
- Esperando completar Task 0.1

---

## 4. PHASE 1: Extraer de main.py

### 4.1 Objetivo

Reducir main.py de **7,198** a **<500** líneas.

### 4.2 Estructura actual de main.py

```
main.py (7,198 líneas)
├── Imports (líneas 1-150)
├── Config y middleware (150-400)
├── Auth endpoints (400-800)           → extraer a routers/auth.py
├── User endpoints (800-1200)          → extraer a routers/users.py
├── Instagram endpoints (1200-2000)    → extraer a routers/instagram.py
├── Campaign endpoints (2000-2800)     → extraer a routers/campaigns.py
├── Analytics endpoints (2800-3400)    → extraer a routers/analytics.py
├── Billing/Stripe (3400-4000)         → extraer a routers/billing.py
├── DM endpoints (4000-5500)           → extraer a routers/dm.py
├── Webhook handlers (5500-6500)       → extraer a routers/webhooks.py
└── Misc endpoints (6500-7198)         → evaluar uno a uno
```

### 4.3 Proceso de extracción (ejemplo: auth)

**Paso 1**: Crear branch
```bash
git checkout -b refactor/extract-auth-router
```

**Paso 2**: Crear archivo destino
```python
# backend/api/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
# ... imports necesarios

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
async def login(...):
    # código exacto de main.py
    pass
```

**Paso 3**: Mover endpoints uno a uno
- Copiar función completa
- Copiar imports necesarios
- NO cambiar lógica

**Paso 4**: Actualizar main.py
```python
# main.py
from backend.api.routers import auth

app.include_router(auth.router)

# Eliminar endpoints movidos
```

**Paso 5**: Verificar
```bash
python3 -m py_compile backend/api/routers/auth.py
python3 -m py_compile backend/api/main.py
pytest tests/ -v
```

**Paso 6**: Commit y PR
```bash
git add .
git commit -m "refactor: extract auth endpoints to routers/auth.py

- Moved /login, /register, /token endpoints
- main.py: 7198 → 6400 lines (-798)
- New file: routers/auth.py (320 lines)"
```

### 4.4 Orden de extracción

| Orden | Router | Endpoints | Líneas Est. | Riesgo |
|-------|--------|-----------|-------------|--------|
| 1 | auth.py | login, register, token, refresh | ~400 | Bajo |
| 2 | users.py | CRUD usuarios, profile | ~400 | Bajo |
| 3 | billing.py | Stripe webhooks, subscriptions | ~600 | Medio |
| 4 | analytics.py | Stats, métricas, dashboards | ~400 | Bajo |
| 5 | campaigns.py | CRUD campañas, activación | ~600 | Medio |
| 6 | instagram.py | Conexión IG, webhooks Meta | ~800 | Alto |
| 7 | dm.py | Endpoints de DM | ~1500 | Alto |

---

## 5. PHASE 2: Extraer de dm_agent.py

### 5.1 Objetivo

Reducir dm_agent.py de **7,463** a **<800** líneas.

### 5.2 Estructura actual

```
dm_agent.py (7,463 líneas)
├── Imports y config (1-200)
├── Intent classification (200-700)     → services/intent_classifier.py
├── Memory operations (700-1500)        → services/memory_manager.py
├── Conversation state (1500-2200)      → services/conversation_engine.py
├── Response generation (2200-3000)     → services/response_generator.py
├── Funnel management (3000-3600)       → services/funnel_manager.py
├── LLM calls (3600-4500)              → services/llm_service.py
├── Message processing (4500-6000)      → mantener en dm_agent.py
└── Utilities (6000-7463)              → utils/dm_utils.py
```

### 5.3 Orden de extracción

| Orden | Service | Responsabilidad | Líneas Est. |
|-------|---------|-----------------|-------------|
| 1 | intent_classifier.py | Clasificar intención del mensaje | ~500 |
| 2 | memory_manager.py | CRUD de follower_memories | ~800 |
| 3 | funnel_manager.py | Progresión en funnel de ventas | ~600 |
| 4 | response_generator.py | Generar respuestas con LLM | ~800 |
| 5 | conversation_engine.py | Estado de conversación | ~700 |

---

## 6. PHASE 3: Audience Intelligence (Feature nuevo)

### 6.1 Contexto

Clonnect tiene datos de 27+ campos por follower que **NO se exponen** en la UI.

### 6.2 Endpoints a crear

```
GET  /api/audience/segments
     → Lista de segmentos (hot leads, cold leads, etc.)

GET  /api/audience/insights
     → Estadísticas agregadas (intenciones, objeciones, etc.)

GET  /api/audience/followers/{segment}
     → Lista de followers en un segmento

POST /api/audience/export
     → Exportar audiencia a CSV/JSON
```

### 6.3 Dependencia

```
Phase 3 REQUIERE:
├── Phase 1 completado (routers extraídos)
└── Phase 2 completado (services extraídos)

Porque los nuevos endpoints usarán los services extraídos.
```

---

## 7. HERRAMIENTAS Y WORKFLOW

### 7.1 Stack de trabajo

```
┌─────────────────────────────────────────────────────────────┐
│                     TU WORKFLOW                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   [Claude.ai]  ←──── planificar, discutir ────→  [Tú]       │
│       │                                            │         │
│       │ instrucciones                    resultados│         │
│       ▼                                            │         │
│   [Claude Code CLI] ───── ejecutar ───────────────┘         │
│       │                                                      │
│       │ cambios                                              │
│       ▼                                                      │
│   [Git repo] ──── push ────→ [GitHub]                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Archivos de control

| Archivo | Propósito | Quién lo actualiza |
|---------|-----------|-------------------|
| CLAUDE.md | Reglas que CLI sigue | Tú (manualmente) |
| REFACTOR_PLAN.md | Plan de trabajo | Claude (cuando hay cambios) |
| PROGRESS.md | Estado actual | Claude (después de cada tarea) |
| ROADMAP_DETALLADO.md | Este documento | Claude (referencia) |

### 7.3 Comandos frecuentes en CLI

```bash
# Ver progreso
cat PROGRESS.md

# Contar prints restantes
grep -rn "print(" backend/ --include="*.py" | wc -l

# Ver tamaño de monolitos
wc -l backend/api/main.py backend/core/dm_agent.py

# Verificar sintaxis de un archivo
python3 -m py_compile backend/path/to/file.py

# Correr tests
pytest tests/ -v --tb=short

# Ver cambios pendientes
git status

# Ver historial reciente
git log --oneline -10
```

---

## 8. TIMELINE Y MÉTRICAS

### 8.1 Estimación por fase

| Fase | Tareas | Horas Est. | Score Esperado |
|------|--------|------------|----------------|
| Phase 0 | 2 tasks | 4-6h | 42 → 48 |
| Phase 1 | 7 extracciones | 10-14h | 48 → 55 |
| Phase 2 | 5 extracciones | 8-12h | 55 → 60 |
| Phase 3 | 4 endpoints | 6-8h | 60 → 62 |
| **TOTAL** | **18 tareas** | **28-40h** | **42 → 62** |

### 8.2 Métricas de éxito

```
╔════════════════════════════════════════════════════════════╗
║                    DEFINICIÓN DE ÉXITO                      ║
╠════════════════════════════════════════════════════════════╣
║                                                             ║
║  ✓ main.py < 500 líneas                                    ║
║  ✓ dm_agent.py < 800 líneas                                ║
║  ✓ 0 print() statements                                    ║
║  ✓ 0 bare except: clauses                                  ║
║  ✓ Todos los tests pasan                                   ║
║  ✓ Aplicación funciona igual que antes                     ║
║  ✓ Audit score ≥ 62/80                                     ║
║                                                             ║
╚════════════════════════════════════════════════════════════╝
```

---

## 9. ESTADO ACTUAL (2026-01-28)

### 9.1 Resumen ejecutivo

```
FASE ACTUAL: Phase 0 - Task 0.1
TAREA: Reemplazar print() con logging
PROGRESO: ~5% (28/542 prints convertidos)
PRÓXIMO: Continuar con archivos restantes
```

### 9.2 Últimas acciones completadas

1. ✅ Auditoría técnica completa (score 42/80)
2. ✅ Framework ai-specs implementado y adaptado
3. ✅ CLAUDE.md configurado (CLI lo lee automáticamente)
4. ✅ REFACTOR_PLAN.md creado
5. ✅ PROGRESS.md creado
6. ✅ Migración a CLI completada
7. ✅ Primeros 28 prints convertidos (screenshot_service.py, llm.py)

### 9.3 Próximas acciones

```
INMEDIATO (hoy):
└── Continuar Task 0.1: convertir prints restantes
    └── Siguiente archivo: dm_agent.py (~200 prints)

DESPUÉS:
└── Task 0.2: Fix bare except clauses

LUEGO:
└── Phase 1: Extraer routers de main.py
```

---

## 10. COMANDOS PARA CLAUDE CLI

### Para continuar el trabajo:

```
Lee ROADMAP_DETALLADO.md y continúa con Task 0.1.
Convierte los prints de backend/core/dm_agent.py.
Haz commits cada 50 prints aproximadamente.
Actualiza PROGRESS.md después de cada commit.
```

### Para verificar estado:

```
Muéstrame el estado actual del refactoring.
¿Cuántos prints quedan?
¿Qué tareas están pendientes?
```

### Para empezar Phase 1:

```
Task 0.1 y 0.2 están completos.
Empieza Phase 1: extrae los endpoints de auth de main.py a routers/auth.py.
Sigue el proceso de refactor-standards.mdc.
```
