# Arquitectura V2 - Context Injection

## Resumen Ejecutivo

El refactor **Context Injection V2** reemplaza los 12+ fast paths que cortocircuitaban el LLM por un sistema donde el **LLM siempre decide**, pero con toda la información necesaria inyectada en el prompt.

### Métricas Objetivo
| Métrica | Antes (V1) | Después (V2) |
|---------|------------|--------------|
| % mensajes al LLM | 45% | 97% |
| Fast paths hardcoded | 12+ | 0 (condicionados) |
| Caso Silvia B2B | "frustrado" | profesional |

## Diagrama de Flujo

```
                    ┌─────────────────┐
                    │  Mensaje entrante │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Filtros técnicos │
                    │ (bot paused,     │
                    │  rate limit,     │
                    │  GDPR)           │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ CreatorDataLoader│ │UserContextLoader│ │ ContextDetector │
│                 │ │                 │ │                 │
│ - Productos     │ │ - Nombre        │ │ - Frustración   │
│ - Precios       │ │ - Historial     │ │ - Sarcasmo      │
│ - Links pago    │ │ - Preferencias  │ │ - B2B           │
│ - Booking       │ │ - Intent score  │ │ - Interés       │
│ - FAQ           │ │ - Productos     │ │ - Objeciones    │
│ - Tone profile  │ │   discutidos    │ │ - Meta-mensajes │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼────────┐
                    │  PromptBuilder   │
                    │                 │
                    │ Combina todo en │
                    │ system prompt:  │
                    │ - Identidad     │
                    │ - Datos         │
                    │ - Usuario       │
                    │ - Alertas       │
                    │ - Reglas        │
                    │ - Acciones      │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │      LLM        │
                    │   (Groq/GPT)    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ OutputValidator  │
                    │                 │
                    │ - Precios OK?   │
                    │ - Links OK?     │
                    │ - Productos OK? │
                    │ - Truncate      │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Respuesta final │
                    └─────────────────┘
```

## Módulos Nuevos

| Módulo | Archivo | Líneas | Función |
|--------|---------|--------|---------|
| CreatorDataLoader | `core/creator_data_loader.py` | 752 | Carga productos, precios, links, booking, FAQ, tone |
| UserContextLoader | `core/user_context_loader.py` | 672 | Carga perfil usuario, historial, preferencias |
| ContextDetector | `core/context_detector.py` | 1007 | Detecta frustración, sarcasmo, B2B, interés, objeciones |
| PromptBuilder | `core/prompt_builder.py` | 675 | Construye system prompt completo con todo el contexto |
| OutputValidator | `core/output_validator.py` | 739 | Valida precios, links, productos post-LLM |

### Dataclasses Principales

```python
# creator_data_loader.py
@dataclass
class CreatorData:
    creator_id: str
    profile: CreatorProfile
    products: List[ProductInfo]
    booking_links: List[BookingInfo]
    payment_methods: PaymentMethods
    lead_magnets: List[ProductInfo]
    faqs: List[FAQInfo]
    tone_profile: ToneProfileInfo

# user_context_loader.py
@dataclass
class UserContext:
    follower_id: str
    creator_id: str
    name: str
    preferred_language: str
    total_messages: int
    purchase_intent_score: float
    products_discussed: List[str]
    recent_messages: List[ConversationMessage]
    lead_info: LeadInfo

# context_detector.py
@dataclass
class DetectedContext:
    sentiment: str          # frustrated, sarcastic, positive, neutral
    frustration_level: str  # none, mild, moderate, severe
    is_b2b: bool
    company_context: str
    intent: Intent
    interest_level: str     # strong, soft, none
    user_name: str
    alerts: List[str]
```

## Feature Flag

```bash
# Activar V2 (default)
export ENABLE_CONTEXT_INJECTION_V2=true

# Rollback a V1 (fast paths)
export ENABLE_CONTEXT_INJECTION_V2=false
```

El flag está definido en `core/dm_agent.py`:
```python
ENABLE_CONTEXT_INJECTION_V2 = os.getenv("ENABLE_CONTEXT_INJECTION_V2", "true").lower() == "true"
```

## Fast Paths Migrados

Los siguientes fast paths ahora están **condicionados** con `use_legacy_fast_paths`:

| Fast Path | Línea | Comportamiento V2 |
|-----------|-------|-------------------|
| USER_FRUSTRATED | 4369 | ContextDetector detecta, PromptBuilder inyecta alerta |
| SARCASM_DETECTED | 4401 | ContextDetector detecta, PromptBuilder inyecta alerta |
| ESCALATION | 4478 | LLM decide con contexto de escalación |
| BOOKING | 4514 | Links de booking en prompt, LLM los incluye |
| INTEREST_STRONG | 4545 | Links de pago en prompt, LLM los ofrece |
| Direct Payment | 4634 | Métodos de pago en prompt |
| Price Question | 4679 | Precios en prompt, OutputValidator verifica |
| Direct Purchase | 4762 | Links en prompt, LLM los da |
| INTEREST_SOFT | 4935 | Productos en prompt, LLM presenta |
| LEAD_MAGNET | 4970 | Lead magnets en prompt |
| THANKS | 5008 | Contexto de booking en historial |
| Anti-hallucination | 5084 | OutputValidator verifica post-LLM |

## Caching

| Módulo | TTL | Qué cachea |
|--------|-----|------------|
| CreatorDataLoader | 5 min | Productos, config, tone profile |
| UserContextLoader | 1 min | Perfil usuario, historial reciente |

## Tests

```bash
# Tests unitarios por módulo
pytest tests/test_context_detector.py -v      # 69 tests
pytest tests/test_prompt_builder.py -v        # 46 tests
pytest tests/test_output_validator.py -v      # 46 tests

# Tests de integración V2
pytest tests/test_integration_v2.py -v        # 28 tests

# Total: 189 tests
```

## Caso Silvia (B2B) - El Fix Principal

### Problema (V1)
```
Usuario: "Hola! Les escribe Silvia de Bamos, ya habíamos trabajado antes"
Bot V1:  "Entiendo que estás frustrado..." ❌
```

El patrón "trabajado" contenía "aja" que disparaba detección de sarcasmo.

### Solución (V2)
1. **Word boundaries** en regex: `\baja\b` no matchea "trabajado"
2. **detect_b2b()** reconoce "de [Empresa]" y "trabajado antes"
3. Si es B2B, se resetea frustración a "none"
4. PromptBuilder inyecta sección B2B profesional

```
Usuario: "Hola! Les escribe Silvia de Bamos, ya habíamos trabajado antes"
Bot V2:  "¡Hola Silvia! Qué gusto volver a saber de ti..." ✅
```

## Anti-Alucinación

### Validaciones Post-LLM
1. **Precios**: Solo acepta precios que existen en `CreatorData.products`
2. **Links**: Solo permite URLs conocidas o dominios permitidos
3. **Productos**: Advierte si menciona productos desconocidos

### Ejemplo
```python
# Respuesta del LLM
"El programa cuesta 500€, cómpralo en https://fake.com"

# OutputValidator detecta:
- Precio 500€ NO está en productos conocidos (297€, 497€)
- URL https://fake.com NO es conocida

# Resultado: is_valid=False, should_escalate=True
```

## Logging

Todos los logs V2 usan el prefijo `[CONTEXT_INJECTION_V2]`:

```
[CONTEXT_INJECTION_V2] Creator data loaded: 5 products
[CONTEXT_INJECTION_V2] User context loaded: name=Carlos, messages=12
[CONTEXT_INJECTION_V2] Context detected: sentiment=neutral, frustration=none, b2b=True
[CONTEXT_INJECTION_V2] Built prompt with PromptBuilder: 2450 chars
[CONTEXT_INJECTION_V2] Response validated: price_valid=True, links_valid=True
```

## Archivos Modificados

```
core/
├── dm_agent.py           # +240 líneas (integración)
├── creator_data_loader.py # NUEVO (752 líneas)
├── user_context_loader.py # NUEVO (672 líneas)
├── context_detector.py    # NUEVO (1007 líneas)
├── prompt_builder.py      # NUEVO (675 líneas)
└── output_validator.py    # NUEVO (739 líneas)

tests/
├── test_context_detector.py   # NUEVO (69 tests)
├── test_prompt_builder.py     # NUEVO (46 tests)
├── test_output_validator.py   # NUEVO (46 tests)
└── test_integration_v2.py     # NUEVO (28 tests)
```

## Próximos Pasos

1. **Monitoreo**: Verificar métricas de % LLM en producción
2. **Ajustes**: Tunear prompts según feedback real
3. **Cleanup**: Remover fast paths legacy después de validar en prod
