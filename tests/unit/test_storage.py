import pytest

from kaos_graph.storage.vfs import load_from_vfs, save_to_vfs


class TestVfsStorage:
    @pytest.mark.asyncio
    async def test_save_requires_context(self):
        from kaos_graph import Graph

        g = Graph()
        g.add_node("a")
        with pytest.raises(ValueError, match="requires a KaosContext"):
            await save_to_vfs(g, "test")

    @pytest.mark.asyncio
    async def test_load_requires_context(self):
        with pytest.raises(ValueError, match="requires a KaosContext"):
            await load_from_vfs("test")


class TestVfsRoundTrip:
    @pytest.mark.asyncio
    async def test_save_load_roundtrip(self):
        """Test save -> load round-trip with a mock VFS."""
        from kaos_graph import Graph

        # Create a mock VFS and runtime
        storage: dict[str, bytes] = {}

        class MockVFS:
            async def write(self, path: str, data: bytes, context_id: str | None = None) -> int:
                storage[path] = data
                return len(data)

            async def read(self, path: str, context_id: str | None = None) -> bytes:
                return storage[path]

        class MockManifest:
            uri = "kaos://artifacts/test-graph"

        class MockArtifacts:
            async def create_from_path(self, path: str, **kwargs: object) -> MockManifest:
                return MockManifest()

        class MockRuntime:
            vfs = MockVFS()
            artifacts = MockArtifacts()

        class MockContext:
            runtime = MockRuntime()
            session_id = "test-session"

        g = Graph()
        g.add_node("a", color="red")
        g.add_node("b")
        g.add_edge("a", "b", weight=1.5)

        uri = await save_to_vfs(g, "test-graph", context=MockContext())
        assert uri == "kaos://artifacts/test-graph"
        assert "graphs/test-graph.json" in storage

        g2 = await load_from_vfs("test-graph", context=MockContext())
        assert g2.n_nodes == 2
        assert g2.n_edges == 1
        props = g2.node("a")
        assert props is not None
        assert props["color"] == "red"
