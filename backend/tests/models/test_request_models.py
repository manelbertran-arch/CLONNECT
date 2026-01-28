"""
Request schemas tests - Written BEFORE implementation (TDD).
Run these tests FIRST - they should FAIL until schemas are created.
"""
import pytest
from pydantic import ValidationError


class TestSchemasPackageImport:
    """Test schemas package can be imported."""

    def test_schemas_package_exists(self):
        """Schemas package should exist and be importable."""
        import api.schemas
        assert api.schemas is not None

    def test_schemas_init_exports_creator_request(self):
        """Schemas __init__ should export CreateCreatorRequest."""
        from api.schemas import CreateCreatorRequest
        assert CreateCreatorRequest is not None

    def test_schemas_init_exports_product_request(self):
        """Schemas __init__ should export CreateProductRequest."""
        from api.schemas import CreateProductRequest
        assert CreateProductRequest is not None


class TestCreateCreatorRequestImport:
    """Test CreateCreatorRequest schema can be imported."""

    def test_import_from_package(self):
        from api.schemas import CreateCreatorRequest
        assert CreateCreatorRequest is not None

    def test_import_from_module(self):
        from api.schemas.requests import CreateCreatorRequest
        assert CreateCreatorRequest is not None


class TestCreateProductRequestImport:
    """Test CreateProductRequest schema can be imported."""

    def test_import_from_package(self):
        from api.schemas import CreateProductRequest
        assert CreateProductRequest is not None

    def test_import_from_module(self):
        from api.schemas.requests import CreateProductRequest
        assert CreateProductRequest is not None


class TestCreateCreatorRequestValidation:
    """Test CreateCreatorRequest validation rules."""

    def test_valid_creator_request(self):
        """Should accept valid data with required fields."""
        from api.schemas import CreateCreatorRequest
        creator = CreateCreatorRequest(
            id="creator123",
            name="Test Creator",
            instagram_handle="@testcreator"
        )
        assert creator.id == "creator123"
        assert creator.name == "Test Creator"
        assert creator.instagram_handle == "@testcreator"

    def test_creator_request_with_optional_fields(self):
        """Should accept optional fields."""
        from api.schemas import CreateCreatorRequest
        creator = CreateCreatorRequest(
            id="creator123",
            name="Test Creator",
            instagram_handle="@testcreator",
            personality={"tone": "friendly"},
            emoji_style="high",
            sales_style="aggressive"
        )
        assert creator.personality == {"tone": "friendly"}
        assert creator.emoji_style == "high"
        assert creator.sales_style == "aggressive"

    def test_creator_request_default_optional_values(self):
        """Optional fields should have correct defaults."""
        from api.schemas import CreateCreatorRequest
        creator = CreateCreatorRequest(
            id="creator123",
            name="Test Creator",
            instagram_handle="@testcreator"
        )
        assert creator.personality is None
        assert creator.emoji_style == "moderate"
        assert creator.sales_style == "soft"

    def test_creator_request_requires_id(self):
        """Should require id field."""
        from api.schemas import CreateCreatorRequest
        with pytest.raises(ValidationError):
            CreateCreatorRequest(
                name="Test Creator",
                instagram_handle="@testcreator"
            )

    def test_creator_request_requires_name(self):
        """Should require name field."""
        from api.schemas import CreateCreatorRequest
        with pytest.raises(ValidationError):
            CreateCreatorRequest(
                id="creator123",
                instagram_handle="@testcreator"
            )

    def test_creator_request_requires_instagram_handle(self):
        """Should require instagram_handle field."""
        from api.schemas import CreateCreatorRequest
        with pytest.raises(ValidationError):
            CreateCreatorRequest(
                id="creator123",
                name="Test Creator"
            )


class TestCreateProductRequestValidation:
    """Test CreateProductRequest validation rules."""

    def test_valid_product_request(self):
        """Should accept valid data with required fields."""
        from api.schemas import CreateProductRequest
        product = CreateProductRequest(
            id="product123",
            name="Test Product",
            description="A test product description",
            price=99.99
        )
        assert product.id == "product123"
        assert product.name == "Test Product"
        assert product.price == 99.99

    def test_product_request_with_optional_fields(self):
        """Should accept optional fields."""
        from api.schemas import CreateProductRequest
        product = CreateProductRequest(
            id="product123",
            name="Test Product",
            description="Description",
            price=49.99,
            currency="USD",
            payment_link="https://pay.example.com",
            category="digital",
            features=["feature1", "feature2"],
            keywords=["keyword1", "keyword2"]
        )
        assert product.currency == "USD"
        assert product.payment_link == "https://pay.example.com"
        assert product.category == "digital"
        assert product.features == ["feature1", "feature2"]
        assert product.keywords == ["keyword1", "keyword2"]

    def test_product_request_default_optional_values(self):
        """Optional fields should have correct defaults."""
        from api.schemas import CreateProductRequest
        product = CreateProductRequest(
            id="product123",
            name="Test Product",
            description="Description",
            price=29.99
        )
        assert product.currency == "EUR"
        assert product.payment_link == ""
        assert product.category == ""
        assert product.features == []
        assert product.keywords == []

    def test_product_request_requires_id(self):
        """Should require id field."""
        from api.schemas import CreateProductRequest
        with pytest.raises(ValidationError):
            CreateProductRequest(
                name="Test Product",
                description="Description",
                price=99.99
            )

    def test_product_request_requires_name(self):
        """Should require name field."""
        from api.schemas import CreateProductRequest
        with pytest.raises(ValidationError):
            CreateProductRequest(
                id="product123",
                description="Description",
                price=99.99
            )

    def test_product_request_requires_description(self):
        """Should require description field."""
        from api.schemas import CreateProductRequest
        with pytest.raises(ValidationError):
            CreateProductRequest(
                id="product123",
                name="Test Product",
                price=99.99
            )

    def test_product_request_requires_price(self):
        """Should require price field."""
        from api.schemas import CreateProductRequest
        with pytest.raises(ValidationError):
            CreateProductRequest(
                id="product123",
                name="Test Product",
                description="Description"
            )
