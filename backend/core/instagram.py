"""
Instagram Connector para Clonnect MVP
Maneja: OAuth, Webhooks, Send/Receive DMs, Content Ingestion
"""

import os
import json
import aiohttp
import hashlib
import hmac
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class InstagramMessage:
    """Representa un mensaje de Instagram DM"""
    message_id: str
    sender_id: str
    recipient_id: str
    text: str
    timestamp: datetime
    attachments: List[dict] = None

    def __post_init__(self):
        if self.attachments is None:
            self.attachments = []


@dataclass
class InstagramUser:
    """Representa un usuario de Instagram"""
    user_id: str
    username: str
    name: str
    profile_pic_url: str = ""


class InstagramConnector:
    """Conector principal para Instagram Graph API"""

    # API de Facebook para operaciones generales (media, conversations)
    FACEBOOK_API_URL = "https://graph.facebook.com/v21.0"
    # API de Instagram para mensajes DM (requiere token IGAA)
    INSTAGRAM_API_URL = "https://graph.instagram.com/v21.0"

    def __init__(
        self,
        access_token: str,
        page_id: str,
        ig_user_id: str,
        app_secret: str = None,
        verify_token: str = None
    ):
        self.access_token = access_token
        self.page_id = page_id
        self.ig_user_id = ig_user_id
        self.app_secret = app_secret or os.getenv("INSTAGRAM_APP_SECRET", "")
        self.verify_token = verify_token or os.getenv("INSTAGRAM_VERIFY_TOKEN", "clonnect_verify_2024")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Obtener o crear sesión HTTP"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Cerrar sesión HTTP"""
        if self._session and not self._session.closed:
            await self._session.close()

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verificar firma HMAC del webhook de Meta"""
        if not self.app_secret:
            return True  # Skip en desarrollo
        expected = hmac.new(
            self.app_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

    def verify_webhook_challenge(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """Verificar challenge de webhook (GET request de Meta)"""
        if mode == "subscribe" and token == self.verify_token:
            return challenge
        return None

    async def handle_webhook_event(self, payload: dict) -> List[InstagramMessage]:
        """Procesar evento de webhook y extraer mensajes"""
        messages = []

        try:
            for entry in payload.get("entry", []):
                for messaging in entry.get("messaging", []):
                    if "message" in messaging:
                        msg = InstagramMessage(
                            message_id=messaging["message"].get("mid", ""),
                            sender_id=messaging["sender"]["id"],
                            recipient_id=messaging["recipient"]["id"],
                            text=messaging["message"].get("text", ""),
                            timestamp=datetime.fromtimestamp(
                                messaging.get("timestamp", 0) / 1000
                            ),
                            attachments=messaging["message"].get("attachments", [])
                        )
                        messages.append(msg)
        except Exception as e:
            logger.error(f"Error parsing webhook: {e}")

        return messages

    async def send_message(self, recipient_id: str, text: str) -> dict:
        """Enviar mensaje directo a un usuario via Instagram API"""
        session = await self._get_session()
        # Usar Instagram API para enviar mensajes (requiere token IGAA)
        url = f"{self.INSTAGRAM_API_URL}/me/messages"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": text}
        }

        async with session.post(url, json=payload, headers=headers) as resp:
            result = await resp.json()
            if "error" in result:
                logger.error(f"Error sending message: {result['error']}")
            else:
                logger.info(f"Message sent to {recipient_id} via Instagram API")
            return result

    async def send_message_with_buttons(
        self,
        recipient_id: str,
        text: str,
        buttons: List[Dict[str, str]]
    ) -> dict:
        """Enviar mensaje con botones de respuesta rápida via Instagram API"""
        session = await self._get_session()
        # Usar Instagram API para enviar mensajes (requiere token IGAA)
        url = f"{self.INSTAGRAM_API_URL}/me/messages"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        quick_replies = [
            {
                "content_type": "text",
                "title": btn.get("title", ""),
                "payload": btn.get("payload", btn.get("title", ""))
            }
            for btn in buttons[:13]  # Máximo 13 quick replies
        ]

        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "text": text,
                "quick_replies": quick_replies
            }
        }

        async with session.post(url, json=payload, headers=headers) as resp:
            result = await resp.json()
            if "error" in result:
                logger.error(f"Error sending message with buttons: {result['error']}")
            return result

    async def get_user_profile(self, user_id: str) -> Optional[InstagramUser]:
        """Obtener perfil de usuario de Instagram"""
        session = await self._get_session()
        url = f"{self.FACEBOOK_API_URL}/{user_id}"
        params = {
            "fields": "id,username,name,profile_pic",
            "access_token": self.access_token
        }

        async with session.get(url, params=params) as resp:
            data = await resp.json()
            if "error" in data:
                logger.error(f"Error getting profile: {data['error']}")
                return None

            return InstagramUser(
                user_id=data.get("id", user_id),
                username=data.get("username", ""),
                name=data.get("name", ""),
                profile_pic_url=data.get("profile_pic", "")
            )

    async def get_media(self, limit: int = 100) -> List[dict]:
        """Obtener posts/reels del creador"""
        session = await self._get_session()
        url = f"{self.FACEBOOK_API_URL}/{self.ig_user_id}/media"
        params = {
            "fields": "id,caption,media_type,media_url,timestamp,permalink,like_count,comments_count",
            "limit": limit,
            "access_token": self.access_token
        }

        async with session.get(url, params=params) as resp:
            data = await resp.json()
            return data.get("data", [])

    async def get_conversations(self, limit: int = 20) -> List[dict]:
        """Obtener conversaciones recientes"""
        session = await self._get_session()
        url = f"{self.FACEBOOK_API_URL}/{self.page_id}/conversations"
        params = {
            "platform": "instagram",
            "limit": limit,
            "access_token": self.access_token
        }

        async with session.get(url, params=params) as resp:
            data = await resp.json()
            return data.get("data", [])

    async def get_conversation_messages(
        self,
        conversation_id: str,
        limit: int = 50
    ) -> List[dict]:
        """Obtener mensajes de una conversación"""
        session = await self._get_session()
        url = f"{self.FACEBOOK_API_URL}/{conversation_id}/messages"
        params = {
            "fields": "id,message,from,to,created_time",
            "limit": limit,
            "access_token": self.access_token
        }

        async with session.get(url, params=params) as resp:
            data = await resp.json()
            return data.get("data", [])

    async def mark_message_seen(self, sender_id: str) -> dict:
        """Marcar mensajes como vistos via Instagram API"""
        session = await self._get_session()
        url = f"{self.INSTAGRAM_API_URL}/me/messages"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "recipient": {"id": sender_id},
            "sender_action": "mark_seen"
        }

        async with session.post(url, json=payload, headers=headers) as resp:
            return await resp.json()

    async def send_typing_indicator(self, recipient_id: str, typing_on: bool = True) -> dict:
        """Enviar indicador de 'escribiendo...' via Instagram API"""
        session = await self._get_session()
        url = f"{self.INSTAGRAM_API_URL}/me/messages"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "recipient": {"id": recipient_id},
            "sender_action": "typing_on" if typing_on else "typing_off"
        }

        async with session.post(url, json=payload, headers=headers) as resp:
            return await resp.json()


class InstagramContentIngester:
    """Ingestor de contenido de Instagram al RAG"""

    def __init__(self, connector: InstagramConnector, rag_adapter, creator_id: str):
        self.connector = connector
        self.rag_adapter = rag_adapter
        self.creator_id = creator_id

    async def ingest_posts(self, limit: int = 100) -> dict:
        """Ingestar posts del creador al RAG"""
        media = await self.connector.get_media(limit=limit)
        ingested = 0
        errors = 0

        for item in media:
            if item.get("caption"):
                doc = {
                    "id": f"ig_post_{item['id']}",
                    "text": item["caption"],
                    "metadata": {
                        "source": "instagram",
                        "type": item.get("media_type", "IMAGE"),
                        "url": item.get("permalink", ""),
                        "timestamp": item.get("timestamp", ""),
                        "creator_id": self.creator_id,
                        "likes": item.get("like_count", 0),
                        "comments": item.get("comments_count", 0)
                    }
                }

                try:
                    if hasattr(self.rag_adapter, 'add_document'):
                        self.rag_adapter.add_document(
                            doc_id=doc["id"],
                            text=doc["text"],
                            metadata=doc["metadata"]
                        )
                    ingested += 1
                except Exception as e:
                    logger.error(f"Error ingesting post {item['id']}: {e}")
                    errors += 1

        logger.info(f"Ingested {ingested} posts for creator {self.creator_id}")
        return {
            "ingested": ingested,
            "errors": errors,
            "total": len(media)
        }

    async def ingest_document(self, file_path: str, doc_type: str = "pdf") -> dict:
        """Ingestar documento adicional (PDF, texto)"""
        try:
            from core.multimodal import MultiModalProcessor
            processor = MultiModalProcessor()

            if doc_type == "pdf":
                content = processor.process_pdf(file_path)
            elif doc_type in ["jpg", "jpeg", "png"]:
                content = processor.process_image(file_path)
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

            doc_id = f"doc_{self.creator_id}_{os.path.basename(file_path)}"

            if hasattr(self.rag_adapter, 'add_document'):
                self.rag_adapter.add_document(
                    doc_id=doc_id,
                    text=content,
                    metadata={
                        "source": "upload",
                        "type": doc_type,
                        "creator_id": self.creator_id,
                        "filename": os.path.basename(file_path)
                    }
                )

            return {"status": "ok", "doc_id": doc_id, "chars": len(content)}

        except Exception as e:
            logger.error(f"Error ingesting document: {e}")
            return {"status": "error", "error": str(e)}

    async def ingest_faq(self, faqs: List[Dict[str, str]]) -> dict:
        """Ingestar lista de preguntas frecuentes"""
        ingested = 0

        for i, faq in enumerate(faqs):
            question = faq.get("question", "")
            answer = faq.get("answer", "")

            if question and answer:
                doc_id = f"faq_{self.creator_id}_{i}"
                text = f"Pregunta: {question}\nRespuesta: {answer}"

                try:
                    if hasattr(self.rag_adapter, 'add_document'):
                        self.rag_adapter.add_document(
                            doc_id=doc_id,
                            text=text,
                            metadata={
                                "source": "faq",
                                "type": "qa",
                                "creator_id": self.creator_id,
                                "question": question
                            }
                        )
                    ingested += 1
                except Exception as e:
                    logger.error(f"Error ingesting FAQ {i}: {e}")

        return {"ingested": ingested, "total": len(faqs)}


class InstagramWebhookHandler:
    """Handler para procesar webhooks de Instagram en tiempo real"""

    def __init__(self, connector: InstagramConnector, dm_agent=None):
        self.connector = connector
        self.dm_agent = dm_agent
        self._message_handlers = []

    def add_message_handler(self, handler):
        """Añadir handler para mensajes entrantes"""
        self._message_handlers.append(handler)

    async def process_webhook(self, payload: dict, signature: str = "") -> dict:
        """Procesar webhook completo"""

        # Verificar firma si hay app_secret
        if self.connector.app_secret and signature:
            payload_bytes = json.dumps(payload).encode()
            if not self.connector.verify_webhook_signature(payload_bytes, signature):
                logger.warning("Invalid webhook signature")
                return {"status": "error", "reason": "invalid_signature"}

        # Extraer mensajes
        messages = await self.connector.handle_webhook_event(payload)

        results = []
        for message in messages:
            # Ignorar mensajes propios
            if message.sender_id == self.connector.page_id:
                continue

            logger.info(f"Processing message from {message.sender_id}: {message.text[:50]}")

            # Procesar con DM agent si disponible
            if self.dm_agent:
                try:
                    response = await self.dm_agent.process_dm(
                        sender_id=message.sender_id,
                        message_text=message.text,
                        message_id=message.message_id
                    )
                    results.append({
                        "message_id": message.message_id,
                        "sender_id": message.sender_id,
                        "response": response.response_text,
                        "intent": response.intent.value
                    })
                except Exception as e:
                    logger.error(f"Error processing with DM agent: {e}")

            # Llamar handlers adicionales
            for handler in self._message_handlers:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error(f"Error in message handler: {e}")

        return {
            "status": "ok",
            "messages_processed": len(messages),
            "results": results
        }
