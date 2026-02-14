"""
Tests críticos que DEBEN pasar antes de cualquier deploy.
Si fallan, el sistema de detección de productos está roto.

Ejecutar: pytest tests/test_ingestion_critical.py -v -m critical
"""

import pytest


@pytest.mark.critical
class TestIngestionV2Critical:
    """Tests críticos para IngestionV2Pipeline - NO DEBEN FALLAR"""

    @pytest.mark.asyncio
    async def test_pipeline_detects_products_from_website(self):
        """El pipeline DEBE detectar productos con precio de una web real"""
        from ingestion.v2.pipeline import IngestionV2Pipeline

        pipeline = IngestionV2Pipeline(db_session=None, max_pages=100)
        result = await pipeline.run(
            creator_id="test_critical",
            website_url="https://www.stefanobonanno.com",
            clean_before=False,
            re_verify=False,
        )

        assert result.pages_scraped > 0, "Debe scrapear páginas"
        assert result.products_detected >= 1, "Debe detectar al menos 1 producto"

        # Verificar que detecta el producto Fitpack Challenge €22
        product_prices = [p.get("price") for p in result.products if p.get("price")]
        assert 22.0 in product_prices, f"Debe detectar producto de €22, encontrados: {product_prices}"

    @pytest.mark.asyncio
    async def test_pipeline_creates_result_structure(self):
        """El pipeline DEBE devolver estructura correcta"""
        from ingestion.v2.pipeline import IngestionV2Pipeline

        pipeline = IngestionV2Pipeline(db_session=None, max_pages=5)
        result = await pipeline.run(
            creator_id="test_structure",
            website_url="https://www.stefanobonanno.com",
            clean_before=False,
            re_verify=False,
        )

        # Verificar estructura del resultado
        assert hasattr(result, "success"), "Debe tener campo success"
        assert hasattr(result, "status"), "Debe tener campo status"
        assert hasattr(result, "pages_scraped"), "Debe tener campo pages_scraped"
        assert hasattr(result, "products_detected"), "Debe tener campo products_detected"
        assert hasattr(result, "products"), "Debe tener campo products"
        assert hasattr(result, "sanity_checks"), "Debe tener campo sanity_checks"

    @pytest.mark.asyncio
    async def test_pipeline_without_db_does_not_crash(self):
        """El pipeline NO debe crashear sin db_session (modo preview)"""
        from ingestion.v2.pipeline import IngestionV2Pipeline

        pipeline = IngestionV2Pipeline(db_session=None, max_pages=5)

        # No debe lanzar excepción
        result = await pipeline.run(
            creator_id="test_no_db",
            website_url="https://www.stefanobonanno.com",
            clean_before=False,
            re_verify=False,
        )

        assert result is not None, "Debe devolver resultado aunque no haya DB"
        assert result.products_saved == 0, "Sin DB, products_saved debe ser 0"


@pytest.mark.critical
class TestProductDetectorCritical:
    """Tests críticos para ProductDetector"""

    def test_detector_finds_price_in_text(self):
        """El detector DEBE encontrar precios en texto"""
        from ingestion.v2.product_detector import ProductDetector

        detector = ProductDetector()

        # Texto con precio claro
        test_text = "Apúntate por solo €22 al Fitpack Challenge"
        price, currency, source_text = detector._extract_price(test_text)

        assert price is not None, f"Debe encontrar precio en: {test_text}"
        assert price == 22.0, f"Debe encontrar €22, encontrado: {price}"
        assert currency == "EUR", f"Debe ser EUR, encontrado: {currency}"

    def test_detector_finds_euro_prices(self):
        """El detector DEBE encontrar precios en euros (formato principal)"""
        from ingestion.v2.product_detector import ProductDetector

        detector = ProductDetector()

        # Formatos EUR que son los principales para este mercado
        test_cases = [
            ("Solo 22€", 22.0),
            ("Precio: €99", 99.0),
            ("Por €150", 150.0),
            ("APÚNTATE POR SÓLO €22", 22.0),
        ]

        for text, expected_price in test_cases:
            price, _, _ = detector._extract_price(text)
            assert price == expected_price, f"En '{text}' esperaba {expected_price}, encontró {price}"
