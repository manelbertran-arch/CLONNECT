"""Audit tests for core/products.py"""

import tempfile

from core.products import Product, ProductManager


class TestAuditProducts:
    def test_import(self):
        from core.products import Product, ProductManager, SalesTracker  # noqa: F811

        assert Product is not None
        assert ProductManager is not None

    def test_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ProductManager(storage_path=tmpdir)
            assert manager is not None

    def test_happy_path_product_to_dict(self):
        product = Product(id="p1", name="Curso Test", description="Test desc", price=99.0)
        d = product.to_dict()
        assert isinstance(d, dict)
        assert d["name"] == "Curso Test"

    def test_edge_case_matches_query(self):
        product = Product(
            id="p1", name="Coaching Premium", description="Coaching session", price=199.0
        )
        result = product.matches_query("coaching")
        assert isinstance(result, (bool, float, int))

    def test_error_handling_get_products_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ProductManager(storage_path=tmpdir)
            products = manager.get_products("nonexistent_creator")
            assert isinstance(products, list)
            assert len(products) == 0
