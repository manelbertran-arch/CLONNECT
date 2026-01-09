"""
SanityChecker - Verifies extraction results are reasonable
Principle: If something looks wrong, REJECT it
"""

import logging
import httpx
from typing import List, Optional
from urllib.parse import urlparse

from .models import DetectedProduct, CheckResult, VerificationResult

logger = logging.getLogger(__name__)


class SanityChecker:
    """
    Verifies that extraction results make sense.
    If something is suspicious, REJECT the whole batch.
    """

    MAX_PRODUCTS = 20
    MIN_PRICE = 0      # Allow free products
    MAX_PRICE = 50000  # Reasonable max for digital products

    def verify(self, products: List[DetectedProduct], website_url: str) -> VerificationResult:
        """
        Run all sanity checks on extracted products.
        Returns VerificationResult with pass/fail status.
        """
        checks = []
        filtered_products = list(products)

        # Check 1: Reasonable number of products
        count_check = self._check_product_count(filtered_products)
        checks.append(count_check)

        # Check 2: All have source_url
        source_check, filtered_products = self._check_source_urls(filtered_products)
        checks.append(source_check)

        # Check 3: All URLs from same domain
        domain_check, filtered_products = self._check_same_domain(filtered_products, website_url)
        checks.append(domain_check)

        # Check 4: Reasonable prices
        price_check = self._check_reasonable_prices(filtered_products)
        checks.append(price_check)

        # Check 5: No duplicate products
        dupe_check, filtered_products = self._check_duplicates(filtered_products)
        checks.append(dupe_check)

        # Check 6: Re-verify by fetching URLs (async would be better, but sync for simplicity)
        verify_check = self._check_url_verification(filtered_products)
        checks.append(verify_check)

        # Determine overall status
        critical_failed = any(
            not c.passed for c in checks
            if c.name in ['product_count', 'source_urls', 'same_domain']
        )

        if critical_failed:
            status = 'failed'
        elif any(not c.passed for c in checks):
            status = 'needs_review'
        else:
            status = 'success'

        return VerificationResult(
            passed=status == 'success',
            status=status,
            checks=checks,
            products=filtered_products
        )

    def _check_product_count(self, products: List[DetectedProduct]) -> CheckResult:
        """Check if product count is reasonable"""
        count = len(products)

        if count > self.MAX_PRODUCTS:
            return CheckResult(
                name='product_count',
                passed=False,
                message=f"Too many products: {count}. Maximum expected: {self.MAX_PRODUCTS}. "
                        "This suggests extraction is too liberal."
            )
        elif count == 0:
            return CheckResult(
                name='product_count',
                passed=True,
                message="No products found (may be correct for some websites)"
            )
        else:
            return CheckResult(
                name='product_count',
                passed=True,
                message=f"Product count OK: {count}"
            )

    def _check_source_urls(self, products: List[DetectedProduct]) -> tuple:
        """Check all products have source_url and source_html"""
        products_without_source = [p for p in products if not p.source_url or not p.source_html]

        if products_without_source:
            # Remove products without source
            filtered = [p for p in products if p.source_url and p.source_html]
            return (
                CheckResult(
                    name='source_urls',
                    passed=False,
                    message=f"{len(products_without_source)} products without source proof. REJECTED."
                ),
                filtered
            )

        return (
            CheckResult(
                name='source_urls',
                passed=True,
                message="All products have source_url and source_html proof"
            ),
            products
        )

    def _check_same_domain(self, products: List[DetectedProduct], website_url: str) -> tuple:
        """Check all source URLs are from the same domain"""
        base_domain = urlparse(website_url).netloc.lower()

        # Handle www. variations
        base_domain_clean = base_domain.replace('www.', '')

        foreign_products = []
        valid_products = []

        for p in products:
            product_domain = urlparse(p.source_url).netloc.lower().replace('www.', '')
            if product_domain == base_domain_clean:
                valid_products.append(p)
            else:
                foreign_products.append(p)

        if foreign_products:
            return (
                CheckResult(
                    name='same_domain',
                    passed=False,
                    message=f"{len(foreign_products)} products from different domain. REJECTED. "
                            f"Expected domain: {base_domain}"
                ),
                valid_products
            )

        return (
            CheckResult(
                name='same_domain',
                passed=True,
                message=f"All products from same domain: {base_domain}"
            ),
            products
        )

    def _check_reasonable_prices(self, products: List[DetectedProduct]) -> CheckResult:
        """Check prices are within reasonable range"""
        suspicious = []

        for p in products:
            if p.price is not None:
                if p.price < self.MIN_PRICE:
                    suspicious.append(f"{p.name}: €{p.price} (negative)")
                elif p.price > self.MAX_PRICE:
                    suspicious.append(f"{p.name}: €{p.price} (too high)")

        if suspicious:
            return CheckResult(
                name='reasonable_prices',
                passed=False,
                message=f"Suspicious prices found: {', '.join(suspicious)}"
            )

        # Count products with prices
        with_price = len([p for p in products if p.price is not None])
        without_price = len(products) - with_price

        return CheckResult(
            name='reasonable_prices',
            passed=True,
            message=f"Prices OK. {with_price} with price, {without_price} without (NULL, not invented)"
        )

    def _check_duplicates(self, products: List[DetectedProduct]) -> tuple:
        """Check for duplicate products"""
        seen_urls = set()
        seen_names = set()
        unique_products = []

        for p in products:
            url_key = p.source_url.lower().rstrip('/')
            name_key = p.name.lower().strip()

            if url_key in seen_urls or name_key in seen_names:
                continue

            seen_urls.add(url_key)
            seen_names.add(name_key)
            unique_products.append(p)

        removed = len(products) - len(unique_products)

        if removed > 0:
            return (
                CheckResult(
                    name='no_duplicates',
                    passed=True,  # Not a failure, just cleanup
                    message=f"Removed {removed} duplicate products"
                ),
                unique_products
            )

        return (
            CheckResult(
                name='no_duplicates',
                passed=True,
                message="No duplicates found"
            ),
            products
        )

    def _check_url_verification(self, products: List[DetectedProduct]) -> CheckResult:
        """Re-fetch URLs and verify products still exist"""
        verified = 0
        failed = 0

        for product in products:
            try:
                # Quick fetch to verify
                result = self._verify_product_at_url(product)
                if result:
                    product.verified = True
                    product.verification_note = "Verified: product found at URL"
                    verified += 1
                else:
                    product.verified = False
                    product.verification_note = "Warning: could not verify at URL"
                    failed += 1
            except Exception as e:
                product.verified = False
                product.verification_note = f"Verification error: {str(e)}"
                failed += 1

        if failed > 0 and failed > verified:
            return CheckResult(
                name='url_verification',
                passed=False,
                message=f"URL verification: {verified} verified, {failed} failed. "
                        "Most products could not be verified."
            )

        return CheckResult(
            name='url_verification',
            passed=True,
            message=f"URL verification: {verified} verified, {failed} unverified"
        )

    def _verify_product_at_url(self, product: DetectedProduct) -> bool:
        """
        Fetch the URL and verify the product name exists in the page.
        Returns True if verified, False otherwise.
        """
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                response = client.get(product.source_url)
                if response.status_code != 200:
                    return False

                # Check if product name appears in page
                page_text = response.text.lower()
                product_name_lower = product.name.lower()

                # Try exact match first
                if product_name_lower in page_text:
                    return True

                # Try partial match (first 3 significant words)
                words = [w for w in product_name_lower.split() if len(w) > 3][:3]
                if words:
                    matched = sum(1 for w in words if w in page_text)
                    if matched >= len(words) * 0.5:  # At least 50% of words match
                        return True

                return False

        except Exception as e:
            logger.warning(f"[SanityChecker] Verification failed for {product.source_url}: {e}")
            return False
