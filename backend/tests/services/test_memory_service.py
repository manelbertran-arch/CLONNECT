"""
Memory Service tests - Written BEFORE implementation (TDD).
Run these tests FIRST - they should FAIL until service is created.
"""
import pytest


class TestMemoryServiceImport:
    """Test memory service can be imported."""

    def test_memory_service_module_exists(self):
        """Memory service module should exist."""
        import services.memory_service
        assert services.memory_service is not None

    def test_follower_memory_class_exists(self):
        """FollowerMemory class should exist."""
        from services.memory_service import FollowerMemory
        assert FollowerMemory is not None

    def test_memory_store_class_exists(self):
        """MemoryStore class should exist."""
        from services.memory_service import MemoryStore
        assert MemoryStore is not None

    def test_memory_store_has_get_method(self):
        """MemoryStore should have get method."""
        from services.memory_service import MemoryStore
        assert hasattr(MemoryStore, 'get')

    def test_memory_store_has_save_method(self):
        """MemoryStore should have save method."""
        from services.memory_service import MemoryStore
        assert hasattr(MemoryStore, 'save')

    def test_memory_store_has_get_or_create_method(self):
        """MemoryStore should have get_or_create method."""
        from services.memory_service import MemoryStore
        assert hasattr(MemoryStore, 'get_or_create')


class TestFollowerMemoryDataclass:
    """Test FollowerMemory dataclass."""

    def test_follower_memory_instantiation(self):
        """FollowerMemory should be instantiable with required fields."""
        from services.memory_service import FollowerMemory
        memory = FollowerMemory(
            follower_id="test_follower",
            creator_id="test_creator"
        )
        assert memory is not None
        assert memory.follower_id == "test_follower"
        assert memory.creator_id == "test_creator"

    def test_follower_memory_has_default_values(self):
        """FollowerMemory should have sensible default values."""
        from services.memory_service import FollowerMemory
        memory = FollowerMemory(
            follower_id="test_follower",
            creator_id="test_creator"
        )
        assert memory.username == ""
        assert memory.total_messages == 0
        assert memory.purchase_intent_score == 0.0
        assert memory.status == "new"
        assert memory.interests == []
        assert memory.last_messages == []

    def test_follower_memory_handles_none_values(self):
        """FollowerMemory should handle None values gracefully."""
        from services.memory_service import FollowerMemory
        memory = FollowerMemory(
            follower_id="test",
            creator_id="test",
            username=None,
            total_messages=None,
        )
        # After __post_init__, None should be replaced with defaults
        assert memory.username == ""
        assert memory.total_messages == 0


class TestMemoryStoreInstantiation:
    """Test MemoryStore instantiation."""

    def test_memory_store_instantiation(self):
        """MemoryStore should be instantiable."""
        from services.memory_service import MemoryStore
        store = MemoryStore()
        assert store is not None

    def test_memory_store_with_custom_path(self):
        """MemoryStore should accept custom storage path."""
        from services.memory_service import MemoryStore
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(storage_path=tmpdir)
            assert store is not None


class TestMemoryStoreOperations:
    """Test MemoryStore CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_returns_none_for_nonexistent(self):
        """get should return None for non-existent follower."""
        from services.memory_service import MemoryStore
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(storage_path=tmpdir)
            result = await store.get("creator1", "nonexistent_follower")
            assert result is None

    @pytest.mark.asyncio
    async def test_save_and_get_roundtrip(self):
        """save then get should return the same data."""
        from services.memory_service import FollowerMemory, MemoryStore
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(storage_path=tmpdir)

            # Create and save
            memory = FollowerMemory(
                follower_id="follower123",
                creator_id="creator456",
                username="testuser",
                total_messages=5,
            )
            await store.save(memory)

            # Get back
            retrieved = await store.get("creator456", "follower123")
            assert retrieved is not None
            assert retrieved.follower_id == "follower123"
            assert retrieved.username == "testuser"
            assert retrieved.total_messages == 5

    @pytest.mark.asyncio
    async def test_get_or_create_creates_new(self):
        """get_or_create should create new memory if not exists."""
        from services.memory_service import MemoryStore
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(storage_path=tmpdir)

            memory = await store.get_or_create(
                creator_id="creator1",
                follower_id="new_follower",
                username="newuser"
            )
            assert memory is not None
            assert memory.follower_id == "new_follower"
            assert memory.username == "newuser"

    @pytest.mark.asyncio
    async def test_get_or_create_returns_existing(self):
        """get_or_create should return existing memory if exists."""
        from services.memory_service import FollowerMemory, MemoryStore
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(storage_path=tmpdir)

            # Create first
            original = FollowerMemory(
                follower_id="existing",
                creator_id="creator1",
                username="originaluser",
                total_messages=10,
            )
            await store.save(original)

            # get_or_create should return existing
            retrieved = await store.get_or_create(
                creator_id="creator1",
                follower_id="existing",
                username="different_name"  # Should be ignored
            )
            assert retrieved.username == "originaluser"
            assert retrieved.total_messages == 10


class TestMemoryStoreCaching:
    """Test MemoryStore caching behavior."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_same_object(self):
        """Subsequent gets should return cached object."""
        from services.memory_service import FollowerMemory, MemoryStore
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(storage_path=tmpdir)

            memory = FollowerMemory(
                follower_id="cached",
                creator_id="creator1",
            )
            await store.save(memory)

            # Get twice
            first = await store.get("creator1", "cached")
            second = await store.get("creator1", "cached")

            # Should be same object from cache
            assert first is second
