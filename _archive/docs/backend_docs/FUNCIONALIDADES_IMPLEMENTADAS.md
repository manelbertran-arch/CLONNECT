# Funcionalidades Implementadas - Clonnect Creators

## Resumen de Cambios

Este documento contiene todas las funcionalidades y fixes implementados en esta sesión.

---

## 1. TAREA 1: Instagram Webhook - Variables de Entorno

### Variables necesarias para Railway:

| Variable | Requerida | Descripción |
|----------|-----------|-------------|
| `INSTAGRAM_ACCESS_TOKEN` | ✅ Sí | Token de Meta Graph API para enviar mensajes |
| `INSTAGRAM_PAGE_ID` | ✅ Sí | ID de la página de Facebook vinculada |
| `INSTAGRAM_USER_ID` | ✅ Sí | ID de la cuenta Instagram Business/Creator |
| `INSTAGRAM_APP_SECRET` | ⚠️ Recomendado | Para verificar firmas de webhook |
| `INSTAGRAM_VERIFY_TOKEN` | ❌ Tiene default | Token para verificación (default: `clonnect_verify_2024`) |

### Archivos relevantes:
- `core/instagram_handler.py:67-71` - Lee las variables de entorno
- `api/main.py:926-996` - Endpoints del webhook

---

## 2. TAREA 2: Endpoint Enviar Mensaje Manual

### Backend - `api/main.py`

```python
class SendMessageRequest(BaseModel):
    """Request to send a manual message to a follower"""
    follower_id: str
    message: str


@app.post("/dm/send/{creator_id}")
async def send_manual_message(creator_id: str, request: SendMessageRequest):
    """
    Send a manual message to a follower.

    The message will be sent via the appropriate platform (Telegram, Instagram, WhatsApp)
    based on the follower_id prefix:
    - tg_* -> Telegram
    - ig_* -> Instagram
    - wa_* -> WhatsApp

    The message is also saved in the conversation history.
    """
    try:
        follower_id = request.follower_id
        message_text = request.message

        if not message_text.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        # Detect platform from follower_id prefix
        if follower_id.startswith("tg_"):
            platform = "telegram"
            chat_id = follower_id.replace("tg_", "")
        elif follower_id.startswith("ig_"):
            platform = "instagram"
            recipient_id = follower_id.replace("ig_", "")
        elif follower_id.startswith("wa_"):
            platform = "whatsapp"
            phone = follower_id.replace("wa_", "")
        else:
            # Assume Instagram for legacy IDs without prefix
            platform = "instagram"
            recipient_id = follower_id

        sent = False

        # Send via appropriate platform
        if platform == "telegram" and TELEGRAM_BOT_TOKEN:
            try:
                telegram_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                async with httpx.AsyncClient() as client:
                    resp = await client.post(telegram_api, json={
                        "chat_id": int(chat_id),
                        "text": message_text,
                        "parse_mode": "HTML"
                    })
                    if resp.status_code == 200:
                        sent = True
                        logger.info(f"Manual message sent to Telegram chat {chat_id}")
            except Exception as e:
                logger.error(f"Error sending Telegram message: {e}")

        elif platform == "instagram":
            try:
                handler = get_instagram_handler()
                if handler.connector:
                    sent = await handler.send_response(recipient_id, message_text)
                    if sent:
                        logger.info(f"Manual message sent to Instagram {recipient_id}")
            except Exception as e:
                logger.error(f"Error sending Instagram message: {e}")

        elif platform == "whatsapp":
            try:
                wa_handler = get_whatsapp_handler()
                if wa_handler and wa_handler.connector:
                    result = await wa_handler.connector.send_message(phone, message_text)
                    sent = "error" not in result
                    if sent:
                        logger.info(f"Manual message sent to WhatsApp {phone}")
            except Exception as e:
                logger.error(f"Error sending WhatsApp message: {e}")

        # Save the message in conversation history
        agent = get_dm_agent(creator_id)
        await agent.save_manual_message(follower_id, message_text, sent)

        return {
            "status": "ok",
            "sent": sent,
            "platform": platform,
            "follower_id": follower_id,
            "message_preview": message_text[:100] + "..." if len(message_text) > 100 else message_text
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending manual message: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### Backend - `core/dm_agent.py` - Método save_manual_message

```python
async def save_manual_message(
    self,
    follower_id: str,
    message_text: str,
    sent: bool = True
) -> bool:
    """
    Save a manually sent message in the conversation history.

    Args:
        follower_id: The follower's ID
        message_text: The message text that was sent
        sent: Whether the message was successfully sent

    Returns:
        True if saved successfully
    """
    try:
        follower = await self.memory_store.get(self.creator_id, follower_id)

        if not follower:
            logger.warning(f"Follower {follower_id} not found for saving manual message")
            return False

        # Add the message to history
        timestamp = datetime.now(timezone.utc).isoformat()
        follower.last_messages.append({
            "role": "assistant",
            "content": message_text,
            "timestamp": timestamp,
            "manual": True,  # Mark as manually sent
            "sent": sent
        })

        # Keep only last 50 messages
        if len(follower.last_messages) > 50:
            follower.last_messages = follower.last_messages[-50:]

        # Update last contact time
        follower.last_contact = timestamp

        # Save to memory store
        await self.memory_store.save(follower)

        logger.info(f"Saved manual message for {follower_id}")
        return True

    except Exception as e:
        logger.error(f"Error saving manual message: {e}")
        return False
```

### Frontend - `src/services/api.ts`

```typescript
/**
 * Send a manual message to a follower
 */
export async function sendMessage(
  creatorId: string = CREATOR_ID,
  followerId: string,
  message: string
): Promise<{ status: string; sent: boolean; platform: string; follower_id: string }> {
  return apiFetch(`/dm/send/${creatorId}`, {
    method: "POST",
    body: JSON.stringify({ follower_id: followerId, message }),
  });
}
```

### Frontend - `src/hooks/useApi.ts`

```typescript
/**
 * Hook to send a manual message to a follower
 */
export function useSendMessage(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ followerId, message }: { followerId: string; message: string }) =>
      sendMessage(creatorId, followerId, message),
    onSuccess: (_, variables) => {
      // Invalidate the follower detail to refresh conversation history
      queryClient.invalidateQueries({
        queryKey: apiKeys.follower(creatorId, variables.followerId)
      });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
    },
  });
}
```

### Frontend - `src/pages/Inbox.tsx` - Handler y botón

```typescript
// Handle sending a manual message
const handleSend = async () => {
  console.log("handleSend called", { selectedId, message: message.trim() });

  if (!selectedId || !message.trim()) {
    console.log("handleSend early return - missing data");
    return;
  }

  console.log("Calling sendMessageMutation...");
  try {
    const result = await sendMessageMutation.mutateAsync({
      followerId: selectedId,
      message: message.trim(),
    });
    console.log("sendMessageMutation result:", result);

    if (result.sent) {
      toast({
        title: "Message sent",
        description: `Sent via ${result.platform}`,
      });
    } else {
      toast({
        title: "Message saved",
        description: "Message saved but delivery pending (platform not connected)",
        variant: "destructive",
      });
    }
    setMessage(""); // Clear input on success
  } catch (error) {
    console.error("sendMessageMutation error:", error);
    toast({
      title: "Error sending message",
      description: error instanceof Error ? error.message : "Failed to send",
      variant: "destructive",
    });
  }
};

// Handle enter key to send
const handleKeyDown = (e: React.KeyboardEvent) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
};

// Botón de enviar
<Button
  type="button"
  onClick={() => {
    console.log("Send button clicked!", { selectedId, message, isPending: sendMessageMutation.isPending });
    handleSend();
  }}
  disabled={!selectedId || !message.trim() || sendMessageMutation.isPending}
  className="bg-gradient-to-r from-primary to-accent hover:opacity-90 transition-opacity"
>
  {sendMessageMutation.isPending ? (
    <Loader2 className="w-4 h-4 animate-spin" />
  ) : (
    <Send className="w-4 h-4" />
  )}
</Button>
```

---

## 3. TAREA 3: Endpoint Actualizar Status de Lead

### Backend - `api/main.py`

```python
class UpdateLeadStatusRequest(BaseModel):
    """Request to update lead status in pipeline"""
    status: str  # cold, warm, hot, customer


@app.put("/dm/follower/{creator_id}/{follower_id}/status")
async def update_follower_status(
    creator_id: str,
    follower_id: str,
    request: UpdateLeadStatusRequest
):
    """
    Update the lead status for a follower.

    Valid status values:
    - cold: New follower, low intent (purchase_intent < 0.3)
    - warm: Engaged follower, medium intent (purchase_intent 0.3-0.7)
    - hot: High purchase intent (purchase_intent > 0.7)
    - customer: Has made a purchase
    """
    try:
        valid_statuses = ["cold", "warm", "hot", "customer"]
        status = request.status.lower()

        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {valid_statuses}"
            )

        # Map status to purchase_intent score
        status_to_score = {
            "cold": 0.15,
            "warm": 0.50,
            "hot": 0.85,
            "customer": 1.0
        }

        agent = get_dm_agent(creator_id)
        success = await agent.update_follower_status(
            follower_id=follower_id,
            status=status,
            purchase_intent=status_to_score[status],
            is_customer=(status == "customer")
        )

        if not success:
            raise HTTPException(status_code=404, detail="Follower not found")

        logger.info(f"Updated status for {follower_id} to {status}")

        return {
            "status": "ok",
            "follower_id": follower_id,
            "new_status": status,
            "purchase_intent": status_to_score[status]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating follower status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### Backend - `core/dm_agent.py` - Método update_follower_status

```python
async def update_follower_status(
    self,
    follower_id: str,
    status: str,
    purchase_intent: float,
    is_customer: bool = False
) -> bool:
    """
    Update the lead status for a follower.

    Args:
        follower_id: The follower's ID
        status: The new status (cold, warm, hot, customer)
        purchase_intent: The purchase intent score (0.0 to 1.0)
        is_customer: Whether the follower is now a customer

    Returns:
        True if updated successfully
    """
    try:
        follower = await self.memory_store.get(self.creator_id, follower_id)

        if not follower:
            logger.warning(f"Follower {follower_id} not found for status update")
            return False

        # Update the follower's status
        old_score = follower.purchase_intent_score
        follower.purchase_intent_score = purchase_intent

        # Update is_lead based on score
        if purchase_intent >= 0.3:
            follower.is_lead = True

        # Update is_customer
        if is_customer:
            follower.is_customer = True

        # Save to memory store (no message added to history)
        await self.memory_store.save(follower)

        logger.info(f"Updated status for {follower_id}: {status} (intent: {old_score:.0%} → {purchase_intent:.0%})")
        return True

    except Exception as e:
        logger.error(f"Error updating follower status: {e}")
        return False
```

### Frontend - `src/services/api.ts`

```typescript
/**
 * Update the lead status for a follower
 */
export async function updateLeadStatus(
  creatorId: string = CREATOR_ID,
  followerId: string,
  status: "cold" | "warm" | "hot" | "customer"
): Promise<{ status: string; follower_id: string; new_status: string; purchase_intent: number }> {
  return apiFetch(`/dm/follower/${creatorId}/${followerId}/status`, {
    method: "PUT",
    body: JSON.stringify({ status }),
  });
}
```

### Frontend - `src/hooks/useApi.ts`

```typescript
/**
 * Hook to update lead status (for drag & drop in pipeline)
 */
export function useUpdateLeadStatus(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      followerId,
      status
    }: {
      followerId: string;
      status: "cold" | "warm" | "hot" | "customer";
    }) => updateLeadStatus(creatorId, followerId, status),
    onSuccess: (_, variables) => {
      // Invalidate leads, conversations, and follower detail
      queryClient.invalidateQueries({ queryKey: apiKeys.leads(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
      queryClient.invalidateQueries({
        queryKey: apiKeys.follower(creatorId, variables.followerId)
      });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}
```

### Frontend - `src/pages/Leads.tsx` - Drag & Drop Handler

```typescript
// Map UI status to backend status
const statusToBackend: Record<LeadStatus, "cold" | "warm" | "hot" | "customer"> = {
  new: "cold",
  active: "warm",
  hot: "hot",
  customer: "customer",
};

const handleDrop = async (status: LeadStatus) => {
  if (!draggedLead || draggedLead.status === status) {
    setDraggedLead(null);
    return;
  }

  const leadId = draggedLead.id;
  const oldStatus = draggedLead.status;

  // Optimistic update - update local state immediately
  setLocalStatusOverrides(prev => ({
    ...prev,
    [leadId]: status
  }));
  setDraggedLead(null);

  // Call API to persist the change
  try {
    await updateStatusMutation.mutateAsync({
      followerId: leadId,
      status: statusToBackend[status],
    });

    toast({
      title: "Status updated",
      description: `Lead moved to ${status.toUpperCase()}`,
    });
  } catch (error) {
    // Revert on error
    setLocalStatusOverrides(prev => ({
      ...prev,
      [leadId]: oldStatus
    }));

    toast({
      title: "Error updating status",
      description: error instanceof Error ? error.message : "Failed to update",
      variant: "destructive",
    });
  }
};
```

---

## 4. FIX: Instagram Bot Loop Infinito

### `core/instagram_handler.py` - Filtro is_echo

```python
async def _extract_messages(self, payload: Dict[str, Any]) -> List[InstagramMessage]:
    """Extract messages from webhook payload"""
    messages = []

    try:
        for entry in payload.get("entry", []):
            for messaging in entry.get("messaging", []):
                if "message" in messaging:
                    message_data = messaging["message"]

                    # CRITICAL: Skip echo messages (messages sent BY the page/bot)
                    # Meta sends is_echo=true for messages we sent
                    if message_data.get("is_echo"):
                        logger.info(f"Skipping echo message (sent by bot)")
                        continue

                    # Skip if sender is same as recipient (edge case)
                    sender_id = messaging.get("sender", {}).get("id", "")
                    recipient_id = messaging.get("recipient", {}).get("id", "")
                    if sender_id == recipient_id:
                        logger.info(f"Skipping message where sender==recipient")
                        continue

                    msg = InstagramMessage(
                        message_id=message_data.get("mid", ""),
                        sender_id=sender_id,
                        recipient_id=recipient_id,
                        text=message_data.get("text", ""),
                        timestamp=datetime.fromtimestamp(
                            messaging.get("timestamp", 0) / 1000
                        ),
                        attachments=message_data.get("attachments", [])
                    )
                    if msg.text:  # Only process text messages
                        messages.append(msg)
    except Exception as e:
        logger.error(f"Error extracting messages from webhook: {e}")

    return messages
```

### `core/instagram_handler.py` - Filtros adicionales en handle_webhook

```python
results = []
for message in messages:
    # Skip messages from our own page/account (prevent self-reply loop)
    if message.sender_id == self.page_id:
        logger.info(f"Skipping message from page_id: {message.sender_id}")
        continue
    if self.ig_user_id and message.sender_id == self.ig_user_id:
        logger.info(f"Skipping message from ig_user_id: {message.sender_id}")
        continue

    # Additional safety: skip if recipient_id matches sender_id
    if message.recipient_id and message.sender_id == message.recipient_id:
        logger.info(f"Skipping self-message: {message.sender_id}")
        continue

    self._record_received(message)
```

---

## 5. FIX: memory_store.save() Argumentos Incorrectos

### Problema
La llamada era:
```python
await self.memory_store.save(self.creator_id, follower)  # INCORRECTO
```

### Solución
```python
await self.memory_store.save(follower)  # CORRECTO
```

Aplicado en:
- `save_manual_message()` línea 1780
- `update_follower_status()` línea 1828

---

## 6. FIX: Status Changes No Deben Aparecer en Conversación

### Código eliminado de `update_follower_status`:

```python
# ELIMINADO - No añadir status changes al historial
# timestamp = datetime.now(timezone.utc).isoformat()
# follower.last_messages.append({
#     "role": "system",
#     "content": f"[Status changed to {status.upper()}] (score: {old_score:.0%} → {purchase_intent:.0%})",
#     "timestamp": timestamp
# })
```

---

## 7. FIX: Botón Enviar Deshabilitado

### Problema
El botón no verificaba si había una conversación seleccionada.

### Solución en `Inbox.tsx`:

```typescript
// ANTES:
disabled={!message.trim() || sendMessageMutation.isPending}

// DESPUÉS:
disabled={!selectedId || !message.trim() || sendMessageMutation.isPending}
```

---

## Commits Realizados

| Commit | Descripción |
|--------|-------------|
| `2ec8842` | feat: add manual message sending and lead status update endpoints |
| `2638f29` | feat: connect manual messaging and lead status to backend |
| `0b77446` | fix: correct memory_store.save() call signature |
| `580b40c` | fix: disable send button when no conversation selected |
| `11796b2` | debug: add console.log to diagnose send button issue |
| `814a6e8` | fix: prevent Instagram bot from responding to its own messages |
| `5aee1e9` | fix: don't add status changes to conversation history |

---

## Endpoints Nuevos

### POST /dm/send/{creator_id}
Envía mensaje manual a un follower.

**Request:**
```json
{
  "follower_id": "tg_1359681305",
  "message": "Hola, ¿cómo estás?"
}
```

**Response:**
```json
{
  "status": "ok",
  "sent": true,
  "platform": "telegram",
  "follower_id": "tg_1359681305",
  "message_preview": "Hola, ¿cómo estás?"
}
```

### PUT /dm/follower/{creator_id}/{follower_id}/status
Actualiza el status de un lead.

**Request:**
```json
{
  "status": "hot"
}
```

**Response:**
```json
{
  "status": "ok",
  "follower_id": "tg_1359681305",
  "new_status": "hot",
  "purchase_intent": 0.85
}
```

---

## Mapeo de Status

| UI Status | Backend Status | purchase_intent |
|-----------|----------------|-----------------|
| new | cold | 0.15 |
| active | warm | 0.50 |
| hot | hot | 0.85 |
| customer | customer | 1.0 |
