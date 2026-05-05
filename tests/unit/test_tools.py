"""Tests for kaos-graph MCP tools."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from kaos_graph import Graph
from kaos_graph.tools import _ALGORITHMS, _EXPORT_FORMATS, register_graph_tools


def _make_graph_json(directed: bool = True, name: str = "test") -> str:
    """Build a small test graph and return its JSON serialization."""
    g = Graph(directed=directed, name=name)
    g.add_node("a", type="start")
    g.add_node("b", type="middle")
    g.add_node("c", type="end")
    g.add_edge("a", "b", weight=1.0)
    g.add_edge("b", "c", weight=2.0)
    return g.to_json()


def _make_dag_json_with_weights() -> str:
    """Build a DAG with latency_ms properties for critical_path testing."""
    g = Graph(directed=True, name="pipeline")
    g.add_node("start", latency_ms=10.0)
    g.add_node("step_a", latency_ms=50.0)
    g.add_node("step_b", latency_ms=30.0)
    g.add_node("end", latency_ms=5.0)
    g.add_edge("start", "step_a")
    g.add_edge("start", "step_b")
    g.add_edge("step_a", "end")
    g.add_edge("step_b", "end")
    return g.to_json()


class TestRegisterGraphTools:
    """Test the tool registration function."""

    def test_raises_without_kaos_core(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """register_graph_tools raises ImportError without kaos-core."""
        import builtins
        import types

        real_import = builtins.__import__

        def mock_import(
            name: str,
            globals: dict[str, object] | None = None,
            locals: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> types.ModuleType:
            if name.startswith("kaos_core"):
                raise ImportError("kaos-core not installed")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        with pytest.raises(ImportError, match="kaos-core is required"):
            register_graph_tools(cast(Any, object()))

    def test_function_exists(self) -> None:
        """register_graph_tools is importable and callable."""
        assert callable(register_graph_tools)

    def test_constants_defined(self) -> None:
        """Algorithm and format constants are populated."""
        assert len(_ALGORITHMS) > 0
        assert "pagerank" in _ALGORITHMS
        assert "shortest_path" in _ALGORITHMS

        assert len(_EXPORT_FORMATS) > 0
        assert "mermaid" in _EXPORT_FORMATS
        assert "json" in _EXPORT_FORMATS

    def test_graph_json_roundtrip(self) -> None:
        """The test helper produces valid graph JSON."""
        data = _make_graph_json()
        g = Graph.from_json(data)
        assert g.n_nodes == 3
        assert g.n_edges == 2
        assert g.has_node("a")
        assert g.has_node("b")
        assert g.has_node("c")


class TestToolsWithMockRuntime:
    """Test tool registration with a mock runtime (no kaos-core needed)."""

    def test_register_with_mock_runtime(self) -> None:
        """Tools can register against a mock runtime if kaos-core is available."""
        try:
            from kaos_core.base.tool import KaosTool
        except ImportError:
            pytest.skip("kaos-core not installed")

        class MockToolRegistry:
            def __init__(self) -> None:
                self.tools: dict[str, KaosTool] = {}

            def register_tool(self, tool: KaosTool) -> None:
                self.tools[tool.metadata.name] = tool

        class MockRuntime:
            def __init__(self) -> None:
                self.tools = MockToolRegistry()

        runtime = MockRuntime()
        count = register_graph_tools(runtime)
        assert count == 17

        expected_names = {
            "kaos-graph-create",
            "kaos-graph-query",
            "kaos-graph-algorithm",
            "kaos-graph-load-rdf",
            "kaos-graph-export",
            "kaos-graph-info",
            "kaos-graph-visualize",
            "kaos-graph-transform",
            "kaos-graph-trace-to-graph",
            "kaos-graph-validate-schema",
            "kaos-graph-load-adjacency",
            "kaos-graph-load-rdf-string",
            "kaos-graph-sparql",
            "kaos-graph-export-adjacency",
            "kaos-graph-critical-path",
            "kaos-graph-find-patterns",
            "kaos-graph-stats",
        }
        assert set(runtime.tools.tools.keys()) == expected_names

    def test_all_tools_have_annotations(self) -> None:
        """Every registered tool has ToolAnnotations set (not None)."""
        try:
            from kaos_core.base.tool import KaosTool
        except ImportError:
            pytest.skip("kaos-core not installed")

        class MockToolRegistry:
            def __init__(self) -> None:
                self.tools: dict[str, KaosTool] = {}

            def register_tool(self, tool: KaosTool) -> None:
                self.tools[tool.metadata.name] = tool

        class MockRuntime:
            def __init__(self) -> None:
                self.tools = MockToolRegistry()

        runtime = MockRuntime()
        register_graph_tools(runtime)

        for name, tool in runtime.tools.tools.items():
            assert tool.metadata.annotations is not None, f"Tool '{name}' has annotations=None"
            assert tool.metadata.annotations.readOnlyHint is True

    def test_all_tools_have_valid_names(self) -> None:
        """Every tool name follows the kaos-graph-* pattern."""
        try:
            from kaos_core.base.tool import KaosTool
        except ImportError:
            pytest.skip("kaos-core not installed")

        class MockToolRegistry:
            def __init__(self) -> None:
                self.tools: dict[str, KaosTool] = {}

            def register_tool(self, tool: KaosTool) -> None:
                self.tools[tool.metadata.name] = tool

        class MockRuntime:
            def __init__(self) -> None:
                self.tools = MockToolRegistry()

        runtime = MockRuntime()
        register_graph_tools(runtime)

        for name in runtime.tools.tools:
            assert name.startswith("kaos-graph-"), f"Tool name '{name}' does not match pattern"


class TestToolExecution:
    """Test tool execution (requires kaos-core)."""

    @pytest.fixture()
    def tools(self) -> dict:
        """Register and return tools dict."""
        try:
            from kaos_core.base.tool import KaosTool
        except ImportError:
            pytest.skip("kaos-core not installed")

        class MockToolRegistry:
            def __init__(self) -> None:
                self.tools: dict[str, KaosTool] = {}

            def register_tool(self, tool: KaosTool) -> None:
                self.tools[tool.metadata.name] = tool

        class MockRuntime:
            def __init__(self) -> None:
                self.tools = MockToolRegistry()

        runtime = MockRuntime()
        register_graph_tools(runtime)
        return runtime.tools.tools

    @pytest.mark.asyncio
    async def test_info_tool(self, tools: dict) -> None:
        """kaos-graph-info returns correct graph properties."""
        tool = tools["kaos-graph-info"]
        result = await tool.execute({"graph_json": _make_graph_json()})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["n_nodes"] == 3
        assert result.structuredContent["n_edges"] == 2
        assert result.structuredContent["is_directed"] is True
        assert result.structuredContent["is_dag"] is True

    @pytest.mark.asyncio
    async def test_info_tool_invalid_json(self, tools: dict) -> None:
        """kaos-graph-info returns error for invalid JSON."""
        tool = tools["kaos-graph-info"]
        result = await tool.execute({"graph_json": "not valid json"})
        assert result.isError

    @pytest.mark.asyncio
    async def test_visualize_tool(self, tools: dict) -> None:
        """kaos-graph-visualize returns Mermaid output."""
        tool = tools["kaos-graph-visualize"]
        result = await tool.execute({"graph_json": _make_graph_json()})
        assert not result.isError
        text = result.text
        assert text is not None
        assert "flowchart" in text
        assert "a" in text

    @pytest.mark.asyncio
    async def test_create_tool(self, tools: dict) -> None:
        """kaos-graph-create builds a graph from JSON definition."""
        tool = tools["kaos-graph-create"]
        definition = json.dumps(
            {
                "name": "test",
                "directed": True,
                "nodes": [{"id": "x"}, {"id": "y"}],
                "edges": [{"source": "x", "target": "y"}],
            }
        )
        result = await tool.execute({"graph_json": definition})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["n_nodes"] == 2
        assert result.structuredContent["n_edges"] == 1

    @pytest.mark.asyncio
    async def test_create_tool_bad_json(self, tools: dict) -> None:
        """kaos-graph-create returns error for malformed input."""
        tool = tools["kaos-graph-create"]
        result = await tool.execute({"graph_json": "{"})
        assert result.isError

    @pytest.mark.asyncio
    async def test_query_tool_node(self, tools: dict) -> None:
        """kaos-graph-query returns node properties."""
        tool = tools["kaos-graph-query"]
        result = await tool.execute(
            {
                "graph_json": _make_graph_json(),
                "node_id": "a",
                "query_type": "node",
            }
        )
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["node_id"] == "a"

    @pytest.mark.asyncio
    async def test_query_tool_missing_node(self, tools: dict) -> None:
        """kaos-graph-query returns error for missing node."""
        tool = tools["kaos-graph-query"]
        result = await tool.execute(
            {
                "graph_json": _make_graph_json(),
                "node_id": "missing",
            }
        )
        assert result.isError

    @pytest.mark.asyncio
    async def test_query_successors(self, tools: dict) -> None:
        """kaos-graph-query returns successors."""
        tool = tools["kaos-graph-query"]
        result = await tool.execute(
            {
                "graph_json": _make_graph_json(),
                "node_id": "a",
                "query_type": "successors",
            }
        )
        assert not result.isError
        assert "b" in result.structuredContent["successors"]

    @pytest.mark.asyncio
    async def test_algorithm_pagerank(self, tools: dict) -> None:
        """kaos-graph-algorithm runs PageRank."""
        tool = tools["kaos-graph-algorithm"]
        result = await tool.execute(
            {
                "graph_json": _make_graph_json(),
                "algorithm": "pagerank",
            }
        )
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["algorithm"] == "pagerank"
        assert len(result.structuredContent["results"]) > 0

    @pytest.mark.asyncio
    async def test_algorithm_bfs(self, tools: dict) -> None:
        """kaos-graph-algorithm runs BFS."""
        tool = tools["kaos-graph-algorithm"]
        result = await tool.execute(
            {
                "graph_json": _make_graph_json(),
                "algorithm": "bfs",
                "source": "a",
            }
        )
        assert not result.isError
        assert result.structuredContent["order"] == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_algorithm_missing_source(self, tools: dict) -> None:
        """kaos-graph-algorithm returns error when source is required but missing."""
        tool = tools["kaos-graph-algorithm"]
        result = await tool.execute(
            {
                "graph_json": _make_graph_json(),
                "algorithm": "bfs",
            }
        )
        assert result.isError

    @pytest.mark.asyncio
    async def test_export_mermaid(self, tools: dict) -> None:
        """kaos-graph-export produces Mermaid output."""
        tool = tools["kaos-graph-export"]
        result = await tool.execute(
            {
                "graph_json": _make_graph_json(),
                "format": "mermaid",
            }
        )
        assert not result.isError
        assert "flowchart" in (result.text or "")

    @pytest.mark.asyncio
    async def test_export_dot(self, tools: dict) -> None:
        """kaos-graph-export produces DOT output."""
        tool = tools["kaos-graph-export"]
        result = await tool.execute(
            {
                "graph_json": _make_graph_json(),
                "format": "dot",
            }
        )
        assert not result.isError
        assert "digraph" in (result.text or "")

    @pytest.mark.asyncio
    async def test_export_json(self, tools: dict) -> None:
        """kaos-graph-export produces JSON output."""
        tool = tools["kaos-graph-export"]
        result = await tool.execute(
            {
                "graph_json": _make_graph_json(),
                "format": "json",
            }
        )
        assert not result.isError
        # Should be valid JSON
        parsed = json.loads(result.text or "")
        assert "nodes" in parsed or "name" in parsed


class TestNewToolMetadata:
    """Test metadata for all 10 new tools."""

    @pytest.fixture()
    def tools(self) -> dict:
        """Register and return tools dict."""
        try:
            from kaos_core.base.tool import KaosTool
        except ImportError:
            pytest.skip("kaos-core not installed")

        class MockToolRegistry:
            def __init__(self) -> None:
                self.tools: dict[str, KaosTool] = {}

            def register_tool(self, tool: KaosTool) -> None:
                self.tools[tool.metadata.name] = tool

        class MockRuntime:
            def __init__(self) -> None:
                self.tools = MockToolRegistry()

        runtime = MockRuntime()
        register_graph_tools(runtime)
        return runtime.tools.tools

    @pytest.mark.parametrize(
        "tool_name",
        [
            "kaos-graph-transform",
            "kaos-graph-trace-to-graph",
            "kaos-graph-validate-schema",
            "kaos-graph-load-adjacency",
            "kaos-graph-load-rdf-string",
            "kaos-graph-sparql",
            "kaos-graph-export-adjacency",
            "kaos-graph-critical-path",
            "kaos-graph-find-patterns",
            "kaos-graph-stats",
        ],
    )
    def test_tool_registered(self, tools: dict, tool_name: str) -> None:
        """Each new tool is registered."""
        assert tool_name in tools

    @pytest.mark.parametrize(
        "tool_name",
        [
            "kaos-graph-transform",
            "kaos-graph-trace-to-graph",
            "kaos-graph-validate-schema",
            "kaos-graph-load-adjacency",
            "kaos-graph-load-rdf-string",
            "kaos-graph-sparql",
            "kaos-graph-export-adjacency",
            "kaos-graph-critical-path",
            "kaos-graph-find-patterns",
            "kaos-graph-stats",
        ],
    )
    def test_tool_has_annotations(self, tools: dict, tool_name: str) -> None:
        """Each new tool has ToolAnnotations set."""
        tool = tools[tool_name]
        assert tool.metadata.annotations is not None
        assert tool.metadata.annotations.readOnlyHint is True
        assert tool.metadata.annotations.destructiveHint is False

    @pytest.mark.parametrize(
        "tool_name",
        [
            "kaos-graph-transform",
            "kaos-graph-trace-to-graph",
            "kaos-graph-validate-schema",
            "kaos-graph-load-adjacency",
            "kaos-graph-load-rdf-string",
            "kaos-graph-sparql",
            "kaos-graph-export-adjacency",
            "kaos-graph-critical-path",
            "kaos-graph-find-patterns",
            "kaos-graph-stats",
        ],
    )
    def test_tool_has_input_schema(self, tools: dict, tool_name: str) -> None:
        """Each new tool has a non-empty input_schema."""
        tool = tools[tool_name]
        assert tool.metadata.input_schema is not None
        assert len(tool.metadata.input_schema) > 0


class TestNewToolExecution:
    """Test execution of the 10 new tools."""

    @pytest.fixture()
    def tools(self) -> dict:
        """Register and return tools dict."""
        try:
            from kaos_core.base.tool import KaosTool
        except ImportError:
            pytest.skip("kaos-core not installed")

        class MockToolRegistry:
            def __init__(self) -> None:
                self.tools: dict[str, KaosTool] = {}

            def register_tool(self, tool: KaosTool) -> None:
                self.tools[tool.metadata.name] = tool

        class MockRuntime:
            def __init__(self) -> None:
                self.tools = MockToolRegistry()

        runtime = MockRuntime()
        register_graph_tools(runtime)
        return runtime.tools.tools

    # ── Transform tool ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_transform_subgraph(self, tools: dict) -> None:
        """kaos-graph-transform extracts a subgraph."""
        tool = tools["kaos-graph-transform"]
        result = await tool.execute(
            {
                "graph_json": _make_graph_json(),
                "operation": "subgraph",
                "nodes": ["a", "b"],
            }
        )
        assert not result.isError
        assert result.structuredContent["n_nodes"] == 2
        assert result.structuredContent["n_edges"] == 1

    @pytest.mark.asyncio
    async def test_transform_reverse(self, tools: dict) -> None:
        """kaos-graph-transform reverses edge directions."""
        tool = tools["kaos-graph-transform"]
        result = await tool.execute({"graph_json": _make_graph_json(), "operation": "reverse"})
        assert not result.isError
        # Reversed graph still has same node/edge counts
        assert result.structuredContent["n_nodes"] == 3
        assert result.structuredContent["n_edges"] == 2
        # Verify edges are reversed: original a->b becomes b->a
        reversed_g = Graph.from_json(result.structuredContent["graph_data"])
        assert reversed_g.has_edge("b", "a")
        assert reversed_g.has_edge("c", "b")

    @pytest.mark.asyncio
    async def test_transform_to_undirected(self, tools: dict) -> None:
        """kaos-graph-transform converts to undirected."""
        tool = tools["kaos-graph-transform"]
        result = await tool.execute(
            {"graph_json": _make_graph_json(), "operation": "to_undirected"}
        )
        assert not result.isError
        assert result.structuredContent["is_directed"] is False

    @pytest.mark.asyncio
    async def test_transform_condensation(self, tools: dict) -> None:
        """kaos-graph-transform computes condensation."""
        tool = tools["kaos-graph-transform"]
        result = await tool.execute({"graph_json": _make_graph_json(), "operation": "condensation"})
        assert not result.isError
        # DAG condensation of a DAG should have same number of SCCs as nodes
        assert result.structuredContent["n_nodes"] == 3

    @pytest.mark.asyncio
    async def test_transform_ego_graph(self, tools: dict) -> None:
        """kaos-graph-transform extracts ego graph."""
        tool = tools["kaos-graph-transform"]
        result = await tool.execute(
            {
                "graph_json": _make_graph_json(),
                "operation": "ego_graph",
                "center": "b",
                "radius": 1,
            }
        )
        assert not result.isError
        # b connects to a and c within radius 1
        assert result.structuredContent["n_nodes"] == 3

    @pytest.mark.asyncio
    async def test_transform_subgraph_missing_nodes(self, tools: dict) -> None:
        """kaos-graph-transform returns error when nodes param is missing for subgraph."""
        tool = tools["kaos-graph-transform"]
        result = await tool.execute({"graph_json": _make_graph_json(), "operation": "subgraph"})
        assert result.isError

    @pytest.mark.asyncio
    async def test_transform_ego_missing_center(self, tools: dict) -> None:
        """kaos-graph-transform returns error when center is missing for ego_graph."""
        tool = tools["kaos-graph-transform"]
        result = await tool.execute({"graph_json": _make_graph_json(), "operation": "ego_graph"})
        assert result.isError

    @pytest.mark.asyncio
    async def test_transform_invalid_json(self, tools: dict) -> None:
        """kaos-graph-transform returns error for bad JSON."""
        tool = tools["kaos-graph-transform"]
        result = await tool.execute({"graph_json": "not json", "operation": "reverse"})
        assert result.isError

    # ── Validate Schema tool ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_validate_schema_valid(self, tools: dict) -> None:
        """kaos-graph-validate-schema passes for valid graph."""
        tool = tools["kaos-graph-validate-schema"]
        schema = json.dumps(
            {
                "node_types": [
                    {"name": "start", "required_properties": []},
                    {"name": "middle", "required_properties": []},
                    {"name": "end", "required_properties": []},
                ],
            }
        )
        result = await tool.execute({"graph_json": _make_graph_json(), "schema_json": schema})
        assert not result.isError
        assert result.structuredContent["valid"] is True
        assert result.structuredContent["violation_count"] == 0

    @pytest.mark.asyncio
    async def test_validate_schema_violations(self, tools: dict) -> None:
        """kaos-graph-validate-schema finds violations."""
        tool = tools["kaos-graph-validate-schema"]
        schema = json.dumps(
            {
                "node_types": [
                    {"name": "start", "required_properties": ["priority"]},
                ],
            }
        )
        result = await tool.execute({"graph_json": _make_graph_json(), "schema_json": schema})
        assert not result.isError
        assert result.structuredContent["valid"] is False
        assert result.structuredContent["violation_count"] > 0

    @pytest.mark.asyncio
    async def test_validate_schema_bad_schema(self, tools: dict) -> None:
        """kaos-graph-validate-schema returns error for bad schema JSON."""
        tool = tools["kaos-graph-validate-schema"]
        result = await tool.execute({"graph_json": _make_graph_json(), "schema_json": "not json"})
        assert result.isError

    # ── Adjacency round-trip ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_adjacency_roundtrip(self, tools: dict) -> None:
        """Load adjacency JSON, then export back to adjacency JSON."""
        load_tool = tools["kaos-graph-load-adjacency"]
        export_tool = tools["kaos-graph-export-adjacency"]

        adjacency = json.dumps(
            {
                "directed": True,
                "nodes": {"x": {"color": "red"}, "y": {"color": "blue"}},
                "edges": {"x": [["y", {"weight": 1.5}]]},
            }
        )

        # Load
        load_result = await load_tool.execute({"adjacency_json": adjacency})
        assert not load_result.isError
        assert load_result.structuredContent["n_nodes"] == 2
        assert load_result.structuredContent["n_edges"] == 1

        # Export back
        graph_data = load_result.structuredContent["graph_data"]
        export_result = await export_tool.execute({"graph_json": graph_data})
        assert not export_result.isError

        # Verify round-trip
        exported = json.loads(export_result.text or "")
        assert "x" in exported["nodes"]
        assert "y" in exported["nodes"]
        assert exported["directed"] is True

    @pytest.mark.asyncio
    async def test_load_adjacency_invalid(self, tools: dict) -> None:
        """kaos-graph-load-adjacency returns error for bad input."""
        tool = tools["kaos-graph-load-adjacency"]
        result = await tool.execute({"adjacency_json": "not json"})
        assert result.isError

    @pytest.mark.asyncio
    async def test_export_adjacency_bad_graph(self, tools: dict) -> None:
        """kaos-graph-export-adjacency returns error for bad graph JSON."""
        tool = tools["kaos-graph-export-adjacency"]
        result = await tool.execute({"graph_json": "bad json"})
        assert result.isError

    # ── Critical path ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_critical_path(self, tools: dict) -> None:
        """kaos-graph-critical-path finds the correct critical path."""
        tool = tools["kaos-graph-critical-path"]
        result = await tool.execute({"graph_json": _make_dag_json_with_weights()})
        assert not result.isError
        content = result.structuredContent
        assert content["path"] is not None
        assert len(content["path"]) > 0
        # The critical path should go through the heaviest route:
        # start(10) -> step_a(50) -> end(5) = 65
        assert content["total_cost"] == 65.0
        assert content["path"] == ["start", "step_a", "end"]

    @pytest.mark.asyncio
    async def test_critical_path_custom_weight(self, tools: dict) -> None:
        """kaos-graph-critical-path uses custom weight key."""
        g = Graph(directed=True, name="custom_weight")
        g.add_node("a", cost=100.0)
        g.add_node("b", cost=200.0)
        g.add_edge("a", "b")
        tool = tools["kaos-graph-critical-path"]
        result = await tool.execute({"graph_json": g.to_json(), "weight": "cost"})
        assert not result.isError
        assert result.structuredContent["total_cost"] == 300.0
        assert result.structuredContent["path"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_critical_path_with_cycle(self, tools: dict) -> None:
        """kaos-graph-critical-path returns error for cyclic graph."""
        g = Graph(directed=True, name="cycle")
        g.add_node("a", latency_ms=10.0)
        g.add_node("b", latency_ms=20.0)
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        tool = tools["kaos-graph-critical-path"]
        result = await tool.execute({"graph_json": g.to_json()})
        assert result.isError

    # ── Find patterns ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_find_patterns_nodes(self, tools: dict) -> None:
        """kaos-graph-find-patterns filters nodes by properties."""
        tool = tools["kaos-graph-find-patterns"]
        result = await tool.execute(
            {
                "graph_json": _make_graph_json(),
                "node_filters": {"type": "start"},
            }
        )
        assert not result.isError
        assert result.structuredContent["node_count"] == 1
        assert "a" in result.structuredContent["matching_nodes"]

    @pytest.mark.asyncio
    async def test_find_patterns_edges(self, tools: dict) -> None:
        """kaos-graph-find-patterns filters edges by properties."""
        tool = tools["kaos-graph-find-patterns"]
        result = await tool.execute(
            {
                "graph_json": _make_graph_json(),
                "edge_filters": {"weight": 2.0},
            }
        )
        assert not result.isError
        assert result.structuredContent["edge_count"] == 1
        edge = result.structuredContent["matching_edges"][0]
        assert edge["source"] == "b"
        assert edge["target"] == "c"

    @pytest.mark.asyncio
    async def test_find_patterns_no_filters(self, tools: dict) -> None:
        """kaos-graph-find-patterns returns error when no filters provided."""
        tool = tools["kaos-graph-find-patterns"]
        result = await tool.execute({"graph_json": _make_graph_json()})
        assert result.isError

    @pytest.mark.asyncio
    async def test_find_patterns_no_match(self, tools: dict) -> None:
        """kaos-graph-find-patterns returns empty results when nothing matches."""
        tool = tools["kaos-graph-find-patterns"]
        result = await tool.execute(
            {
                "graph_json": _make_graph_json(),
                "node_filters": {"type": "nonexistent"},
            }
        )
        assert not result.isError
        assert result.structuredContent["node_count"] == 0

    # ── Stats ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_stats(self, tools: dict) -> None:
        """kaos-graph-stats computes correct statistics."""
        tool = tools["kaos-graph-stats"]
        result = await tool.execute({"graph_json": _make_graph_json()})
        assert not result.isError
        content = result.structuredContent
        assert content["node_count"] == 3
        assert content["edge_count"] == 2
        assert content["is_dag"] is True
        assert content["is_directed"] is True
        assert content["connected_components"] == 1
        assert content["max_degree"] >= 1
        assert content["density"] > 0

    @pytest.mark.asyncio
    async def test_stats_empty_graph(self, tools: dict) -> None:
        """kaos-graph-stats handles empty graph."""
        g = Graph(directed=True, name="empty")
        tool = tools["kaos-graph-stats"]
        result = await tool.execute({"graph_json": g.to_json()})
        assert not result.isError
        content = result.structuredContent
        assert content["node_count"] == 0
        assert content["edge_count"] == 0
        assert content["avg_degree"] == 0.0
        assert content["max_degree"] == 0

    @pytest.mark.asyncio
    async def test_stats_invalid_json(self, tools: dict) -> None:
        """kaos-graph-stats returns error for bad JSON."""
        tool = tools["kaos-graph-stats"]
        result = await tool.execute({"graph_json": "bad"})
        assert result.isError

    # ── Load RDF string ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_load_rdf_string_turtle(self, tools: dict) -> None:
        """kaos-graph-load-rdf-string loads Turtle data."""
        tool = tools["kaos-graph-load-rdf-string"]
        turtle_data = "<http://example.org/a> <http://example.org/knows> <http://example.org/b> .\n"
        result = await tool.execute({"rdf_data": turtle_data, "format": "turtle"})
        assert not result.isError
        assert result.structuredContent["n_nodes"] >= 2
        assert result.structuredContent["n_edges"] >= 1
        assert result.structuredContent["stats"]["total_triples"] >= 1

    @pytest.mark.asyncio
    async def test_load_rdf_string_invalid(self, tools: dict) -> None:
        """kaos-graph-load-rdf-string returns error for bad RDF data."""
        tool = tools["kaos-graph-load-rdf-string"]
        result = await tool.execute({"rdf_data": "this is not valid turtle", "format": "turtle"})
        assert result.isError

    # ── Trace to graph ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_trace_to_graph_no_llm_core(self, tools: dict) -> None:
        """kaos-graph-trace-to-graph handles missing kaos-llm-core gracefully."""
        tool = tools["kaos-graph-trace-to-graph"]
        # Even if kaos-llm-core IS installed, we test with invalid JSON
        # to verify the tool handles errors properly
        result = await tool.execute({"trace_json": "not json"})
        assert result.isError

    # ── SPARQL ───────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_sparql_invalid_graph(self, tools: dict) -> None:
        """kaos-graph-sparql returns error for bad graph JSON."""
        tool = tools["kaos-graph-sparql"]
        result = await tool.execute({"graph_json": "bad", "query": "SELECT ?s WHERE { ?s ?p ?o }"})
        assert result.isError


def test_serve_entrypoint_exists() -> None:
    """Verify the serve module's main() is importable and callable."""
    from kaos_graph.serve import main

    assert callable(main)
