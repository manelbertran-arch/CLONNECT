"""
Product Detector V2 - Signal-Based Detection

Un producto SOLO existe si tiene AL MENOS 3 de estas señales:
1. Página dedicada (/servicio/X, /producto/X)
2. CTA de compra ("comprar", "reservar", "apúntate")
3. Precio visible (€X)
4. Descripción > 50 palabras
5. Link de pago (stripe, calendly, paypal)
6. Aparece en nav como servicio

Si < 3 señales → NO ES PRODUCTO → IGNORAR
Si > 20 productos → ABORTAR (algo está mal)
"""

import re
import logging
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ProductSignal(Enum):
    """Señales que indican que algo es un producto real."""
    DEDICATED_PAGE = "dedicated_page"
    CTA_PRESENT = "cta_present"
    PRICE_VISIBLE = "price_visible"
    SUBSTANTIAL_DESCRIPTION = "substantial_description"
    PAYMENT_LINK = "payment_link"
    CLEAR_TITLE = "clear_title"


@dataclass
class DetectedProduct:
    """Producto detectado con todas sus pruebas."""
    name: str
    description: str
    price: Optional[float]  # NULL si no encontrado, NUNCA inventado
    currency: str = "EUR"
    source_url: str = ""
    source_html: str = ""  # Prueba del origen
    price_source_text: Optional[str] = None  # Texto literal donde se encontró el precio
    signals_matched: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "currency": self.currency,
            "source_url": self.source_url,
            "price_source_text": self.price_source_text,
            "signals_matched": self.signals_matched,
            "confidence": self.confidence,
        }


class SuspiciousExtractionError(Exception):
    """Se lanza cuando la extracción parece sospechosa."""
    pass


class ProductDetector:
    """
    Detecta productos REALES con múltiples señales.
    Conservador: mejor perder un producto que inventar uno.
    """

    REQUIRED_SIGNALS = 3  # Mínimo para considerar algo un producto
    MAX_PRODUCTS = 20  # Si hay más, algo está mal

    # Indicadores de página de servicio en URL
    SERVICE_URL_PATTERNS = [
        r'/servicio', r'/service', r'/producto', r'/product',
        r'/curso', r'/course', r'/programa', r'/program',
        r'/coaching', r'/taller', r'/workshop', r'/sesion',
        r'/challenge', r'/pack', r'/pricing', r'/precio',
        r'/mentoria', r'/consultoria', r'/formacion',
        r'/del.*plenitud', r'/respira.*conecta', r'/fitpack',
    ]

    # Patrones de CTA de compra
    CTA_PATTERNS = [
        r'\b(comprar|compra)\b', r'\b(reservar|reserva)\b',
        r'\b(contratar|contrata)\b', r'\bapúntate\b', r'\binscríbete\b',
        r'\bquiero\s+(empezar|saber|acceder)\b', r'\bacceder\b',
        r'\búnete\b', r'\bempezar\b', r'\bcomenzar\b',
        r'\bbuy\b', r'\bbook\b', r'\bjoin\b', r'\bstart\b',
        r'\bacepto\s+el\s+desafío\b', r'\bquiero\s+saber\s+más\b',
    ]

    # Dominios de pago/booking
    PAYMENT_DOMAINS = [
        'stripe', 'paypal', 'calendly', 'gumroad', 'hotmart',
        'thinkific', 'teachable', 'kajabi', 'podia', 'payhip',
        'ko-fi', 'buymeacoffee', 'typeform', 'cal.com',
    ]

    # Patrones de precio
    PRICE_PATTERNS = [
        (r'€\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)', 'EUR'),
        (r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*€', 'EUR'),
        (r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*EUR\b', 'EUR'),
        (r'\$\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)', 'USD'),
        (r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*\$', 'USD'),
    ]

    # Páginas a excluir (no son productos)
    EXCLUDE_URL_PATTERNS = [
        r'/blog', r'/post', r'/articulo', r'/article',
        r'/contacto', r'/contact', r'/about', r'/sobremi',
        r'/testimonio', r'/review', r'/legal', r'/privacy',
        r'/terminos', r'/terms', r'/faq', r'/ayuda',
    ]

    # ============================================================
    # FILTRO ANTI-TESTIMONIOS
    # Un testimonio NO es un producto, aunque aparezca en página de servicios
    # ============================================================

    # Patrones que indican que es un TESTIMONIO, no un producto
    TESTIMONIAL_PATTERNS = [
        # Frases típicas de testimonios
        r'\bme ayud[óo]\b', r'\bgracias a\b', r'\brecomiendo\b',
        r'\bcambi[óo] mi vida\b', r'\btransform[óo]\b',
        r'\bincreíble experiencia\b', r'\bmejor decisión\b',
        r'\bno puedo agradecer\b', r'\bestoy muy content[oa]\b',
        r'\bsuperó mis expectativas\b', r'\b100% recomendable\b',
        r'\bsi estás dudando\b', r'\bno lo dudes\b',
        r'\bme siento\b.*\b(mejor|genial|increíble)\b',
        r'\bél me enseñó\b', r'\bella me enseñó\b',
        r'\baprendí\b.*\bcon (él|ella|stefano)\b',
        # Atribución de testimonios
        r'^"[^"]{10,200}"$',  # Texto solo entre comillas
        r'^\s*—\s*\w+',  # Atribución tipo "— María"
        r'\b(cliente|alumno|participante)\s+de\b',
    ]

    # Palabras en el TÍTULO que indican testimonio
    TESTIMONIAL_TITLE_PATTERNS = [
        r'^".*"$',  # Título entre comillas
        r'^'.*'$',  # Título entre comillas simples
        r'testimonio', r'opinión', r'review', r'reseña',
        r'lo que dicen', r'experiencias', r'casos de éxito',
    ]

    def detect_products(self, pages: List['ScrapedPage']) -> List[DetectedProduct]:
        """
        Detecta productos reales usando sistema de señales.

        Args:
            pages: Páginas scrapeadas

        Returns:
            Lista de productos detectados (solo los verificados)

        Raises:
            SuspiciousExtractionError: Si se detectan > MAX_PRODUCTS
        """
        from ..deterministic_scraper import ScrapedPage

        # 1. Identificar páginas de servicio
        service_pages = self._identify_service_pages(pages)
        logger.info(f"Páginas de servicio identificadas: {len(service_pages)}")

        # 2. Analizar cada página buscando señales
        candidates = []
        for page in service_pages:
            product = self._analyze_page(page)
            if product and len(product.signals_matched) >= self.REQUIRED_SIGNALS:
                candidates.append(product)
                logger.info(
                    f"Producto detectado: {product.name} "
                    f"({len(product.signals_matched)} señales: {product.signals_matched})"
                )

        # 3. SANITY CHECK: Si hay demasiados, abortar
        if len(candidates) > self.MAX_PRODUCTS:
            raise SuspiciousExtractionError(
                f"Se detectaron {len(candidates)} productos. "
                f"Máximo esperado: {self.MAX_PRODUCTS}. "
                "Esto indica un error en la detección. Abortando."
            )

        logger.info(f"Total productos verificados: {len(candidates)}")
        return candidates

    def _identify_service_pages(self, pages: List['ScrapedPage']) -> List['ScrapedPage']:
        """Identifica páginas que parecen ser de servicios/productos."""
        service_pages = []

        for page in pages:
            url_lower = page.url.lower()

            # Excluir páginas que claramente no son productos
            if any(re.search(p, url_lower) for p in self.EXCLUDE_URL_PATTERNS):
                continue

            # Incluir si URL contiene indicador de servicio
            is_service = any(re.search(p, url_lower) for p in self.SERVICE_URL_PATTERNS)

            # También incluir homepage (puede tener servicios)
            is_homepage = url_lower.rstrip('/').endswith('.com') or url_lower.count('/') <= 3

            if is_service or is_homepage:
                service_pages.append(page)

        return service_pages

    def _analyze_page(self, page: 'ScrapedPage') -> Optional[DetectedProduct]:
        """Analiza una página buscando señales de producto."""
        signals = []
        content = page.main_content.lower()
        url_lower = page.url.lower()

        # Señal 1: DEDICATED_PAGE
        if any(re.search(p, url_lower) for p in self.SERVICE_URL_PATTERNS):
            signals.append(ProductSignal.DEDICATED_PAGE.value)

        # Señal 2: CTA_PRESENT
        if any(re.search(p, content, re.IGNORECASE) for p in self.CTA_PATTERNS):
            signals.append(ProductSignal.CTA_PRESENT.value)

        # Señal 3: PRICE_VISIBLE
        price, currency, price_text = self._extract_price(page.main_content)
        if price is not None:
            signals.append(ProductSignal.PRICE_VISIBLE.value)

        # Señal 4: SUBSTANTIAL_DESCRIPTION
        # Contar palabras en contenido principal (excluyendo menú, footer)
        word_count = len(content.split())
        if word_count > 100:  # Más estricto: 100 palabras
            signals.append(ProductSignal.SUBSTANTIAL_DESCRIPTION.value)

        # Señal 5: PAYMENT_LINK
        if self._has_payment_link(page):
            signals.append(ProductSignal.PAYMENT_LINK.value)

        # Señal 6: CLEAR_TITLE
        title = self._extract_title(page)
        if title and 5 < len(title) < 100:
            signals.append(ProductSignal.CLEAR_TITLE.value)

        # Si no hay suficientes señales, no es producto
        if len(signals) < self.REQUIRED_SIGNALS:
            return None

        # Extraer nombre del producto
        name = title or self._extract_name_from_url(page.url)
        if not name:
            return None

        # Extraer descripción (primeros 500 chars significativos)
        description = self._extract_description(page)

        # ============================================================
        # FILTRO ANTI-TESTIMONIOS: Verificar que NO sea un testimonio
        # ============================================================
        if self._is_testimonial(name, description):
            logger.info(f"DESCARTADO (testimonio detectado): {name}")
            return None

        # Calcular confianza
        confidence = len(signals) / len(ProductSignal)

        # Extraer HTML relevante como prueba
        source_html = self._extract_relevant_html(page)

        return DetectedProduct(
            name=name,
            description=description,
            price=price,
            currency=currency or "EUR",
            source_url=page.url,
            source_html=source_html,
            price_source_text=price_text,
            signals_matched=signals,
            confidence=confidence
        )

    def _extract_price(self, text: str) -> tuple[Optional[float], Optional[str], Optional[str]]:
        """
        Extrae precio del texto usando regex.

        Returns:
            (precio, moneda, texto_literal) o (None, None, None)
        """
        for pattern, currency in self.PRICE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price_str = match.group(1)
                # Normalizar precio
                clean = price_str.replace('.', '').replace(',', '.')
                try:
                    price = float(clean)
                    if 0 < price < 50000:  # Rango razonable
                        # Obtener contexto
                        start = max(0, match.start() - 30)
                        end = min(len(text), match.end() + 30)
                        context = text[start:end].strip()
                        return price, currency, context
                except ValueError:
                    continue

        return None, None, None

    def _has_payment_link(self, page: 'ScrapedPage') -> bool:
        """Verifica si la página tiene links de pago/booking."""
        content = page.main_content.lower()
        for domain in self.PAYMENT_DOMAINS:
            if domain in content:
                return True
        return False

    def _extract_title(self, page: 'ScrapedPage') -> Optional[str]:
        """Extrae título limpio de la página."""
        title = page.title
        if not title:
            return None

        # Limpiar título (quitar " — Sitio Web", " | Brand", etc.)
        title = re.split(r'\s*[—|–|-]\s*', title)[0].strip()

        # Quitar comillas
        title = title.strip('"\'')

        return title if title else None

    def _extract_name_from_url(self, url: str) -> Optional[str]:
        """Extrae nombre del producto de la URL."""
        # Obtener último segmento
        path = url.rstrip('/').split('/')[-1]
        if not path or path == 'www.stefanobonanno.com':
            return None

        # Convertir slug a nombre
        name = path.replace('-', ' ').replace('_', ' ').title()
        return name

    def _extract_description(self, page: 'ScrapedPage') -> str:
        """Extrae descripción significativa de la página."""
        content = page.main_content

        # Buscar primer párrafo largo
        sentences = re.split(r'[.!?]\s+', content)
        description_parts = []
        char_count = 0

        for sentence in sentences:
            if len(sentence) > 20:  # Oraciones significativas
                description_parts.append(sentence)
                char_count += len(sentence)
                if char_count > 300:
                    break

        return '. '.join(description_parts)[:500]

    def _extract_relevant_html(self, page: 'ScrapedPage') -> str:
        """Extrae HTML relevante como prueba del origen."""
        # Por ahora, guardar primeros 2000 chars del contenido
        return page.main_content[:2000]

    def _is_testimonial(self, title: str, description: str) -> bool:
        """
        Detecta si el contenido parece ser un TESTIMONIO, no un producto.

        Un testimonio tiene:
        - Título entre comillas
        - Frases tipo "me ayudó", "gracias a", "recomiendo"
        - Texto en primera persona sobre experiencia

        Returns:
            True si parece testimonio (NO guardar como producto)
        """
        title_lower = (title or "").lower().strip()
        desc_lower = (description or "").lower()

        # 1. Verificar título
        for pattern in self.TESTIMONIAL_TITLE_PATTERNS:
            if re.search(pattern, title_lower, re.IGNORECASE):
                logger.info(f"Filtrado como testimonio (título): {title}")
                return True

        # 2. Verificar descripción
        testimonial_matches = 0
        for pattern in self.TESTIMONIAL_PATTERNS:
            if re.search(pattern, desc_lower, re.IGNORECASE):
                testimonial_matches += 1

        # Si hay 2+ patrones de testimonio, es testimonio
        if testimonial_matches >= 2:
            logger.info(f"Filtrado como testimonio ({testimonial_matches} patrones): {title}")
            return True

        # 3. Título que empieza y termina con comillas = testimonio
        if title_lower.startswith('"') and title_lower.endswith('"'):
            logger.info(f"Filtrado como testimonio (comillas en título): {title}")
            return True

        if title_lower.startswith("'") and title_lower.endswith("'"):
            logger.info(f"Filtrado como testimonio (comillas simples): {title}")
            return True

        # 4. Título muy corto con comillas parciales
        if len(title_lower) < 50 and ('"' in title_lower or '"' in title_lower or '"' in title_lower):
            # Verificar si el contenido es testimonial
            if testimonial_matches >= 1:
                logger.info(f"Filtrado como testimonio (comillas + patrón): {title}")
                return True

        return False


def get_product_detector() -> ProductDetector:
    """Get detector instance."""
    return ProductDetector()
