"""
Sanity Checker V2 - Verifica que los resultados tienen sentido.

Si algo es sospechoso, RECHAZA todo.
Re-verifica cada producto fetching la URL original.
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from urllib.parse import urlparse
import httpx

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    """Resultado de una verificación."""
    name: str
    passed: bool
    message: str
    details: Optional[Dict] = None


@dataclass
class VerificationResult:
    """Resultado completo de todas las verificaciones."""
    passed: bool
    status: str  # 'success', 'failed', 'needs_review'
    checks: List[CheckResult] = field(default_factory=list)
    products_verified: int = 0
    products_rejected: int = 0
    rejection_reasons: List[str] = field(default_factory=list)


class SanityChecker:
    """
    Verifica que los resultados de extracción son válidos.
    Si algo es sospechoso, RECHAZA.
    """

    MAX_PRODUCTS = 20
    MIN_CONFIDENCE = 0.5  # Mínimo 50% de señales
    PRICE_MIN = 0  # Permitir productos gratuitos (price=0)
    PRICE_MAX = 50000

    def verify(
        self,
        products: List['DetectedProduct'],
        website_url: str,
        re_verify_urls: bool = True
    ) -> VerificationResult:
        """
        Verifica lista de productos detectados.

        Args:
            products: Productos a verificar
            website_url: URL base del sitio
            re_verify_urls: Si hacer fetch de URLs para re-verificar

        Returns:
            VerificationResult con estado y detalles
        """

        checks = []
        _verified_products = []
        rejected_products = []

        # Check 1: Número razonable de productos
        check1 = self._check_product_count(products)
        checks.append(check1)
        if not check1.passed:
            return VerificationResult(
                passed=False,
                status='failed',
                checks=checks,
                rejection_reasons=[check1.message]
            )

        # Check 2: Todos tienen source_url
        check2, products = self._check_source_urls(products)
        checks.append(check2)

        # Check 3: URLs son del mismo dominio
        check3, products = self._check_same_domain(products, website_url)
        checks.append(check3)

        # Check 4: Precios razonables
        check4, products = self._check_reasonable_prices(products)
        checks.append(check4)

        # Check 5: Confianza mínima
        check5, products = self._check_minimum_confidence(products)
        checks.append(check5)

        # Check 6: Re-verificación (opcional pero recomendado)
        if re_verify_urls and products:
            check6, products = self._re_verify_products(products)
            checks.append(check6)

        # Determinar estado final
        critical_checks = [c for c in checks if 'RECHAZADOS' in c.message or 'Abortando' in c.message]
        all_passed = all(c.passed for c in checks)
        has_critical_failure = len(critical_checks) > 0

        if has_critical_failure:
            status = 'failed'
        elif all_passed:
            status = 'success'
        else:
            status = 'needs_review'

        return VerificationResult(
            passed=all_passed and not has_critical_failure,
            status=status,
            checks=checks,
            products_verified=len(products),
            products_rejected=len(rejected_products),
            rejection_reasons=[c.message for c in checks if not c.passed]
        )

    def _check_product_count(self, products: List['DetectedProduct']) -> CheckResult:
        """Verifica número razonable de productos."""
        count = len(products)

        if count > self.MAX_PRODUCTS:
            return CheckResult(
                name='product_count',
                passed=False,
                message=f"Demasiados productos: {count}. Máximo: {self.MAX_PRODUCTS}. Abortando.",
                details={'count': count, 'max': self.MAX_PRODUCTS}
            )
        elif count == 0:
            return CheckResult(
                name='product_count',
                passed=True,
                message="No se encontraron productos (puede ser correcto si el sitio no tiene precios públicos)",
                details={'count': 0}
            )
        else:
            return CheckResult(
                name='product_count',
                passed=True,
                message=f"Número de productos razonable: {count}",
                details={'count': count}
            )

    def _check_source_urls(
        self,
        products: List['DetectedProduct']
    ) -> tuple[CheckResult, List['DetectedProduct']]:
        """Verifica que todos tienen source_url."""
        products_without_source = [p for p in products if not p.source_url]

        if products_without_source:
            # Filtrar productos sin source
            valid_products = [p for p in products if p.source_url]
            return (
                CheckResult(
                    name='source_urls',
                    passed=False,
                    message=f"{len(products_without_source)} productos sin source_url. RECHAZADOS.",
                    details={'rejected': [p.name for p in products_without_source]}
                ),
                valid_products
            )
        else:
            return (
                CheckResult(
                    name='source_urls',
                    passed=True,
                    message="Todos los productos tienen source_url",
                    details={}
                ),
                products
            )

    def _check_same_domain(
        self,
        products: List['DetectedProduct'],
        website_url: str
    ) -> tuple[CheckResult, List['DetectedProduct']]:
        """Verifica que URLs son del mismo dominio."""
        base_domain = urlparse(website_url).netloc.replace('www.', '')

        foreign_products = []
        valid_products = []

        for p in products:
            product_domain = urlparse(p.source_url).netloc.replace('www.', '')
            if product_domain != base_domain:
                foreign_products.append(p)
            else:
                valid_products.append(p)

        if foreign_products:
            return (
                CheckResult(
                    name='same_domain',
                    passed=False,
                    message=f"{len(foreign_products)} productos de dominio diferente. RECHAZADOS.",
                    details={'rejected': [p.source_url for p in foreign_products]}
                ),
                valid_products
            )
        else:
            return (
                CheckResult(
                    name='same_domain',
                    passed=True,
                    message="Todas las URLs son del mismo dominio",
                    details={}
                ),
                products
            )

    def _check_reasonable_prices(
        self,
        products: List['DetectedProduct']
    ) -> tuple[CheckResult, List['DetectedProduct']]:
        """Verifica que precios son razonables."""
        suspicious = []
        valid_products = []

        for p in products:
            if p.price is not None:
                if p.price < self.PRICE_MIN or p.price > self.PRICE_MAX:
                    suspicious.append(p)
                    continue
            valid_products.append(p)

        if suspicious:
            return (
                CheckResult(
                    name='reasonable_prices',
                    passed=False,
                    message=f"{len(suspicious)} precios sospechosos (<€{self.PRICE_MIN} o >€{self.PRICE_MAX}). RECHAZADOS.",
                    details={'rejected': [(p.name, p.price) for p in suspicious]}
                ),
                valid_products
            )
        else:
            return (
                CheckResult(
                    name='reasonable_prices',
                    passed=True,
                    message="Todos los precios son razonables (o NULL)",
                    details={}
                ),
                products
            )

    def _check_minimum_confidence(
        self,
        products: List['DetectedProduct']
    ) -> tuple[CheckResult, List['DetectedProduct']]:
        """Verifica confianza mínima."""
        low_confidence = []
        valid_products = []

        for p in products:
            if p.confidence < self.MIN_CONFIDENCE:
                low_confidence.append(p)
            else:
                valid_products.append(p)

        if low_confidence:
            return (
                CheckResult(
                    name='minimum_confidence',
                    passed=False,
                    message=f"{len(low_confidence)} productos con confianza < {self.MIN_CONFIDENCE}. RECHAZADOS.",
                    details={'rejected': [(p.name, p.confidence) for p in low_confidence]}
                ),
                valid_products
            )
        else:
            return (
                CheckResult(
                    name='minimum_confidence',
                    passed=True,
                    message=f"Todos los productos tienen confianza >= {self.MIN_CONFIDENCE}",
                    details={}
                ),
                products
            )

    def _re_verify_products(
        self,
        products: List['DetectedProduct']
    ) -> tuple[CheckResult, List['DetectedProduct']]:
        """Re-verifica productos fetching las URLs."""
        verified = []
        failed = []

        for product in products:
            is_verified = self._verify_product_at_url(product)
            if is_verified:
                verified.append(product)
            else:
                failed.append(product)

        if failed:
            return (
                CheckResult(
                    name='re_verification',
                    passed=False,
                    message=f"{len(failed)} productos no se pudieron verificar en su URL.",
                    details={'failed': [p.name for p in failed]}
                ),
                verified
            )
        else:
            return (
                CheckResult(
                    name='re_verification',
                    passed=True,
                    message=f"Todos los {len(verified)} productos verificados en sus URLs",
                    details={}
                ),
                verified
            )

    def _verify_product_at_url(self, product: 'DetectedProduct') -> bool:
        """
        Re-fetch la URL y verificar que el producto existe.
        """
        try:
            response = httpx.get(
                product.source_url,
                timeout=10,
                follow_redirects=True,
                verify=False,  # Some sites have SSL cert issues
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ClonnectBot/1.0)"
                }
            )

            if response.status_code != 200:
                logger.warning(f"URL returned {response.status_code}: {product.source_url}")
                return False

            content = response.text.lower()

            # Verificar que el nombre del producto aparece en la página
            name_words = product.name.lower().split()[:3]  # Primeras 3 palabras
            found = any(word in content for word in name_words if len(word) > 3)

            if not found:
                logger.warning(f"Producto '{product.name}' no encontrado en {product.source_url}")
                return False

            # Si tiene precio, verificar que el precio también aparece
            if product.price is not None:
                price_str = str(int(product.price))
                if price_str not in content and f"€{price_str}" not in content:
                    logger.warning(f"Precio €{product.price} no encontrado en {product.source_url}")
                    # No rechazar solo por esto, el precio podría estar formateado diferente

            return True

        except Exception as e:
            logger.error(f"Error verificando {product.source_url}: {e}")
            return False


def get_sanity_checker() -> SanityChecker:
    """Get checker instance."""
    return SanityChecker()
