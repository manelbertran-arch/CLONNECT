# FIX MONOLÍTICO: Memoria Conversacional

**Copy-paste directo para arreglar el sistema de memoria.**

---

## ARCHIVO: `backend/core/dm_agent.py`

---

### FIX 1: Context-Aware Intent Classification

**BUSCAR** (alrededor de línea 1219-1250):
```python
        # === CORRECTION - MÁXIMA PRIORIDAD ===
        # Cuando el usuario corrige un malentendido
        correction_patterns = [
```

**REEMPLAZAR TODO EL BLOQUE** desde `# === CORRECTION` hasta antes de `# Escalación` con:

```python
        # === CORRECTION - MÁXIMA PRIORIDAD ===
        correction_patterns = [
            "no te he dicho", "no he dicho", "no dije", "eso no es lo que",
            "me has entendido mal", "no me entiendes", "no es eso",
            "te equivocas", "mal entendido"
        ]
        if any(p in msg for p in correction_patterns):
            return Intent.CORRECTION, 0.95

        # === CONTEXT-AWARE ACKNOWLEDGMENT ===
        # NUEVO: Analizar contexto antes de clasificar como ACKNOWLEDGMENT
        acknowledgment_words = ['sí', 'si', 'vale', 'ok', 'okay', 'dale', 'venga', 'claro', 'bueno', 'perfecto', 'genial', 'bien']
        msg_stripped = msg.strip().rstrip('!.?')

        if len(msg_stripped) < 25:
            is_acknowledgment = any(msg_stripped == w or msg_stripped.startswith(w + ' ') for w in acknowledgment_words)

            if is_acknowledgment:
                # NUEVO: Revisar contexto de la conversación
                # Si hay historial, analizar la última pregunta del bot
                if hasattr(self, '_current_conversation_history') and self._current_conversation_history:
                    last_bot_msg = None
                    for m in reversed(self._current_conversation_history):
                        if m.get("role") == "assistant":
                            last_bot_msg = m.get("content", "").lower()
                            break

                    if last_bot_msg and "?" in last_bot_msg:
                        # Si el bot preguntó sobre interés/más info -> INTEREST_SOFT
                        interest_keywords = ["saber más", "te cuento", "te explico", "te interesa",
                                           "quieres que", "te gustaría", "más información", "conocer"]
                        if any(kw in last_bot_msg for kw in interest_keywords):
                            logger.info(f"Context-aware: 'Si' after interest question -> INTEREST_SOFT")
                            return Intent.INTEREST_SOFT, 0.88

                        # Si el bot preguntó sobre compra -> INTEREST_STRONG
                        purchase_keywords = ["comprar", "pagar", "link", "precio", "adquirir", "reservar"]
                        if any(kw in last_bot_msg for kw in purchase_keywords):
                            logger.info(f"Context-aware: 'Si' after purchase question -> INTEREST_STRONG")
                            return Intent.INTEREST_STRONG, 0.88

                        # Si el bot hizo cualquier otra pregunta -> continuar conversación, no ACKNOWLEDGMENT
                        logger.info(f"Context-aware: 'Si' after question -> QUESTION_FOLLOWUP")
                        return Intent.INTEREST_SOFT, 0.75  # Tratar como interés soft para que continúe

                # Sin contexto o sin pregunta previa -> ACKNOWLEDGMENT original
                return Intent.ACKNOWLEDGMENT, 0.85
```

---

### FIX 2: Guardar Historial para Context-Aware Classification

**BUSCAR** la función `async def _process_single_message` (alrededor de línea 2500).

**AÑADIR** al inicio de la función, después de obtener el follower:

```python
        # NUEVO: Guardar historial para context-aware classification
        self._current_conversation_history = follower.last_messages.copy() if follower.last_messages else []
```

---

### FIX 3: Eliminar Fast Path de ACKNOWLEDGMENT

**BUSCAR** (alrededor de línea 2588-2605):
```python
        # === FAST PATH: Acknowledgment (Ok, Vale, Entendido) ===
        # User just confirms/acknowledges - don't assume purchase intent!
        if intent == Intent.ACKNOWLEDGMENT:
            logger.info(f"=== ACKNOWLEDGMENT DETECTED - NOT assuming purchase ===")
            # Use fallback responses for acknowledgment
            response_text = self._get_fallback_response(Intent.ACKNOWLEDGMENT, follower.preferred_language)
            await self._update_memory(follower, message_text, response_text, intent)

            return {
                "response": response_text,
                ...
            }
```

**REEMPLAZAR** todo ese bloque con:

```python
        # === ACKNOWLEDGMENT: Ahora pasa por flujo normal con contexto ===
        # ANTES: Fast path con respuesta hardcoded
        # AHORA: Deja que el LLM responda con contexto de la conversación
        if intent == Intent.ACKNOWLEDGMENT:
            logger.info(f"=== ACKNOWLEDGMENT - procesando con contexto conversacional ===")
            # NO retornar aquí - dejar que continúe al flujo normal con LLM
            # El LLM verá el historial y responderá apropiadamente
```

---

### FIX 4: Pasar Historial como Multi-Turn al LLM

**BUSCAR** la función `_call_llm` o donde se construyen los mensajes para el LLM (alrededor de línea 2900-2930).

**BUSCAR** algo como:
```python
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
```

**REEMPLAZAR** con:

```python
        # NUEVO: Construir conversación multi-turn real
        messages = [{"role": "system", "content": system_prompt}]

        # Añadir historial como mensajes reales (últimos 8 mensajes = 4 intercambios)
        if hasattr(self, '_current_conversation_history') and self._current_conversation_history:
            for msg in self._current_conversation_history[-8:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if content:  # Solo añadir si hay contenido
                    messages.append({"role": role, "content": content})

        # Mensaje actual del usuario
        messages.append({"role": "user", "content": message_text})

        logger.info(f"LLM call with {len(messages)} messages (including {len(messages)-2} history)")
```

---

### FIX 5: Añadir Instrucciones de Coherencia al System Prompt

**BUSCAR** en `_build_system_prompt` (alrededor de línea 2053) donde empieza:
```python
        base_prompt = f"""{magic_slice_tone}
{dynamic_rules}
{sales_strategy}
Eres {name}, un creador de contenido...
```

**AÑADIR** justo después de `{sales_strategy}`:

```python
        # NUEVO: Instrucciones de coherencia conversacional
        coherence_rules = """
=== REGLAS DE COHERENCIA CONVERSACIONAL (CRÍTICO) ===

ANTES de responder, SIEMPRE revisa la CONVERSACIÓN ANTERIOR:

1. Si el usuario dice "sí", "vale", "ok", "claro":
   → Responde a la ÚLTIMA PREGUNTA que TÚ hiciste
   → NO preguntes "¿en qué más puedo ayudarte?"
   → Ejemplo: Si preguntaste "¿quieres saber más sobre el curso?" y dice "sí" → explica el curso

2. Si el usuario dice "ya te lo dije", "te lo acabo de decir", "revisa el chat":
   → BUSCA en el historial qué dijo antes
   → Discúlpate brevemente y responde basándote en lo que YA dijo
   → Ejemplo: "Perdona, tienes razón. Mencionaste que te interesa [X]. Te cuento..."

3. NUNCA preguntes algo que el usuario YA respondió
   → Si ya dijo su nombre, no preguntes cómo se llama
   → Si ya dijo qué le interesa, no preguntes qué necesita

4. Mantén el HILO de la conversación
   → No cambies de tema abruptamente
   → Cada respuesta debe conectar con lo anterior

5. Si genuinamente pierdes el contexto:
   → Di: "Perdona, quiero asegurarme de entenderte bien. ¿Me confirmas que te interesa [último tema]?"

=== FIN REGLAS DE COHERENCIA ===
"""
```

Y luego modificar la línea del base_prompt:

```python
        base_prompt = f"""{magic_slice_tone}
{dynamic_rules}
{sales_strategy}
{coherence_rules}
Eres {name}, un creador de contenido que responde mensajes de Instagram/WhatsApp.
```

---

### FIX 6: Incrementar Historial en User Prompt

**BUSCAR** (alrededor de línea 2150):
```python
            for msg in conversation_history[-4:]:
```

**REEMPLAZAR** con:
```python
            for msg in conversation_history[-8:]:  # 8 mensajes = 4 intercambios completos
```

---

### FIX 7: Detectar Meta-Mensajes del Usuario

**AÑADIR** esta nueva función antes de `_classify_intent`:

```python
    def _detect_meta_message(self, message: str, history: List[dict]) -> Optional[str]:
        """
        Detecta cuando el usuario hace referencia a la conversación misma.
        Retorna una acción especial o None.
        """
        msg_lower = message.lower()

        # Patrones de "revisa lo que dije"
        review_patterns = [
            "ya te lo dije", "te lo dije", "ya te dije",
            "revisa el chat", "lee el chat", "mira el chat",
            "te lo acabo de decir", "lo acabo de decir",
            "ya te lo he dicho", "te lo he dicho",
            "lee arriba", "mira arriba", "scroll up"
        ]

        if any(p in msg_lower for p in review_patterns):
            # Buscar el último mensaje relevante del usuario
            user_messages = [m for m in history if m.get("role") == "user"]
            if len(user_messages) >= 2:
                # Retornar el penúltimo mensaje del usuario (lo que "ya dijo")
                previous_msg = user_messages[-2].get("content", "")
                return f"REVIEW_HISTORY:{previous_msg}"

        # Patrones de frustración
        frustration_patterns = [
            "no me entiendes", "no entiendes", "eres un bot",
            "habla con alguien", "persona real", "no sirves"
        ]

        if any(p in msg_lower for p in frustration_patterns):
            return "USER_FRUSTRATED"

        return None
```

**USAR** esta función al inicio de `_process_single_message`:

```python
        # NUEVO: Detectar meta-mensajes antes de clasificar intent
        meta_action = self._detect_meta_message(message_text, follower.last_messages)

        if meta_action:
            if meta_action.startswith("REVIEW_HISTORY:"):
                previous_context = meta_action.replace("REVIEW_HISTORY:", "")
                logger.info(f"Meta-message detected: User wants us to remember: {previous_context[:50]}...")
                # Inyectar contexto en el mensaje para el LLM
                message_text = f"[El usuario me pide que recuerde que dijo: '{previous_context}']\n\nUsuario: {message_text}"

            elif meta_action == "USER_FRUSTRATED":
                logger.warning(f"User frustration detected for {follower_id}")
                # Respuesta de recuperación
                response_text = "Perdona si no te he entendido bien. Cuéntame de nuevo qué necesitas y te ayudo ahora mismo."
                await self._update_memory(follower, message_text, response_text, Intent.OTHER)
                return {"response": response_text, "intent": "frustrated_recovery"}
```

---

## RESUMEN DE CAMBIOS

| Fix | Línea Aprox | Cambio |
|-----|-------------|--------|
| 1 | 1219-1250 | Context-aware intent classification |
| 2 | 2500+ | Guardar historial para clasificación |
| 3 | 2588-2605 | Eliminar fast path ACKNOWLEDGMENT |
| 4 | 2900-2930 | Multi-turn messages al LLM |
| 5 | 2053 | Instrucciones de coherencia |
| 6 | 2150 | Incrementar historial a 8 mensajes |
| 7 | Nueva función | Detectar meta-mensajes |

---

## TEST DESPUÉS DE APLICAR

Conversación esperada:

```
Usuario: "Hola, me interesa saber sobre tus servicios de coaching"
Bot: "¡Hola! Qué bien que te interese. ¿Qué aspecto te gustaría mejorar?"

Usuario: "Bajar niveles de ansiedad"
Bot: "Entiendo, la ansiedad es algo que trabajo mucho. ¿Quieres que te cuente cómo puedo ayudarte?"

Usuario: "Si"
Bot: "Perfecto! Tengo un programa de 8 semanas donde trabajamos técnicas de respiración, mindfulness y cambio de hábitos. El precio es 297€. ¿Te cuento más detalles?"
     ↑ AHORA responde al contexto, no "¿en qué más puedo ayudarte?"

Usuario: "Ya te lo he dicho antes"
Bot: "Tienes razón, perdona. Me dijiste que te interesa bajar los niveles de ansiedad. Te cuento entonces sobre el programa..."
     ↑ AHORA revisa el historial y recuerda
```

---

## ROLLBACK

Si algo falla, revertir con:
```bash
git checkout HEAD~1 -- backend/core/dm_agent.py
```
