# CHANGELOG - Clonnect Creators

## [1.4.0] - 2026-01-25 - Context Injection V2

### Added
- `core/creator_data_loader.py`: Centraliza carga de datos del creador (752 líneas)
  - Productos, precios, links de pago
  - Booking links, FAQ, tone profile
  - Caché de 5 minutos
- `core/user_context_loader.py`: Carga contexto del usuario (672 líneas)
  - Perfil, historial, preferencias
  - Lead info, productos discutidos
  - Caché de 1 minuto
- `core/context_detector.py`: Detecta contexto del mensaje (1007 líneas)
  - Frustración (none/mild/moderate/severe)
  - Sarcasmo con word boundaries
  - B2B (caso Silvia)
  - Nivel de interés, objeciones
- `core/prompt_builder.py`: Construye prompts con todo el contexto (675 líneas)
  - Secciones: identidad, datos, usuario, alertas, reglas, acciones
  - Instrucciones de conversión migradas
- `core/output_validator.py`: Valida respuestas anti-alucinación (739 líneas)
  - Validación de precios conocidos
  - Validación de links conocidos
  - Smart truncate que protege URLs y precios
- `tests/test_integration_v2.py`: Tests de integración (28 tests)
  - Caso Silvia B2B
  - Usuario frustrado, booking, precios
  - Anti-alucinación, escalación, lead magnet
- Feature flag `ENABLE_CONTEXT_INJECTION_V2` para rollback fácil

### Changed
- `core/dm_agent.py`: Nuevo flujo con context injection (+240 líneas)
  - 12 fast paths ahora condicionados con `use_legacy_fast_paths`
  - Integración de los 5 módulos nuevos
  - Logging detallado con prefijo `[CONTEXT_INJECTION_V2]`

### Fixed
- **Caso Silvia B2B**: Ya no se detecta como frustración
  - Word boundaries en regex (`\baja\b` no matchea "trabajado")
  - Detección de patrón "de [Empresa]" como B2B
- **Truncate**: Ya no corta URLs ni precios a mitad
- **Sarcasmo**: False positives eliminados con word boundaries

### Tests
- 69 tests para context_detector
- 46 tests para prompt_builder
- 46 tests para output_validator
- 28 tests de integración
- **Total: 189 tests nuevos**

### Documentation
- `docs/ARCHITECTURE_V2.md`: Arquitectura completa con diagramas
- `docs/MIGRATION_V2.md`: Guía de migración y rollback

### Metrics
- % mensajes al LLM: 45% → 97%
- Fast paths hardcoded: 12 → 0 (condicionados)

## [1.3.0] - 2026-01-17
### Added
- Sistema inteligente de señales y predicción de ventas (`api/services/signals.py`)
  - 30+ señales de compra/interés/objeciones
  - Detección automática de productos mencionados
  - Análisis de comportamiento (tiempo respuesta, longitud msgs)
  - Predicción de probabilidad de venta con confianza
  - Sugerencias de siguiente paso personalizadas
- Endpoint GET `/dm/leads/{creator_id}/escalations` para alertas de escalación
- Tests completos para signals.py (27 tests)

### Improved
- Caching con TTL de 5 minutos para análisis de señales
- Error handling robusto con graceful degradation
- Safe attribute access para evitar crashes
- Pestaña Actividad en frontend con métricas visuales

### Verified
- Rate limiter ya integrado en dm_agent.py ✓
- Notificaciones de escalación ya funcionando ✓
- Metodología Clonnect aplicada (no N+1, caching, error handling)

## [1.2.0] - 2026-01-16
### Added
- CRM completo con actividades y tareas
- Sistema de notas, email, teléfono por lead
- Historial de actividades con eliminación
- Animación de completar tareas

### Fixed
- Fix guardado de datos CRM (email, phone, notes)
- Fix pestaña Actividad vacía
- Fix rol de mensajes (user/assistant)

## [1.1.0] - 2026-01-15
### Added
- Pipeline visual con drag & drop
- Lead scoring por etapa del funnel
- Fotos de perfil en cards de Pipeline
- Click en foto abre perfil de Instagram

### Improved
- Unificación de etiquetas en español
- Mejora de colores en tags de status

## [1.0.1] - 2025-12-03
### Fixed
- Tests actualizados - 82/82 tests pasando
- Corregido imports y decoradores async

## [1.0.0] - 2025-12-02
### Added
- 45 funcionalidades MVP completas
- Instagram, WhatsApp, Telegram
- 9 idiomas, memoria por seguidor
- Stripe, Hotmart, Calendly
- 70+ endpoints API
