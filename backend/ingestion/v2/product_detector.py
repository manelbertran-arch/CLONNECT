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
import time
import logging
from typing import List, Optional

from core.metrics import record_products_detected, observe_extract_duration, record_ingestion_error

from .product_taxonomy import (
    ProductSignal,
    DetectedProduct,
    SuspiciousExtractionError,
    clasificar_contenido,
    detectar_moneda,
    extraer_descripcion_corta,
    extraer_payment_link,
)

# Re-export so external code that does `from ingestion.v2.product_detector import X` still works
__all__ = [
    'ProductSignal',
    'DetectedProduct',
    'SuspiciousExtractionError',
    'ProductDetector',
    'get_product_detector',
]

logger = logging.getLogger(__name__)


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
        # NUEVOS: Excluir recursos que no son productos
        r'/podcast', r'/recursos', r'/resource', r'/free',
        r'/spotify', r'/apple.*podcast', r'/youtube',
    ]

    # Palabras en título/nombre que indican que NO es un producto
    NOT_PRODUCT_TITLE_PATTERNS = [
        r'\bpodcast\b', r'\bspotify\b', r'\byoutube\b',
        r'\bblog\b', r'\bartículo\b', r'\barticle\b',
        r'\bfree\b', r'\bgratis\b', r'\brecurso\b',
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
        r'\baprendí\b.*\bcon (él|ella|[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)\b',
        # Atribución de testimonios
        r'^"[^"]{10,200}"$',  # Texto solo entre comillas
        r'^\s*—\s*\w+',  # Atribución tipo "— María"
        r'\b(cliente|alumno|participante)\s+de\b',
        # NUEVOS: Más patrones de testimonios
        r'\bdesbloque[óo]\b', r'\bdesbloquear\b',  # "me ayudó a desbloquear"
        r'\bexcelente profesional\b', r'\bmuy profesional\b',
        r'\bsin duda\b', r'\bel mejor\b', r'\bla mejor\b',
        r'\bme ha ayudado\b', r'\bme enseñ[óo]\b',
        r'\bcreencias limitantes\b', r'\bbloqueos\b',
        r'\bproceso de\b.*(coaching|transformación|cambio)\b',
        r'\bsesiones? con\b', r'\btrabaj[éo] con\b',
    ]

    # Palabras en el TÍTULO que indican testimonio
    TESTIMONIAL_TITLE_PATTERNS = [
        r'^".*"$',  # Título entre comillas rectas
        r"^'.*'$",  # Título entre comillas simples rectas
        r'^[\u2018\u201C].*[\u2019\u201D]$',  # Comillas curvas (tipográficas)
        r'^«.*»$',  # Comillas españolas/francesas
        r'^„.*"$',  # Comillas alemanas
        r'testimonio', r'opinión', r'review', r'reseña',
        r'lo que dicen', r'experiencias', r'casos de éxito',
        # NUEVOS: Más patrones de título de testimonio
        r'profesionalismo', r'cercanía', r'confianza',
        r'transformación', r'cambio de vida',
    ]

    def detect_products(self, pages: List['ScrapedPage'], creator_id: str = "unknown") -> List[DetectedProduct]:
        """
        Detecta productos reales usando sistema de señales.

        Args:
            pages: Páginas scrapeadas
            creator_id: Creator ID for metrics tracking

        Returns:
            Lista de productos detectados (solo los verificados)

        Raises:
            SuspiciousExtractionError: Si se detectan > MAX_PRODUCTS
        """
        start_time = time.time()

        # 1. Identificar páginas de servicio
        service_pages = self._identify_service_pages(pages)
        logger.info(f"Páginas de servicio identificadas: {len(service_pages)}")

        # 2. Analizar cada página buscando señales
        candidates = []
        for page in service_pages:
            product = self._analyze_page(page)
            if product and len(product.signals_matched) >= self.REQUIRED_SIGNALS:
                # Filtrar títulos que NO son productos (podcast, blog, etc.)
                if self._is_not_product_title(product.name):
                    logger.info(f"DESCARTADO (título no es producto): {product.name}")
                    continue

                candidates.append(product)
                logger.info(
                    f"Producto detectado: {product.name} "
                    f"({len(product.signals_matched)} señales: {product.signals_matched})"
                )

        # 3. ELIMINAR DUPLICADOS: Mantener solo uno por nombre
        candidates = self._remove_duplicates(candidates)

        # 4. SANITY CHECK: Si hay demasiados, abortar
        if len(candidates) > self.MAX_PRODUCTS:
            record_ingestion_error("too_many_products")
            raise SuspiciousExtractionError(
                f"Se detectaron {len(candidates)} productos. "
                f"Máximo esperado: {self.MAX_PRODUCTS}. "
                "Esto indica un error en la detección. Abortando."
            )

        # Record metrics
        duration = time.time() - start_time
        observe_extract_duration("products", duration)
        record_products_detected(creator_id, len(candidates))

        logger.info(f"Total productos verificados: {len(candidates)}")
        return candidates

    def _is_not_product_title(self, title: str) -> bool:
        """Detecta si el título indica que NO es un producto."""
        title_lower = (title or "").lower()
        for pattern in self.NOT_PRODUCT_TITLE_PATTERNS:
            if re.search(pattern, title_lower, re.IGNORECASE):
                return True
        return False

    def _remove_duplicates(self, products: List[DetectedProduct]) -> List[DetectedProduct]:
        """
        Elimina productos duplicados por nombre.
        Mantiene el que tiene más señales o precio.
        """
        seen_names = {}
        unique = []

        for product in products:
            # Normalizar nombre para comparación
            name_key = product.name.lower().strip()

            if name_key in seen_names:
                # Ya existe - comparar cuál es mejor
                existing = seen_names[name_key]
                # Preferir el que tiene precio
                if product.price is not None and existing.price is None:
                    seen_names[name_key] = product
                    logger.info(f"DUPLICADO reemplazado (tiene precio): {product.name}")
                # O el que tiene más señales
                elif len(product.signals_matched) > len(existing.signals_matched):
                    seen_names[name_key] = product
                    logger.info(f"DUPLICADO reemplazado (más señales): {product.name}")
                else:
                    logger.info(f"DUPLICADO descartado: {product.name}")
            else:
                seen_names[name_key] = product

        unique = list(seen_names.values())
        if len(unique) < len(products):
            logger.info(f"Eliminados {len(products) - len(unique)} duplicados")

        return unique

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

    # Patrones para detectar productos EXPLÍCITAMENTE gratuitos
    # Solo detectar si hay indicación clara de que ES gratis (no solo mencionan algo gratis)
    FREE_PATTERNS = [
        r'\b(gratis|gratuito|gratuita|free)\b.*\b(apunta|inscrib|regist|reserv)',  # "gratis - apúntate"
        r'\b(apunta|inscrib|regist|reserv).*\b(gratis|gratuito|gratuita|free)\b',  # "apúntate gratis"
        r'€\s*0\b|\b0\s*€',  # Precio explícito €0
        r'\bprecio[:\s]+gratis\b',  # "precio: gratis"
        r'\bsin\s+(coste|costo)\s*$',  # "sin coste" al final
    ]

    # Patrones en URL que indican producto gratuito
    FREE_URL_PATTERNS = [
        r'/gratis', r'/free', r'/gratuito',
        r'/discovery', r'/descubrimiento',
    ]

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

        # Señal 3: PRICE_VISIBLE - Extraer precio explícito
        price, currency, price_text = self._extract_price(page.main_content)
        if price is not None:
            signals.append(ProductSignal.PRICE_VISIBLE.value)

        # Señal 3b: FREE_PRODUCT - Detectar si es EXPLÍCITAMENTE gratuito
        # Debe tener indicación clara en contenido O en URL
        is_free_url = any(re.search(p, url_lower, re.IGNORECASE) for p in self.FREE_URL_PATTERNS)
        is_free_content = any(re.search(p, content, re.IGNORECASE) for p in self.FREE_PATTERNS)
        is_free = is_free_url or is_free_content

        if is_free and price is None:
            price = 0.0
            price_text = "gratuito"
            signals.append(ProductSignal.PRICE_VISIBLE.value)
            logger.info(f"Detectado producto gratuito: {page.url}")

        # ============================================================
        # REGLA PRINCIPAL: Solo es PRODUCTO si tiene precio O es gratuito
        # Todo lo demás va al RAG como contenido informativo
        # ============================================================
        has_price_or_free = price is not None
        if not has_price_or_free:
            logger.info(f"DESCARTADO (sin precio): {page.url}")
            return None

        # Señal 4: SUBSTANTIAL_DESCRIPTION
        word_count = len(content.split())
        if word_count > 100:
            signals.append(ProductSignal.SUBSTANTIAL_DESCRIPTION.value)

        # Señal 5: PAYMENT_LINK
        if self._has_payment_link(page):
            signals.append(ProductSignal.PAYMENT_LINK.value)

        # Señal 6: CLEAR_TITLE
        title = self._extract_title(page)
        if title and 5 < len(title) < 100:
            signals.append(ProductSignal.CLEAR_TITLE.value)

        # Ya no requerimos mínimo de señales - el precio/gratuito es suficiente
        # Pero mantenemos las señales para calcular confianza

        # Extraer nombre del producto
        name = title or self._extract_name_from_url(page.url)
        if not name:
            return None

        # Extraer descripción (primeros 500 chars significativos)
        description = self._extract_description(page)

        # ============================================================
        # FILTRO ANTI-TESTIMONIOS: Verificar que NO sea un testimonio
        # ============================================================
        if self._is_testimonial(name, description, has_price=True):
            logger.info(f"DESCARTADO (testimonio detectado): {name}")
            return None

        # Calcular confianza (basada en señales)
        confidence = max(0.5, len(signals) / len(ProductSignal))

        # Extraer HTML relevante como prueba
        source_html = self._extract_relevant_html(page)

        # =================================================================
        # NUEVA TAXONOMÍA: Clasificar como product, service o resource
        # =================================================================
        tiene_precio = price is not None and price > 0
        clasificacion = clasificar_contenido(name, description, page.url, tiene_precio, is_free)

        if clasificacion is None:
            logger.info(f"DESCARTADO (no clasificable): {name}")
            return None

        category = clasificacion['category']
        detected_type = clasificacion['type']
        item_is_free = clasificacion['is_free']

        # Detectar moneda y campos adicionales
        detected_currency = detectar_moneda(page.main_content, price_text or "") if not currency else currency
        short_desc = extraer_descripcion_corta(description, max_chars=150)
        payment_url = extraer_payment_link(page.url, page.main_content)

        logger.info(f"Detectado [{category.upper()}] '{name}': tipo={detected_type}, precio={price}, gratis={item_is_free}")

        return DetectedProduct(
            name=name,
            description=description,
            price=price,
            currency=detected_currency or "EUR",
            source_url=page.url,
            source_html=source_html,
            price_source_text=price_text,
            signals_matched=signals,
            confidence=confidence,
            category=category,
            product_type=detected_type,
            is_free=item_is_free,
            short_description=short_desc,
            payment_link=payment_url
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
        if not path or '.' in path:  # Domain root (e.g. www.example.com) has no product path
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

    def _is_testimonial(self, title: str, description: str, has_price: bool = False) -> bool:
        """
        Detecta si el contenido parece ser un TESTIMONIO, no un producto.

        Un testimonio tiene:
        - Título entre comillas
        - Frases tipo "me ayudó", "gracias a", "recomiendo"
        - Texto en primera persona sobre experiencia
        - SIN precio visible

        Returns:
            True si parece testimonio (NO guardar como producto)
        """
        title_lower = (title or "").lower().strip()
        title_original = (title or "").strip()
        desc_lower = (description or "").lower()

        # 1. Verificar título - patrones regex
        for pattern in self.TESTIMONIAL_TITLE_PATTERNS:
            if re.search(pattern, title_lower, re.IGNORECASE):
                logger.info(f"Filtrado como testimonio (título pattern): {title}")
                return True

        # 2. Título que empieza con cualquier tipo de comilla
        quote_chars = ['"', "'", '\u201c', '\u201d', '\u00ab', '\u201e', '\u201c', '\u2018']
        for q in quote_chars:
            if title_original.startswith(q):
                logger.info(f"Filtrado como testimonio (empieza con comilla '{q}'): {title}")
                return True

        # 3. Verificar descripción - contar patrones
        testimonial_matches = 0
        matched_patterns = []
        for pattern in self.TESTIMONIAL_PATTERNS:
            if re.search(pattern, desc_lower, re.IGNORECASE):
                testimonial_matches += 1
                matched_patterns.append(pattern[:20])

        # Si hay 2+ patrones de testimonio = definitivamente testimonio
        if testimonial_matches >= 2:
            logger.info(f"Filtrado como testimonio ({testimonial_matches} patrones): {title}")
            return True

        # 4. Si hay 1+ patrones Y NO tiene precio = probablemente testimonio
        if testimonial_matches >= 1 and not has_price:
            logger.info(f"Filtrado como testimonio (1 patrón + sin precio): {title}")
            return True

        # 5. Título muy corto con comillas = testimonio (ej: "Profesionalismo y Cercanía")
        if len(title_lower) < 60:
            for q in quote_chars:
                if q in title_original:
                    if testimonial_matches >= 1 or not has_price:
                        logger.info(f"Filtrado como testimonio (título corto con comilla + señales): {title}")
                        return True

        return False


    async def detect_with_fallback(
        self, pages: List['ScrapedPage'], creator_id: str = "unknown"
    ) -> List[DetectedProduct]:
        """
        Detect products with LLM fallback when signal-based detection finds nothing.

        1. Run normal signal-based detection (>=3 signals)
        2. If 0 products found, use LLM to analyze page content
        3. LLM-detected products are marked source="llm_fallback", status="pending_confirmation"
        """
        # Step 1: Normal detection
        products = self.detect_products(pages, creator_id)
        if products:
            return products

        # Step 2: LLM fallback
        logger.info(f"[B9] No products via signals for {creator_id}, trying LLM fallback...")

        # Concatenate page text (max 5000 chars)
        page_texts = []
        total_chars = 0
        for page in pages:
            text = getattr(page, "text", "") or getattr(page, "content", "") or ""
            if text and len(text) > 50:
                page_texts.append(f"URL: {page.url}\n{text[:1000]}")
                total_chars += min(len(text), 1000)
                if total_chars > 5000:
                    break

        if not page_texts:
            logger.info("[B9] No page text available for LLM fallback")
            return []

        combined_text = "\n---\n".join(page_texts)

        try:
            import json
            import os

            import google.generativeai as genai

            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                logger.warning("[B9] No Gemini API key for LLM fallback")
                return []

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash-lite")

            prompt = (
                "Analiza este contenido web y extrae servicios/productos reales.\n"
                "Retorna SOLO un JSON array con objetos: "
                '{"name": "...", "type": "servicio|producto|recurso", '
                '"price": null, "url": "...", "description": "..."}\n'
                "Solo servicios REALES. NO inventes precios. Si no hay productos, retorna [].\n\n"
                f"Contenido:\n{combined_text[:4000]}"
            )

            response = model.generate_content(prompt)
            response_text = response.text.strip()

            # Extract JSON from response
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            llm_products = json.loads(response_text)
            if not isinstance(llm_products, list):
                return []

            results = []
            for p in llm_products[:5]:  # Max 5 from LLM
                product = DetectedProduct(
                    name=p.get("name", "Unknown"),
                    description=p.get("description", "")[:500],
                    price=p.get("price"),
                    source_url=p.get("url", ""),
                    signals_matched=["llm_fallback"],
                    confidence=0.5,
                    category="service" if p.get("type") == "servicio" else "product",
                    product_type=p.get("type", "otro"),
                    short_description=p.get("description", "")[:150],
                )
                results.append(product)

            logger.info(f"[B9] LLM fallback found {len(results)} products for {creator_id}")
            return results

        except Exception as e:
            logger.error(f"[B9] LLM fallback error: {e}")
            return []


def get_product_detector() -> ProductDetector:
    """Get detector instance."""
    return ProductDetector()
