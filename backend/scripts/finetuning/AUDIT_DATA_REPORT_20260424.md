# AUDIT DATA REPORT — Iris Fine-Tuning — 2026-04-24

## Ejecutivo

- **5,739 registros** en `sft_full.jsonl` (Instagram DMs, formato ChatML 3-turn)
- **13.2% de artefactos explícitos** (tags `[audio]`, `[sticker]`, `[🎬 Video]`, `[🎤 Audio]`, `Sent an attachment`) en respuestas de Iris — supera el umbral del 5% del `01_audit_datasets.py` → **filtrado obligatorio**
- **Filtro quirúrgico** (solo tags + URLs) elimina 758 registros y deja **4,981 limpios (86.8%)** — nivel mínimo recomendado antes de SFT
- **Filtro conservador** (añade solo-emoji + muy cortos <5 chars) deja **4,852 (84.5%)** — recomendado para primera iteración
- **WhatsApp no disponible** — requiere export manual desde iPhone; sin este dataset el entrenamiento se hace 100% sobre DMs de Instagram

---

## Fuente 1: Instagram DMs (sft_full.jsonl)

### Schema

Todos los registros tienen exactamente un top-level key: `messages`.  
Formato **ChatML 3-turn** fijo: `[system, user, assistant]`.

```json
{
  "messages": [
    {"role": "system",    "content": "⚠️ REGLAS CRITICAS — APLICA SIEMPRE: ..."},
    {"role": "user",      "content": "<mensaje del lead>"},
    {"role": "assistant", "content": "<respuesta de Iris>"}
  ]
}
```

- **System prompt**: idéntico en los 5,739 registros (510 chars). Contiene: regla de idioma (ca/es), emojis prohibidos de bot, regla de clusters de emojis.
- **No hay metadata adicional**: sin `conversation_id`, `trust_level`, `lead_type`, `timestamp` ni ningún otro campo.
- **Ratio conversación**: cada record es 1 user-turn → 1 assistant-turn (no hay conversaciones multi-turno). El "contexto" de la conversación queda fuera del dataset.

### Stats brutas

| Métrica | Valor |
|---------|-------|
| Total records | 5,739 |
| Total chars (respuestas Iris) | ~410,000 aprox. |
| Longitud media respuesta Iris | 71.5 chars |
| Longitud mediana (P50) | 46 chars |
| P25 | 23 chars |
| P75 | 89 chars |
| P90 | 161 chars |
| Records con artefactos explícitos | 758 (13.2%) |
| Records solo-emoji (Iris) | 74 (1.3%) |
| Records muy cortos <5 chars | 55 (1.0%) |
| Records cortos 5-20 chars | 1,171 (20.4%) |
| Records con emoji spam (>5 emojis únicos o >30% chars) | 299 (5.2%) |
| Records con URL en respuesta Iris | 0 (0.0%) |
| User messages solo-emoji | 152 (2.6%) |
| User messages con audio transcrito [🎤] | 124 (2.2%) |
| Idioma: otro/neutral | 3,745 (65.3%) |
| Idioma: catalán | 1,217 (21.2%) |
| Idioma: español | 672 (11.7%) |
| Idioma: mixto ca+es | 105 (1.8%) |

### Distribución longitudes respuestas Iris

| Bucket (chars) | Count | % |
|---------------|-------|---|
| 0–49 | 3,039 | 52.9% |
| 50–99 | 1,470 | 25.6% |
| 100–149 | 574 | 10.0% |
| 150–199 | 261 | 4.5% |
| 200–249 | 159 | 2.8% |
| 250–299 | 80 | 1.4% |
| 300–349 | 55 | 1.0% |
| 350–399 | 45 | 0.8% |
| 400–449 | 33 | 0.6% |
| 450+ | 73 | 1.3% |

Percentiles clave: **P25=23, P50=46, P75=89, P90=161 chars**  
El 53% de las respuestas caben en 50 chars — Iris es concisa. La cola larga (P90=161) corresponde a respuestas de venta/sesiones.

### Top-10 emojis usados por Iris

| Emoji | Count |
|-------|-------|
| 😂 | 2,973 |
| ❤️ (componente) | 1,392 |
| ❤ | 1,074 |
| 😘 | 771 |
| (skin tone 🏽) | 727 |
| 🫠 | 620 |
| 🩷 | 565 |
| 🤣 | 548 |
| 🥹 | 390 |
| 🫶 | 328 |

Nota: `🏽` (tono de piel médio-oscuro) aparece como componente de emojis de mano — no es emoji autónomo. `❤️` se split en dos code points Unicode, de ahí la doble entrada.

### Artefactos detectados

| Tipo | Count | % del total |
|------|-------|-------------|
| `[audio]` | 315 | 5.5% |
| `[sticker]` | 286 | 5.0% |
| `[🎤 Audio]` (con transcripción) | 101 | 1.8% |
| `[video]` | 64 | 1.1% |
| `Sent an attachment` | 21 | 0.4% |
| `[🎬 Video]` | 8 | 0.1% |
| **Total records afectados** | **758** | **13.2%** |

Nota: `[🎤 Audio]: <transcripción>` es distinto — la respuesta de Iris contiene el audio transcrito seguido de texto. Algunos de estos pueden ser recuperables eliminando sólo el prefijo de tag y conservando la transcripción. Los `[audio]` y `[sticker]` bare son irrecuperables (cero información de respuesta).

### Volumen por filtro level

| Filtro | Records | % conservado | Descripción |
|--------|---------|--------------|-------------|
| Sin filtro | 5,739 | 100% | Dataset bruto |
| Quirúrgico | 4,981 | 86.8% | Drop: tags explícitos de media (`[audio]`, `[sticker]`, `[video]`, `Sent an attachment`, etc.) |
| Conservador | 4,852 | 84.5% | Quirúrgico + drop solo-emoji + drop <5 chars |
| Estricto | 4,650 | 81.0% | Conservador + drop emoji spam (>5 emojis únicos o >30% chars emoji) |

### Muestra de records contaminados (5 ejemplos anónimos)

**[1] tag_video_emoji** — Iris responde solo con un tag de video sin texto.
```
Lead_001: 😍
Iris:     [🎬 Video]
          Te veoo a les 18:30 ja tas apuntada cuca
```
*Nota: este ejemplo tiene texto útil después del tag — podría sanearse quitando `[🎬 Video]\n`.*

**[2] tag_video_emoji** — respuesta vacía de contenido.
```
Lead_002: No llego a Hipos estamos atascados en la calle de atrás obras 🤪 llevamos 10 min
Iris:     [🎬 Video]
```
*Solo tag, cero información — descartar.*

**[3] sent_attachment** — metadato de sistema de Instagram.
```
Lead_003: Mentioned you in their story
Iris:     Ella, Gabriel García Marquez
          Sent an attachment
          Te he pasado los 2
```
*"Sent an attachment" es ruido de export — el texto antes/después puede ser recuperable.*

**[4] tag_audio_emoji con transcripción** — el prefijo `[🎤 Audio]:` precede contenido real.
```
Lead_004: Vale cap problema
Iris:     [🎤 Audio]: Cuca, el que vulguis. Avui és la sessió nova, espero que us agradi molt...
```
*Recuperable si se strip el prefijo `[🎤 Audio]: ` y se conserva la transcripción.*

**[5] sent_attachment inline** — fragmento de conversación con attachment intercalado.
```
Lead_005: Reina ! Pásame el vídeo pf
Iris:     Este lo viste?
          Sent an attachment
          Te he pasado los 2
```
*Podría sanearse eliminando la línea `Sent an attachment`.*

---

## Fuente 2: WhatsApp

### No Disponible

**Búsqueda realizada:** `find ~ -name "*WhatsApp*" -o -name "*_chat.txt"` sobre todo el home del usuario (2025-04-23). Resultado: solo imágenes y audios sueltos en `~/Downloads`. Ningún archivo `.txt` ni `.zip` de export de conversación encontrado.

**Motivo probable:** Las conversaciones de WhatsApp residen en el iPhone y no han sido exportadas manualmente.

**Instrucciones para exportar desde iPhone:**

1. Abrir **WhatsApp** en el iPhone
2. Ir a la conversación que se quiere exportar
3. Tocar el nombre/número en la cabecera para ver el perfil
4. Hacer scroll hasta encontrar **"Exportar chat"**
5. Seleccionar **"Sin media"** (los adjuntos no añaden valor al SFT)
6. Elegir destino: **AirDrop al Mac** o **Guardar en Files → iCloud Drive**

**Nombre del archivo resultante:** `Chat de [Nombre Contacto].zip`  
Al extraer el zip: `_chat.txt` (formato WhatsApp estándar con timestamps)

**Dónde depositar cuando esté listo:**
```
~/Clonnect/backend/data/raw_whatsapp/
```
(Crear el directorio si no existe: `mkdir -p ~/Clonnect/backend/data/raw_whatsapp/`)

**Priorizar:** conversaciones de sesiones de coaching/venta (mayor densidad de respuestas largas y con identidad Iris). Evitar grupos o chats muy cortos (<50 mensajes).

---

## Recomendación

### OPCION A — Solo Instagram, Filtro Conservador (RECOMENDADA ahora)

**Ejecutar con:** filtro conservador → **4,852 records limpios (84.5%)**

Justificación numérica:
- Elimina el 100% de los tags explícitos irrecuperables (316+286+64+21+8 = 695 pure-noise records)
- Elimina los 74 solo-emoji de Iris (cero signal) y 55 respuestas <5 chars (ruido)
- Conserva el 84.5% del dataset original — suficiente para SFT con modelos de 7-9B
- **No** aplica filtro estricto porque el emoji spam en Iris (5.2%) es muchas veces legítimo (clusters de 😂😂😂 son señal de estilo, no ruido)

**Advertencia post-WhatsApp:** si se obtienen exports de WhatsApp con >500 mensajes de Iris, repetir el audit y combinar datasets. Las conversaciones de WhatsApp suelen tener más contexto multi-turno y mayor longitud de respuesta (P50 previsiblemente >80 chars), lo que compensaría el sesgo de mensajes cortos del dataset actual (P50=46 chars).

**Opción B (alternativa):** Aplicar filtro quirúrgico (4,981 records) y sanear manualmente los ~63 casos de `[🎤 Audio]:` stripando el prefijo para recuperar la transcripción. Beneficio: +129 records de audio transcrito que contienen respuestas de venta/sesión de mayor longitud. Coste: ~1h de trabajo manual o script de limpieza específico.

**No recomendado ahora:**
- **Opción C** (filtro estricto, 4,650): recorta demasiado el emoji-spam que es estilo auténtico de Iris
- **Opción D** (dataset bruto sin filtrar): 13.2% de contaminación confirmada — degrada fine-tuning

---

## Próximos pasos

1. **Ejecutar filtro conservador** sobre `sft_full.jsonl` → output `data/dpo/trl/sft_conservador.jsonl` (4,852 records)
2. **Opcionalmente** aplicar script de strip de `[🎤 Audio]:` para recuperar ~101 registros con transcripción (ver Opción B)
3. **Exportar WhatsApp** desde iPhone siguiendo instrucciones de §Fuente 2 — depositar en `data/raw_whatsapp/`
4. Si WhatsApp disponible: parsear `_chat.txt` → formato ChatML → re-audit antes de combinar
5. Con dataset limpio: ejecutar `scripts/finetuning/02_sft_config.py` para configurar run SFT
6. Verificar distribución ca/es en dataset final — actualmente 65.3% "other/neutral", 21.2% catalán, 11.7% español; si el target es ~50% catalán, considerar over-sampling de ca-records
7. Considerar añadir `conversation_id` y `timestamp` al pipeline de extracción de DMs para habilitar ventanas multi-turno en próxima iteración del dataset
