from typing import Protocol, Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("clonnect.analytics.sales_tracker")

class StorageBackend(Protocol):
    async def load(self, key: str) -> List[Dict[str, Any]]: ...
    async def save(self, key: str, data: List[Dict[str, Any]]) -> None: ...
    async def append(self, key: str, item: Dict[str, Any]) -> None: ...

class SalesTracker:
    def __init__(self, storage: StorageBackend):
        self.storage = storage

    def _get_key(self, creator_id: str) -> str:
        return f"sales:{creator_id}"

    async def record_click(self, creator_id: str, product_id: str, follower_id: str, conversation_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> None:
        event = {"type": "click", "product_id": product_id, "follower_id": follower_id, "conversation_id": conversation_id, "metadata": metadata or {}, "timestamp": datetime.utcnow().isoformat()}
        await self.storage.append(self._get_key(creator_id), event)

    async def record_sale(self, creator_id: str, product_id: str, follower_id: str, amount: float, currency: str = "EUR", payment_id: Optional[str] = None, conversation_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> None:
        event = {"type": "sale", "product_id": product_id, "follower_id": follower_id, "amount": amount, "currency": currency, "payment_id": payment_id, "conversation_id": conversation_id, "metadata": metadata or {}, "timestamp": datetime.utcnow().isoformat()}
        await self.storage.append(self._get_key(creator_id), event)

    async def get_stats(self, creator_id: str, product_id: Optional[str] = None, days: Optional[int] = None) -> Dict[str, Any]:
        events = await self.storage.load(self._get_key(creator_id))
        if product_id:
            events = [e for e in events if e.get("product_id") == product_id]
        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            events = [e for e in events if datetime.fromisoformat(e.get("timestamp", "2000-01-01")) >= cutoff]
        clicks = [e for e in events if e.get("type") == "click"]
        sales = [e for e in events if e.get("type") == "sale"]
        total_revenue = sum(e.get("amount", 0) for e in sales)
        conversion_rate = len(sales) / len(clicks) if clicks else 0
        return {"total_clicks": len(clicks), "total_sales": len(sales), "total_revenue": total_revenue, "conversion_rate": conversion_rate}

    async def get_attributed_sales(self, creator_id: str, conversation_id: str) -> List[Dict[str, Any]]:
        events = await self.storage.load(self._get_key(creator_id))
        return [e for e in events if e.get("type") == "sale" and e.get("conversation_id") == conversation_id]
