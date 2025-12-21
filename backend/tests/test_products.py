"""
Tests para gestion de productos
"""

import pytest
import tempfile
import shutil
import os
from core.products import ProductManager, Product, SalesTracker


class TestProduct:
    """Tests para la clase Product"""

    def test_product_creation(self):
        """Test crear producto"""
        product = Product(
            id="test-product",
            name="Test Product",
            description="A test product",
            price=99.0
        )
        assert product.id == "test-product"
        assert product.name == "Test Product"
        assert product.price == 99.0
        assert product.currency == "EUR"
        assert product.is_active is True

    def test_product_to_dict(self):
        """Test conversion a diccionario"""
        product = Product(
            id="test",
            name="Test",
            description="Desc",
            price=50.0
        )
        data = product.to_dict()
        assert data["id"] == "test"
        assert data["name"] == "Test"
        assert data["price"] == 50.0

    def test_product_from_dict(self):
        """Test crear desde diccionario"""
        data = {
            "id": "from-dict",
            "name": "From Dict",
            "description": "Created from dict",
            "price": 150.0,
            "currency": "USD"
        }
        product = Product.from_dict(data)
        assert product.id == "from-dict"
        assert product.currency == "USD"

    def test_product_matches_query(self):
        """Test coincidencia con query"""
        product = Product(
            id="curso-python",
            name="Curso de Python",
            description="Aprende Python desde cero",
            price=197.0,
            category="cursos",
            keywords=["python", "programacion"]
        )

        # Match por keyword
        assert product.matches_query("python") > 0
        # Match por nombre
        assert product.matches_query("curso") > 0
        # Match por categoria
        assert product.matches_query("cursos") > 0
        # No match
        assert product.matches_query("javascript") == 0

    def test_get_short_description(self):
        """Test descripcion corta"""
        product = Product(
            id="test",
            name="Test",
            description="Esta es una descripcion muy larga que deberia ser truncada",
            price=10.0
        )
        short = product.get_short_description(20)
        assert len(short) <= 20
        assert short.endswith("...")


class TestProductManager:
    """Tests para ProductManager"""

    def setup_method(self):
        """Setup con directorio temporal"""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = ProductManager(storage_path=self.temp_dir)
        self.creator_id = "test-creator"

    def teardown_method(self):
        """Cleanup"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_product(self):
        """Test anadir producto"""
        product = Product(
            id="test-1",
            name="Test Product",
            description="Test",
            price=100.0
        )
        product_id = self.manager.add_product(self.creator_id, product)
        assert product_id == "test-1"

        # Verificar que se guardo
        products = self.manager.get_products(self.creator_id)
        assert len(products) == 1
        assert products[0].id == "test-1"

    def test_add_product_duplicate_id(self):
        """Test ID duplicado genera nuevo ID"""
        product1 = Product(id="dup", name="First", description="First", price=50.0)
        product2 = Product(id="dup", name="Second", description="Second", price=60.0)

        id1 = self.manager.add_product(self.creator_id, product1)
        id2 = self.manager.add_product(self.creator_id, product2)

        assert id1 == "dup"
        assert id2 != "dup"  # Deberia generar ID unico

    def test_get_product_by_id(self):
        """Test obtener producto por ID"""
        product = Product(id="find-me", name="Find Me", description="Test", price=25.0)
        self.manager.add_product(self.creator_id, product)

        found = self.manager.get_product_by_id(self.creator_id, "find-me")
        assert found is not None
        assert found.name == "Find Me"

        not_found = self.manager.get_product_by_id(self.creator_id, "not-exist")
        assert not_found is None

    def test_update_product(self):
        """Test actualizar producto"""
        product = Product(id="update-me", name="Original", description="Test", price=100.0)
        self.manager.add_product(self.creator_id, product)

        updated = self.manager.update_product(self.creator_id, "update-me", {"name": "Updated", "price": 150.0})
        assert updated is not None
        assert updated.name == "Updated"
        assert updated.price == 150.0

    def test_delete_product(self):
        """Test eliminar producto"""
        product = Product(id="delete-me", name="Delete Me", description="Test", price=10.0)
        self.manager.add_product(self.creator_id, product)

        success = self.manager.delete_product(self.creator_id, "delete-me")
        assert success is True

        # Verificar que se elimino
        products = self.manager.get_products(self.creator_id)
        assert len(products) == 0

    def test_search_products(self):
        """Test busqueda de productos"""
        product1 = Product(id="p1", name="Curso Python", description="Test", price=100.0, keywords=["python"])
        product2 = Product(id="p2", name="Curso JavaScript", description="Test", price=100.0, keywords=["javascript"])

        self.manager.add_product(self.creator_id, product1)
        self.manager.add_product(self.creator_id, product2)

        results = self.manager.search_products(self.creator_id, "python")
        assert len(results) >= 1
        assert results[0][0].id == "p1"

    def test_recommend_product(self):
        """Test recomendacion de producto"""
        product = Product(
            id="featured",
            name="Featured Product",
            description="Test",
            price=200.0,
            is_featured=True
        )
        self.manager.add_product(self.creator_id, product)

        recommended = self.manager.recommend_product(self.creator_id, {})
        assert recommended is not None

    def test_get_objection_response(self):
        """Test respuesta a objecion"""
        product = Product(
            id="test",
            name="Mi Producto",
            description="Test",
            price=100.0,
            features=["Feature 1", "Feature 2"]
        )
        self.manager.add_product(self.creator_id, product)

        # Test objecion de precio
        response = self.manager.get_objection_response(self.creator_id, "test", "caro")
        assert response != ""
        assert "Mi Producto" in response or "{product_name}" not in response


class TestSalesTracker:
    """Tests para SalesTracker"""

    def setup_method(self):
        """Setup con directorio temporal"""
        self.temp_dir = tempfile.mkdtemp()
        self.tracker = SalesTracker(storage_path=self.temp_dir)
        self.creator_id = "test-creator"

    def teardown_method(self):
        """Cleanup"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_record_click(self):
        """Test registrar clic"""
        self.tracker.record_click(self.creator_id, "product-1", "follower-1")
        stats = self.tracker.get_stats(self.creator_id)
        assert stats["total_clicks"] == 1

    def test_record_sale(self):
        """Test registrar venta"""
        self.tracker.record_sale(self.creator_id, "product-1", "follower-1", 99.0)
        stats = self.tracker.get_stats(self.creator_id)
        assert stats["total_sales"] == 1
        assert stats["total_revenue"] == 99.0

    def test_conversion_rate(self):
        """Test tasa de conversion"""
        # 2 clics, 1 venta = 50% conversion
        self.tracker.record_click(self.creator_id, "p1", "f1")
        self.tracker.record_click(self.creator_id, "p1", "f2")
        self.tracker.record_sale(self.creator_id, "p1", "f1", 100.0)

        stats = self.tracker.get_stats(self.creator_id)
        assert stats["conversion_rate"] == 0.5
