"""
Sales Tracker for Clonnect Creators.

Tracks clicks on product links and completed sales for conversion analytics.
Storage: JSON files in data/sales/
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from collections import defaultdict

logger = logging.getLogger("clonnect-sales-tracker")


class SalesTracker:
    """Tracker de ventas y conversiones"""

    def __init__(self, storage_path: str = "data/sales"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self._cache: Dict[str, List[dict]] = {}

    def _get_file(self, creator_id: str) -> str:
        return os.path.join(self.storage_path, f"{creator_id}_sales.json")

    def _load_sales(self, creator_id: str) -> List[dict]:
        if creator_id in self._cache:
            return self._cache[creator_id]

        filepath = self._get_file(creator_id)
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                sales = json.load(f)
                self._cache[creator_id] = sales
                return sales
        except Exception as e:
            logger.error(f"Error loading sales: {e}")
            return []

    def _save_sales(self, creator_id: str, sales: List[dict]):
        filepath = self._get_file(creator_id)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(sales, f, indent=2, ensure_ascii=False)
            self._cache[creator_id] = sales
        except Exception as e:
            logger.error(f"Error saving sales: {e}")

    def record_click(
        self,
        creator_id: str,
        product_id: str,
        follower_id: str,
        product_name: str = "",
        link_url: str = ""
    ):
        """Registrar clic en link de producto"""
        sales = self._load_sales(creator_id)
        sales.append({
            "type": "click",
            "product_id": product_id,
            "product_name": product_name,
            "follower_id": follower_id,
            "link_url": link_url,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self._save_sales(creator_id, sales)
        logger.info(f"Click recorded: {follower_id} -> {product_id}")

    def record_sale(
        self,
        creator_id: str,
        product_id: str,
        follower_id: str,
        amount: float,
        currency: str = "EUR",
        product_name: str = "",
        external_id: str = "",
        platform: str = "unknown"
    ):
        """Registrar venta completada"""
        sales = self._load_sales(creator_id)
        sales.append({
            "type": "sale",
            "product_id": product_id,
            "product_name": product_name,
            "follower_id": follower_id,
            "amount": amount,
            "currency": currency,
            "external_id": external_id,
            "platform": platform,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self._save_sales(creator_id, sales)
        logger.info(f"Sale recorded: {follower_id} -> {product_id} ({amount} {currency})")

    def get_stats(self, creator_id: str, days: int = 30) -> dict:
        """Obtener estadísticas de ventas"""
        sales = self._load_sales(creator_id)

        clicks = [s for s in sales if s.get("type") == "click"]
        completed_sales = [s for s in sales if s.get("type") == "sale"]
        total_revenue = sum(s.get("amount", 0) for s in completed_sales)

        # Stats by product
        clicks_by_product: Dict[str, int] = defaultdict(int)
        sales_by_product: Dict[str, int] = defaultdict(int)
        revenue_by_product: Dict[str, float] = defaultdict(float)

        for click in clicks:
            product_id = click.get("product_id", "unknown")
            clicks_by_product[product_id] += 1

        for sale in completed_sales:
            product_id = sale.get("product_id", "unknown")
            sales_by_product[product_id] += 1
            revenue_by_product[product_id] += sale.get("amount", 0)

        # Unique clickers who converted
        clickers = set(c.get("follower_id") for c in clicks)
        buyers = set(s.get("follower_id") for s in completed_sales)
        converted_clickers = clickers & buyers

        return {
            "total_clicks": len(clicks),
            "unique_clickers": len(clickers),
            "total_sales": len(completed_sales),
            "unique_buyers": len(buyers),
            "total_revenue": total_revenue,
            "conversion_rate": len(converted_clickers) / len(clickers) if clickers else 0,
            "avg_order_value": total_revenue / len(completed_sales) if completed_sales else 0,
            "clicks_by_product": dict(clicks_by_product),
            "sales_by_product": dict(sales_by_product),
            "revenue_by_product": dict(revenue_by_product)
        }

    def get_recent_activity(self, creator_id: str, limit: int = 20) -> List[dict]:
        """Get recent clicks and sales"""
        sales = self._load_sales(creator_id)
        # Sort by timestamp descending
        sorted_sales = sorted(sales, key=lambda x: x.get("timestamp", ""), reverse=True)
        return sorted_sales[:limit]

    def get_follower_journey(self, creator_id: str, follower_id: str) -> List[dict]:
        """Get all activity for a specific follower"""
        sales = self._load_sales(creator_id)
        follower_activity = [s for s in sales if s.get("follower_id") == follower_id]
        return sorted(follower_activity, key=lambda x: x.get("timestamp", ""))


# Global instance
_sales_tracker: Optional[SalesTracker] = None


def get_sales_tracker() -> SalesTracker:
    """Get or create sales tracker singleton"""
    global _sales_tracker
    if _sales_tracker is None:
        _sales_tracker = SalesTracker()
    return _sales_tracker
