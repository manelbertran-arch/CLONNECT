# AUDITORIA DE FAST PATHS - Estado actual

**Fecha:** 2026-01-25
**Branch:** refactor/context-injection-v2 (baseline desde main)
**Archivo:** `core/dm_agent.py` (6548 lineas)

## Fast paths que cortocircuitan (NO llegan al LLM)

| # | Nombre | Linea | Trigger | Respuesta | Action |
|---|--------|-------|---------|-----------|--------|
| 1 | Bot Paused | 4230-4238 | `bot_active=false` | Respuesta vacia | `bot_paused` |
| 2 | Rate Limiter | 4247-4265 | `rate_limited=true` | "Dame un momento..." | `rate_limited` |
| 3 | GDPR Consent | 4318-4321 | `REQUIRE_CONSENT=true` y sin consentimiento | Request consent | - |
| 4 | USER_FRUSTRATED | 4353-4362 | Patrones frustracion ("ya te lo dije", etc) | "Perdona si no te he entendido bien..." | `frustrated_recovery` |
| 5 | SARCASM_DETECTED | 4380-4389 | Patrones sarcasmo | "Entiendo que estas frustrado..." | `sarcasm_recovery` |
| 6 | ESCALATION | 4398-4431 | `intent=ESCALATION` | Escalacion + notificacion | `escalate` |
| 7 | BOOKING | 4434-4462 | `intent=BOOKING` | Links de reserva formateados | `show_booking_links` |
| 8 | INTEREST_STRONG | 4465-4516 | `intent=INTEREST_STRONG` | Links de pago | `show_payment_links` |
| 9 | Direct Payment | 4544-4577 | Pregunta bizum/revolut/paypal/etc | Datos de pago alternativos | `direct_payment_method` |
| 10 | Price Question | 4579-4677 | "cuanto cuesta" + producto encontrado | Precio directo | `direct_price_response` |
| 11 | Direct Purchase | 4679-4849 | `is_direct_purchase_intent()` | Solo link de pago | `direct_purchase_link` |
| 12 | INTEREST_SOFT | 4855-4885 | `intent=INTEREST_SOFT` | Info producto destacado | `interest_soft_product_info` |
| 13 | LEAD_MAGNET | 4890-4923 | `intent=LEAD_MAGNET` | Link gratis o alternativa | `lead_magnet_response` |
| 14 | THANKS post-booking | 4928-4997 | `intent=THANKS` + ultimo mensaje=booking | "Perfecto! Ahi te espero..." | `thanks_after_booking` |
| 15 | Anti-Hallucination | 5003-5058 | `intent in INTENTS_REQUIRING_RAG` y NO hay RAG content | Escalacion automatica | `escalate_no_rag` |

## Paths que MODIFICAN el mensaje pero SI van al LLM

| # | Nombre | Linea | Trigger | Accion |
|---|--------|-------|---------|--------|
| A | REVIEW_HISTORY | 4364-4368 | "revisa lo que dije" | Inyecta contexto en mensaje |
| B | REPEAT_REQUESTED | 4370-4373 | "repite por favor" | Inyecta ultimo mensaje |
| C | IMPLICIT_REFERENCE | 4375-4378 | Referencia implicita | Inyecta contexto previo |
| D | ACKNOWLEDGMENT | 4523-4525 | `intent=ACKNOWLEDGMENT` | NO retorna - va al LLM |
| E | CORRECTION | 4531-4533 | `intent=CORRECTION` | NO retorna - va al LLM |

## Intents que requieren RAG (Anti-Alucinacion)

Definidos en linea 304-321 como `INTENTS_REQUIRING_RAG`:

```python
INTENTS_REQUIRING_RAG = {
    Intent.QUESTION_PRODUCT,      # Preguntas sobre productos
    Intent.QUESTION_METHODOLOGY,  # Preguntas sobre metodologia
    Intent.QUESTION_LOGISTICS,    # Preguntas sobre logistica
    Intent.QUESTION_PERSONAL,     # Preguntas personales sobre el creador
    Intent.QUESTION_PRICING,      # Preguntas de precios (si no hay fast path)
    Intent.OBJECTION_PRICE,       # Objeciones de precio
    Intent.OBJECTION_DOUBT,       # Dudas/objeciones
}
```

## Estimacion de trafico

Basado en la estructura del codigo:

| Categoria | Estimacion | Notas |
|-----------|------------|-------|
| Fast paths (sin LLM) | ~35-45% | 15 paths diferentes |
| Cache HIT | ~10-15% | TTL 5 minutos en config/productos |
| LLM con RAG | ~25-35% | Requiere embedding search |
| LLM sin RAG | ~15-25% | Saludos, despedidas, etc |

## Problemas identificados

### 1. Fast path de frustracion muy agresivo
- **Linea:** 4353-4362
- **Problema:** Detecta "frustrado" incluso en contextos B2B validos
- **Ejemplo:** "Silvia de Bamos" podria triggear si menciona "antes" o "ya"

### 2. INTEREST_SOFT siempre muestra producto featured
- **Linea:** 4855-4885
- **Problema:** No considera el contexto del mensaje
- **Ejemplo:** Usuario pregunta por tema X, bot responde con producto Y

### 3. Anti-alucinacion escala demasiado rapido
- **Linea:** 5003-5058
- **Problema:** Si `min_relevance=0.25` no encuentra nada, escala
- **Ejemplo:** Pregunta valida pero con palabras diferentes

### 4. THANKS post-booking muy especifico
- **Linea:** 4928-4997
- **Problema:** Solo detecta keywords muy especificos de booking
- **Ejemplo:** Otros tipos de agradecimiento van al LLM

## Orden de evaluacion de fast paths

```
1. bot_paused
2. rate_limited
3. gdpr_consent
4. meta_messages (frustrated, sarcasm, review, repeat, implicit)
5. intent=ESCALATION
6. intent=BOOKING
7. intent=INTEREST_STRONG
8. direct_payment_question
9. price_question
10. direct_purchase
11. intent=INTEREST_SOFT
12. intent=LEAD_MAGNET
13. intent=THANKS (post-booking)
14. anti_hallucination (INTENTS_REQUIRING_RAG)
15. --> LLM <--
```

## Metricas clave a capturar

Para el refactor, necesitamos medir:

1. **Tiempo de respuesta** por tipo de path
2. **Tasa de escalacion** (actual vs nueva)
3. **Tasa de "frustracion detectada"** (falsos positivos)
4. **Uso de LLM** (tokens consumidos)
5. **Satisfaction del usuario** (si hay THANKS despues de respuesta)

---

*Este documento sirve como referencia para el refactor de arquitectura.*
*Actualizar despues de cada fase del refactor.*
