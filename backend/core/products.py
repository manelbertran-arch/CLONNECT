"""
Gestión de productos y servicios del creador
"""

import os
import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Product:
    """Representa un producto/servicio del creador"""
    id: str
    name: str
    description: str
    price: float
    currency: str = "EUR"
    payment_link: str = ""
    category: str = ""
    features: List[str] = field(default_factory=list)
    objection_handlers: Dict[str, str] = field(default_factory=dict)
    keywords: List[str] = field(default_factory=list)
    testimonials: List[str] = field(default_factory=list)
    faq: List[Dict[str, str]] = field(default_factory=list)
    is_active: bool = True
    is_featured: bool = False
    stock: int = -1  # -1 = ilimitado
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Product':
        # Filtrar solo campos válidos
        valid_fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid_fields)

    def matches_query(self, query: str) -> float:
        """Verificar si el producto coincide con una consulta, devuelve score"""
        query_lower = query.lower()
        score = 0.0

        # Coincidencia con keywords (más peso)
        for kw in self.keywords:
            if kw.lower() in query_lower:
                score += 0.4

        # Coincidencia con nombre
        if self.name.lower() in query_lower or query_lower in self.name.lower():
            score += 0.3

        # Coincidencia con categoría
        if self.category.lower() in query_lower:
            score += 0.2

        # Coincidencia con descripción
        if any(word in self.description.lower() for word in query_lower.split()):
            score += 0.1

        return min(score, 1.0)

    def get_short_description(self, max_length: int = 100) -> str:
        """Obtener descripción corta"""
        if len(self.description) <= max_length:
            return self.description
        return self.description[:max_length-3] + "..."


class ProductManager:
    """Gestor de productos del creador"""

    DEFAULT_OBJECTION_HANDLERS = {
        "precio": "Entiendo que el precio es una consideración importante. {product_name} incluye {features_count} módulos/características que te ayudarán a {main_benefit}. Muchos de mis alumnos han recuperado la inversión en menos de {roi_time}. ¿Te gustaría que te cuente más sobre lo que incluye?",
        "tiempo": "Sé que el tiempo es valioso. Por eso {product_name} está diseñado para que puedas avanzar a tu ritmo. Tienes acceso de por vida y cada lección dura máximo 15-20 minutos. ¿Cuánto tiempo podrías dedicarle a la semana?",
        "despues": "¡Claro! Sin presión. Te dejo el link por si quieres guardarlo: {payment_link}. Si tienes dudas, aquí estoy 😊",
        "pensarlo": "Por supuesto, tómate tu tiempo. ¿Hay algo específico que te gustaría saber antes de decidir? Estoy aquí para resolver cualquier duda 💪",
        "funciona": "Te entiendo, todos queremos resultados. Te cuento que {testimonial}. Además, tienes garantía de {guarantee_days} días. Si no te convence, te devuelvo el dinero sin preguntas.",
        "no_se": "Es normal tener dudas. ¿Qué es lo que más te preocupa? Así puedo ayudarte mejor 😊",
        "complicado": "Te entiendo. {product_name} está diseñado para principiantes, con explicaciones paso a paso. Además, tienes acceso a soporte si te atascas en algo. ¿Qué parte te preocupa más?",
        "ya_tengo": "¡Genial que ya tengas experiencia! {product_name} va más allá de lo básico y te enseña {advanced_feature}. ¿Qué nivel dirías que tienes actualmente?"
    }

    def __init__(self, storage_path: str = "data/products"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)

    def _get_creator_file(self, creator_id: str) -> str:
        return os.path.join(self.storage_path, f"{creator_id}_products.json")

    def _load_products(self, creator_id: str) -> List[Product]:
        filepath = self._get_creator_file(creator_id)
        if not os.path.exists(filepath):
            return []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [Product.from_dict(p) for p in data]
        except Exception as e:
            logger.error(f"Error loading products for {creator_id}: {e}")
            return []

    def _save_products(self, creator_id: str, products: List[Product]):
        filepath = self._get_creator_file(creator_id)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump([p.to_dict() for p in products], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving products for {creator_id}: {e}")

    def add_product(self, creator_id: str, product: Product) -> str:
        """Añadir producto"""
        products = self._load_products(creator_id)

        # Verificar ID único
        existing_ids = {p.id for p in products}
        if product.id in existing_ids:
            # Generar ID único
            base_id = product.id
            counter = 1
            while product.id in existing_ids:
                product.id = f"{base_id}_{counter}"
                counter += 1

        # Añadir handlers por defecto si no hay
        if not product.objection_handlers:
            product.objection_handlers = self.DEFAULT_OBJECTION_HANDLERS.copy()

        # Generar keywords automáticas si no hay
        if not product.keywords:
            product.keywords = self._generate_keywords(product)

        products.append(product)
        self._save_products(creator_id, products)
        logger.info(f"Product {product.id} added for creator {creator_id}")
        return product.id

    def _generate_keywords(self, product: Product) -> List[str]:
        """Generar keywords automáticas del producto"""
        keywords = []

        # Del nombre
        keywords.extend(product.name.lower().split())

        # De la categoría
        if product.category:
            keywords.append(product.category.lower())

        # De la descripción (palabras importantes)
        important_words = ["curso", "programa", "mentoría", "coaching", "ebook",
                         "guía", "plantilla", "master", "formación", "servicio"]
        desc_lower = product.description.lower()
        for word in important_words:
            if word in desc_lower:
                keywords.append(word)

        return list(set(keywords))

    def get_products(self, creator_id: str, active_only: bool = True) -> List[Product]:
        """Obtener todos los productos del creador"""
        products = self._load_products(creator_id)
        if active_only:
            products = [p for p in products if p.is_active]
        return products

    def get_product_by_id(self, creator_id: str, product_id: str) -> Optional[Product]:
        """Obtener producto específico"""
        products = self._load_products(creator_id)
        for p in products:
            if p.id == product_id:
                return p
        return None

    def update_product(self, creator_id: str, product_id: str, updates: dict) -> Optional[Product]:
        """Actualizar producto"""
        products = self._load_products(creator_id)
        for i, p in enumerate(products):
            if p.id == product_id:
                for key, value in updates.items():
                    if hasattr(p, key):
                        setattr(p, key, value)
                p.updated_at = datetime.now().isoformat()
                self._save_products(creator_id, products)
                return p
        return None

    def delete_product(self, creator_id: str, product_id: str) -> bool:
        """Eliminar producto"""
        products = self._load_products(creator_id)
        original_len = len(products)
        products = [p for p in products if p.id != product_id]

        if len(products) < original_len:
            self._save_products(creator_id, products)
            logger.info(f"Product {product_id} deleted for creator {creator_id}")
            return True
        return False

    def search_products(
        self,
        creator_id: str,
        query: str,
        min_score: float = 0.2
    ) -> List[tuple]:
        """Buscar productos por query, devuelve lista de (producto, score)"""
        products = self.get_products(creator_id, active_only=True)
        results = []

        for product in products:
            score = product.matches_query(query)
            if score >= min_score:
                results.append((product, score))

        # Ordenar por score descendente
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def recommend_product(
        self,
        creator_id: str,
        user_context: dict,
        query: str = ""
    ) -> Optional[Product]:
        """Recomendar el mejor producto basado en contexto"""
        products = self.get_products(creator_id, active_only=True)
        if not products:
            return None

        # Si hay query, buscar por coincidencia
        if query:
            results = self.search_products(creator_id, query)
            if results:
                return results[0][0]

        # Buscar por intereses del usuario
        user_interests = user_context.get("interests", [])
        if user_interests:
            for product in products:
                for interest in user_interests:
                    if (interest.lower() in product.keywords or
                        interest.lower() in product.category.lower() or
                        interest.lower() in product.name.lower()):
                        return product

        # Devolver producto destacado o el primero
        featured = [p for p in products if p.is_featured]
        if featured:
            return featured[0]

        return products[0]

    def get_objection_response(
        self,
        creator_id: str,
        product_id: str,
        objection_type: str
    ) -> str:
        """Obtener respuesta a objeción específica"""
        product = self.get_product_by_id(creator_id, product_id)
        if not product:
            return ""

        objection_type = objection_type.lower()

        # Mapeo de variaciones a tipo de objeción
        objection_map = {
            "caro": "precio",
            "costoso": "precio",
            "dinero": "precio",
            "no puedo pagar": "precio",
            "muy caro": "precio",
            "sin tiempo": "tiempo",
            "ocupado": "tiempo",
            "no tengo tiempo": "tiempo",
            "luego": "despues",
            "después": "despues",
            "más tarde": "despues",
            "otro momento": "despues",
            "lo voy a pensar": "pensarlo",
            "déjame pensarlo": "pensarlo",
            "lo pienso": "pensarlo",
            "no sé si funciona": "funciona",
            "funciona": "funciona",
            "resultados": "funciona",
            "sirve": "funciona",
            "no sé": "no_se",
            "no estoy seguro": "no_se",
            "complicado": "complicado",
            "difícil": "complicado",
            "ya tengo": "ya_tengo",
            "ya sé": "ya_tengo"
        }

        # Normalizar tipo de objeción
        normalized = objection_type
        for key, value in objection_map.items():
            if key in objection_type:
                normalized = value
                break

        # Obtener template de respuesta
        response_template = product.objection_handlers.get(
            normalized,
            self.DEFAULT_OBJECTION_HANDLERS.get(
                normalized,
                "Entiendo tu preocupación. ¿Hay algo específico que te gustaría saber sobre {product_name}?"
            )
        )

        # Seleccionar testimonial si hay
        testimonial = product.testimonials[0] if product.testimonials else "más del 90% de mis alumnos ven resultados en las primeras semanas"

        # Formatear respuesta
        response = response_template.format(
            product_name=product.name,
            features_count=len(product.features),
            main_benefit=product.features[0] if product.features else "lograr tus objetivos",
            roi_time="un mes",
            payment_link=product.payment_link,
            testimonial=testimonial,
            guarantee_days=7,
            advanced_feature=product.features[-1] if product.features else "técnicas avanzadas"
        )

        return response

    def get_product_info_text(self, product: Product, detailed: bool = False) -> str:
        """Generar texto informativo del producto para el clon"""
        features_text = ""
        if product.features:
            features_text = "\n".join([f"✅ {f}" for f in product.features])

        price_text = f"{product.price} {product.currency}"
        if product.price == 0:
            price_text = "Gratis"

        basic_info = f"""**{product.name}**
{product.description}

💰 Precio: {price_text}
🔗 Link: {product.payment_link}"""

        if not detailed:
            return basic_info

        detailed_info = basic_info
        if features_text:
            detailed_info += f"\n\n📦 Incluye:\n{features_text}"

        if product.testimonials:
            detailed_info += f"\n\n💬 Lo que dicen:\n\"{product.testimonials[0]}\""

        return detailed_info

    def get_products_summary(self, creator_id: str) -> str:
        """Obtener resumen de todos los productos para contexto del clon"""
        products = self.get_products(creator_id, active_only=True)
        if not products:
            return "No tengo productos disponibles actualmente."

        summary_parts = ["Mis productos/servicios disponibles:"]
        for p in products:
            price_text = f"{p.price} {p.currency}" if p.price > 0 else "Gratis"
            summary_parts.append(f"- **{p.name}** ({price_text}): {p.get_short_description(80)}")

        return "\n".join(summary_parts)


class SalesTracker:
    """Tracker de ventas y conversiones"""

    def __init__(self, storage_path: str = "data/sales"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)

    def _get_file(self, creator_id: str) -> str:
        return os.path.join(self.storage_path, f"{creator_id}_sales.json")

    def _load_sales(self, creator_id: str) -> List[dict]:
        filepath = self._get_file(creator_id)
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []

    def _save_sales(self, creator_id: str, sales: List[dict]):
        filepath = self._get_file(creator_id)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(sales, f, indent=2, ensure_ascii=False)

    def record_click(
        self,
        creator_id: str,
        product_id: str,
        follower_id: str
    ):
        """Registrar clic en link de producto"""
        sales = self._load_sales(creator_id)
        sales.append({
            "type": "click",
            "product_id": product_id,
            "follower_id": follower_id,
            "timestamp": datetime.now().isoformat()
        })
        self._save_sales(creator_id, sales)

    def record_sale(
        self,
        creator_id: str,
        product_id: str,
        follower_id: str,
        amount: float,
        currency: str = "EUR"
    ):
        """Registrar venta completada"""
        sales = self._load_sales(creator_id)
        sales.append({
            "type": "sale",
            "product_id": product_id,
            "follower_id": follower_id,
            "amount": amount,
            "currency": currency,
            "timestamp": datetime.now().isoformat()
        })
        self._save_sales(creator_id, sales)

    def get_stats(self, creator_id: str) -> dict:
        """Obtener estadísticas de ventas"""
        sales = self._load_sales(creator_id)

        clicks = [s for s in sales if s.get("type") == "click"]
        completed_sales = [s for s in sales if s.get("type") == "sale"]

        total_revenue = sum(s.get("amount", 0) for s in completed_sales)

        return {
            "total_clicks": len(clicks),
            "total_sales": len(completed_sales),
            "total_revenue": total_revenue,
            "conversion_rate": len(completed_sales) / len(clicks) if clicks else 0
        }
