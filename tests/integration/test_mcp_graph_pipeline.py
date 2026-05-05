"""Integration tests for kaos-graph MCP tools.

Exercises the full pipeline: KaosRuntime -> register_graph_tools -> tool.execute().
Uses a non-trivial test graph (organizational hierarchy + project dependencies)
to validate structural correctness of all major tool operations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from kaos_core import KaosRuntime, KaosSettings
from kaos_core.base.tool import KaosTool
from kaos_core.types.enums import StorageBackend
from kaos_core.types.results import ToolResult
from kaos_core.vfs import VFSConfig, VirtualFileSystem

from kaos_graph import Graph
from kaos_graph.tools import register_graph_tools

pytestmark = pytest.mark.integration


class _S3Stub:
    """Stub S3Backend that does not raise on init (S3 is not implemented)."""

    def __init__(self, **kwargs: object) -> None:
        pass


def _make_runtime(tmp_path: Path) -> KaosRuntime:
    """Create a KaosRuntime with disk-based VFS.

    Patches S3Backend to avoid NotImplementedError during VFS init
    (S3 is a stub; graph tools only use memory/disk).
    """
    import unittest.mock

    with unittest.mock.patch("kaos_core.vfs.core.S3Backend", _S3Stub):
        settings = KaosSettings()
        runtime = KaosRuntime(config=settings)
        runtime.vfs = VirtualFileSystem(
            VFSConfig(default_backend=StorageBackend.DISK, disk_base_path=tmp_path / "vfs")
        )
        runtime.artifacts = runtime.artifacts.__class__(
            runtime.vfs,
            manifest_context_id=settings.artifact_manifest_context_id,
            manifest_prefix=settings.artifact_manifest_prefix,
            max_inline_read_bytes=settings.artifact_inline_read_max_bytes,
            default_chunk_size=settings.artifact_chunk_size_bytes,
            temporary_ttl_seconds=settings.artifact_temporary_ttl_seconds,
        )
    return runtime


def _tool(runtime: KaosRuntime, name: str) -> KaosTool:
    tool = runtime.tools.get_tool(name)
    assert tool is not None
    return tool


def _structured(result: ToolResult) -> dict[str, Any]:
    structured = result.structuredContent
    assert structured is not None
    return structured


# ---------------------------------------------------------------------------
# Test graph definitions
# ---------------------------------------------------------------------------

# An organizational graph: 7 nodes (people), 8 directed edges (reports-to + collaborates).
# This is a DAG with properties on nodes and edges, suitable for centrality,
# path-finding, community detection, and schema validation.
_ORG_NODES: list[dict[str, str | float]] = [
    {"id": "ceo", "type": "person", "role": "CEO", "department": "exec", "latency_ms": 100.0},
    {"id": "vp_eng", "type": "person", "role": "VP", "department": "eng", "latency_ms": 50.0},
    {
        "id": "vp_sales",
        "type": "person",
        "role": "VP",
        "department": "sales",
        "latency_ms": 40.0,
    },
    {"id": "lead_a", "type": "person", "role": "lead", "department": "eng", "latency_ms": 30.0},
    {"id": "lead_b", "type": "person", "role": "lead", "department": "eng", "latency_ms": 35.0},
    {"id": "dev_1", "type": "person", "role": "dev", "department": "eng", "latency_ms": 20.0},
    {"id": "dev_2", "type": "person", "role": "dev", "department": "eng", "latency_ms": 25.0},
]

_ORG_EDGES: list[dict[str, str | float]] = [
    {"source": "ceo", "target": "vp_eng", "type": "manages", "weight": 1.0},
    {"source": "ceo", "target": "vp_sales", "type": "manages", "weight": 1.0},
    {"source": "vp_eng", "target": "lead_a", "type": "manages", "weight": 1.0},
    {"source": "vp_eng", "target": "lead_b", "type": "manages", "weight": 1.0},
    {"source": "lead_a", "target": "dev_1", "type": "manages", "weight": 1.0},
    {"source": "lead_a", "target": "dev_2", "type": "manages", "weight": 1.0},
    {"source": "lead_b", "target": "dev_2", "type": "collaborates", "weight": 0.5},
    {"source": "dev_1", "target": "dev_2", "type": "collaborates", "weight": 0.3},
]

_ORG_GRAPH_DEFINITION = {
    "name": "org_chart",
    "directed": True,
    "nodes": _ORG_NODES,
    "edges": _ORG_EDGES,
}

_ORG_GRAPH_JSON = json.dumps(_ORG_GRAPH_DEFINITION)


def _make_dag_with_weights() -> str:
    """Build a pipeline DAG with latency_ms properties for critical path tests."""
    g = Graph(directed=True, name="pipeline")
    g.add_node("ingest", latency_ms=10.0, stage="input")
    g.add_node("parse", latency_ms=50.0, stage="transform")
    g.add_node("validate", latency_ms=30.0, stage="transform")
    g.add_node("enrich", latency_ms=80.0, stage="transform")
    g.add_node("store", latency_ms=15.0, stage="output")
    g.add_edge("ingest", "parse")
    g.add_edge("ingest", "validate")
    g.add_edge("parse", "enrich")
    g.add_edge("validate", "enrich")
    g.add_edge("enrich", "store")
    return g.to_json()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runtime(tmp_path: Path) -> KaosRuntime:
    """Fresh KaosRuntime with graph tools registered."""
    rt = _make_runtime(tmp_path)
    count = register_graph_tools(rt)
    assert count == 17, f"Expected 17 tools registered, got {count}"
    return rt


@pytest.fixture
def graph_data(runtime: KaosRuntime) -> str:
    """Create an org-chart graph via the create tool and return its graph_data JSON.

    This fixture is sync; it builds the graph directly from the Graph API
    (the create tool is tested separately in TestCreateGraph).
    """
    g = Graph(directed=True, name="org_chart")
    for node_def in _ORG_NODES:
        nid = cast(str, node_def["id"])
        props = {k: v for k, v in node_def.items() if k != "id"}
        g.add_node(nid, **props)
    for edge_def in _ORG_EDGES:
        src = cast(str, edge_def["source"])
        tgt = cast(str, edge_def["target"])
        props = {k: v for k, v in edge_def.items() if k not in ("source", "target")}
        g.add_edge(src, tgt, **props)
    return g.to_json()


# ---------------------------------------------------------------------------
# 1. Create graph
# ---------------------------------------------------------------------------


class TestCreateGraph:
    async def test_create_from_json_definition(self, runtime: KaosRuntime) -> None:
        """Create a graph from a JSON definition and verify node/edge counts."""
        tool = _tool(runtime, "kaos-graph-create")
        result = await tool.execute({"graph_json": _ORG_GRAPH_JSON})

        assert not result.isError
        sc = _structured(result)
        assert sc["name"] == "org_chart"
        assert sc["n_nodes"] == 7
        assert sc["n_edges"] == 8
        assert sc["is_directed"] is True
        # graph_data should be valid JSON that round-trips
        roundtrip = Graph.from_json(sc["graph_data"])
        assert roundtrip.n_nodes == 7
        assert roundtrip.n_edges == 8

    async def test_create_preserves_node_properties(self, runtime: KaosRuntime) -> None:
        """Node properties from the JSON definition survive serialization."""
        create_tool = _tool(runtime, "kaos-graph-create")
        result = await create_tool.execute({"graph_json": _ORG_GRAPH_JSON})
        assert not result.isError

        g = Graph.from_json(_structured(result)["graph_data"])
        ceo = g.node("ceo")
        assert ceo is not None
        assert ceo.properties["role"] == "CEO"
        assert ceo.properties["department"] == "exec"

    async def test_create_invalid_json_returns_error(self, runtime: KaosRuntime) -> None:
        """Invalid JSON input produces a helpful error, not a crash."""
        tool = _tool(runtime, "kaos-graph-create")
        result = await tool.execute({"graph_json": "{broken"})
        assert result.isError
        assert "Invalid graph JSON" in (result.text or "")


# ---------------------------------------------------------------------------
# 2. Graph info / statistics
# ---------------------------------------------------------------------------


class TestGraphInfo:
    async def test_info_returns_structural_properties(
        self, runtime: KaosRuntime, graph_data: str
    ) -> None:
        """kaos-graph-info returns correct structural properties."""
        tool = _tool(runtime, "kaos-graph-info")
        result = await tool.execute({"graph_json": graph_data})

        assert not result.isError
        sc = _structured(result)
        assert sc["n_nodes"] == 7
        assert sc["n_edges"] == 8
        assert sc["is_directed"] is True
        # The org chart is NOT a DAG due to dev_1 -> dev_2 AND lead_b -> dev_2
        # but all edges flow downward, so it IS a DAG
        assert sc["is_dag"] is True
        assert sc["is_connected"] is True
        assert isinstance(sc["density"], float)
        assert 0 < sc["density"] < 1

    async def test_stats_returns_degree_metrics(
        self, runtime: KaosRuntime, graph_data: str
    ) -> None:
        """kaos-graph-stats returns correct degree statistics."""
        tool = _tool(runtime, "kaos-graph-stats")
        result = await tool.execute({"graph_json": graph_data})

        assert not result.isError
        sc = _structured(result)
        assert sc["node_count"] == 7
        assert sc["edge_count"] == 8
        assert sc["is_dag"] is True
        assert sc["is_directed"] is True
        assert sc["connected_components"] == 1
        # dev_2 has 3 inbound edges (lead_a, lead_b, dev_1) = degree 3
        # lead_a and vp_eng also have degree 3
        assert sc["max_degree"] >= 3
        assert sc["avg_degree"] > 0
        assert isinstance(sc["density"], float)
        assert 0 < sc["density"] < 1


# ---------------------------------------------------------------------------
# 3. Query tool
# ---------------------------------------------------------------------------


class TestQueryTool:
    async def test_query_node_properties(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Query a specific node and verify its properties."""
        tool = _tool(runtime, "kaos-graph-query")
        result = await tool.execute(
            {"graph_json": graph_data, "node_id": "vp_eng", "query_type": "node"}
        )

        assert not result.isError
        sc = _structured(result)
        assert sc["node_id"] == "vp_eng"
        assert sc["properties"]["role"] == "VP"
        assert sc["properties"]["department"] == "eng"
        assert sc["degree"] >= 3  # in from ceo, out to lead_a, lead_b

    async def test_query_successors(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Query successors of a node."""
        tool = _tool(runtime, "kaos-graph-query")
        result = await tool.execute(
            {"graph_json": graph_data, "node_id": "vp_eng", "query_type": "successors"}
        )

        assert not result.isError
        sc = _structured(result)
        assert set(sc["successors"]) == {"lead_a", "lead_b"}
        assert sc["count"] == 2

    async def test_query_predecessors(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Query predecessors of a node."""
        tool = _tool(runtime, "kaos-graph-query")
        result = await tool.execute(
            {"graph_json": graph_data, "node_id": "dev_2", "query_type": "predecessors"}
        )

        assert not result.isError
        sc = _structured(result)
        # dev_2 receives edges from lead_a, lead_b, and dev_1
        assert set(sc["predecessors"]) == {"lead_a", "lead_b", "dev_1"}
        assert sc["count"] == 3

    async def test_query_neighbors(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Query all neighbors (both directions)."""
        tool = _tool(runtime, "kaos-graph-query")
        result = await tool.execute(
            {"graph_json": graph_data, "node_id": "lead_a", "query_type": "neighbors"}
        )

        assert not result.isError
        sc = _structured(result)
        # lead_a: in from vp_eng, out to dev_1 and dev_2
        assert "vp_eng" in sc["neighbors"]
        assert "dev_1" in sc["neighbors"]
        assert "dev_2" in sc["neighbors"]

    async def test_query_missing_node_returns_error(
        self, runtime: KaosRuntime, graph_data: str
    ) -> None:
        """Querying a non-existent node returns a helpful error."""
        tool = _tool(runtime, "kaos-graph-query")
        result = await tool.execute({"graph_json": graph_data, "node_id": "nonexistent"})
        assert result.isError
        assert "not found" in (result.text or "").lower()


# ---------------------------------------------------------------------------
# 4. Algorithms
# ---------------------------------------------------------------------------


class TestAlgorithms:
    async def test_pagerank(self, runtime: KaosRuntime, graph_data: str) -> None:
        """PageRank identifies dev_2 as highest-ranked (most inbound edges)."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute({"graph_json": graph_data, "algorithm": "pagerank"})

        assert not result.isError
        sc = _structured(result)
        assert sc["algorithm"] == "pagerank"
        assert sc["total"] == 7
        results = sc["results"]
        assert len(results) == 7
        # All scores should be positive floats
        for r in results:
            assert isinstance(r["score"], float)
            assert r["score"] > 0
        # dev_2 has the most inbound edges (3), so it should be top-ranked
        assert results[0]["node_id"] == "dev_2"

    async def test_shortest_path(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Shortest path from ceo to dev_1."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute(
            {
                "graph_json": graph_data,
                "algorithm": "shortest_path",
                "source": "ceo",
                "target": "dev_1",
            }
        )

        assert not result.isError
        sc = _structured(result)
        assert sc["algorithm"] == "shortest_path"
        assert sc["reachable"] is True
        assert sc["path"][0] == "ceo"
        assert sc["path"][-1] == "dev_1"
        # The path should go ceo -> vp_eng -> lead_a -> dev_1 (3 hops)
        assert len(sc["path"]) == 4
        assert sc["path"] == ["ceo", "vp_eng", "lead_a", "dev_1"]
        assert isinstance(sc["cost"], (int, float))

    async def test_shortest_path_unreachable(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Shortest path returns not-reachable for reversed direction."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute(
            {
                "graph_json": graph_data,
                "algorithm": "shortest_path",
                "source": "dev_1",
                "target": "ceo",
            }
        )

        assert not result.isError
        sc = _structured(result)
        assert sc["reachable"] is False

    async def test_bfs_traversal(self, runtime: KaosRuntime, graph_data: str) -> None:
        """BFS from ceo visits all 7 nodes."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute({"graph_json": graph_data, "algorithm": "bfs", "source": "ceo"})

        assert not result.isError
        sc = _structured(result)
        assert sc["algorithm"] == "bfs"
        order = sc["order"]
        assert len(order) == 7
        # ceo must be first in BFS
        assert order[0] == "ceo"
        # All nodes must be visited
        assert set(order) == {"ceo", "vp_eng", "vp_sales", "lead_a", "lead_b", "dev_1", "dev_2"}

    async def test_dfs_traversal(self, runtime: KaosRuntime, graph_data: str) -> None:
        """DFS from ceo visits all 7 nodes."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute({"graph_json": graph_data, "algorithm": "dfs", "source": "ceo"})

        assert not result.isError
        sc = _structured(result)
        assert sc["algorithm"] == "dfs"
        order = sc["order"]
        assert len(order) == 7
        assert order[0] == "ceo"
        assert set(order) == {"ceo", "vp_eng", "vp_sales", "lead_a", "lead_b", "dev_1", "dev_2"}

    async def test_topological_sort(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Topological sort on DAG: ceo comes before all, leaves come last."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute({"graph_json": graph_data, "algorithm": "topological_sort"})

        assert not result.isError
        sc = _structured(result)
        order = sc["order"]
        assert len(order) == 7
        # ceo has no predecessors, so it must come first
        assert order.index("ceo") < order.index("vp_eng")
        assert order.index("vp_eng") < order.index("lead_a")
        assert order.index("lead_a") < order.index("dev_1")

    async def test_scc(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Strongly connected components: each node is its own SCC in a DAG."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute({"graph_json": graph_data, "algorithm": "scc"})

        assert not result.isError
        sc = _structured(result)
        assert sc["count"] == 7  # DAG: every node is its own SCC

    async def test_betweenness_centrality(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Betweenness centrality returns scores for all nodes."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute(
            {"graph_json": graph_data, "algorithm": "betweenness_centrality"}
        )

        assert not result.isError
        sc = _structured(result)
        assert sc["algorithm"] == "betweenness_centrality"
        assert sc["total"] == 7
        results = sc["results"]
        for r in results:
            assert isinstance(r["score"], float)
            assert r["score"] >= 0

    async def test_degree_centrality(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Degree centrality returns scores for all nodes."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute({"graph_json": graph_data, "algorithm": "degree_centrality"})

        assert not result.isError
        sc = _structured(result)
        assert sc["algorithm"] == "degree_centrality"
        assert sc["total"] == 7
        # All nodes should have positive degree centrality
        for r in sc["results"]:
            assert r["score"] > 0

    async def test_closeness_centrality(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Closeness centrality returns scores for all nodes."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute({"graph_json": graph_data, "algorithm": "closeness_centrality"})

        assert not result.isError
        sc = _structured(result)
        assert sc["algorithm"] == "closeness_centrality"
        assert sc["total"] == 7

    async def test_eigenvector_centrality(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Eigenvector centrality returns scores for all nodes."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute(
            {"graph_json": graph_data, "algorithm": "eigenvector_centrality"}
        )

        assert not result.isError
        sc = _structured(result)
        assert sc["algorithm"] == "eigenvector_centrality"
        assert sc["total"] == 7

    async def test_louvain_communities(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Louvain community detection returns at least 1 community."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute({"graph_json": graph_data, "algorithm": "louvain"})

        assert not result.isError
        sc = _structured(result)
        assert sc["algorithm"] == "louvain"
        assert sc["count"] >= 1
        # All 7 nodes should be in some community
        all_nodes = set()
        for community in sc["communities"]:
            all_nodes.update(community)
        assert len(all_nodes) == 7

    async def test_label_propagation(self, runtime: KaosRuntime) -> None:
        """Label propagation on an undirected graph returns communities covering all nodes.

        Note: label_propagation can loop indefinitely on directed graphs where
        consensus is unreachable, so we test with an undirected graph.
        """
        g = Graph(directed=False, name="undirected_social")
        for nid in ["a", "b", "c", "d", "e"]:
            g.add_node(nid)
        # Two clusters connected by a bridge
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("a", "c")
        g.add_edge("d", "e")
        g.add_edge("c", "d")  # bridge
        undirected_json = g.to_json()

        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute(
            {"graph_json": undirected_json, "algorithm": "label_propagation"}
        )

        assert not result.isError
        sc = _structured(result)
        assert sc["algorithm"] == "label_propagation"
        assert sc["count"] >= 1
        all_nodes = set()
        for community in sc["communities"]:
            all_nodes.update(community)
        assert len(all_nodes) == 5

    async def test_longest_path(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Longest path in the DAG."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute({"graph_json": graph_data, "algorithm": "longest_path"})

        assert not result.isError
        sc = _structured(result)
        assert sc["algorithm"] == "longest_path"
        # Longest path: ceo -> vp_eng -> lead_a -> dev_1 -> dev_2 (length 4)
        # or ceo -> vp_eng -> lead_a -> dev_2 (length 3)
        # The actual longest is 4 edges: ceo->vp_eng->lead_a->dev_1->dev_2
        assert sc["length"] >= 3
        assert len(sc["path"]) >= 4

    async def test_ancestors(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Ancestors of dev_2 include all upstream nodes."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute(
            {"graph_json": graph_data, "algorithm": "ancestors", "source": "dev_2"}
        )

        assert not result.isError
        sc = _structured(result)
        assert sc["algorithm"] == "ancestors"
        # dev_2 ancestors: lead_a, lead_b, dev_1, vp_eng, ceo
        ancestors = set(sc["ancestors"])
        assert "ceo" in ancestors
        assert "vp_eng" in ancestors
        assert "lead_a" in ancestors

    async def test_descendants(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Descendants of ceo include all nodes below."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute(
            {"graph_json": graph_data, "algorithm": "descendants", "source": "ceo"}
        )

        assert not result.isError
        sc = _structured(result)
        assert sc["algorithm"] == "descendants"
        descendants = set(sc["descendants"])
        assert len(descendants) == 6  # everyone except ceo
        assert "ceo" not in descendants

    async def test_shortest_path_missing_params(
        self, runtime: KaosRuntime, graph_data: str
    ) -> None:
        """shortest_path without source/target returns error."""
        tool = _tool(runtime, "kaos-graph-algorithm")
        result = await tool.execute(
            {"graph_json": graph_data, "algorithm": "shortest_path", "source": "ceo"}
        )
        assert result.isError
        assert "target" in (result.text or "").lower()


# ---------------------------------------------------------------------------
# 5. Export
# ---------------------------------------------------------------------------


class TestExport:
    async def test_export_json(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Export to JSON produces valid, parseable JSON with graph structure."""
        tool = _tool(runtime, "kaos-graph-export")
        result = await tool.execute({"graph_json": graph_data, "format": "json"})

        assert not result.isError
        parsed = json.loads(result.text or "")
        # Should contain nodes and edges or be a valid graph structure
        assert isinstance(parsed, dict)

    async def test_export_mermaid(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Export to Mermaid produces a flowchart with node references."""
        tool = _tool(runtime, "kaos-graph-export")
        result = await tool.execute({"graph_json": graph_data, "format": "mermaid"})

        assert not result.isError
        text = result.text or ""
        assert "flowchart" in text or "graph" in text
        assert "ceo" in text
        assert "vp_eng" in text

    async def test_export_dot(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Export to DOT produces a digraph with node references."""
        tool = _tool(runtime, "kaos-graph-export")
        result = await tool.execute({"graph_json": graph_data, "format": "dot"})

        assert not result.isError
        text = result.text or ""
        assert "digraph" in text
        assert "ceo" in text

    async def test_export_graphml(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Export to GraphML produces valid XML."""
        tool = _tool(runtime, "kaos-graph-export")
        result = await tool.execute({"graph_json": graph_data, "format": "graphml"})

        assert not result.isError
        text = result.text or ""
        assert "<graphml" in text or "graphml" in text.lower()

    async def test_export_gexf(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Export to GEXF produces valid XML."""
        tool = _tool(runtime, "kaos-graph-export")
        result = await tool.execute({"graph_json": graph_data, "format": "gexf"})

        assert not result.isError
        text = result.text or ""
        assert "<gexf" in text or "gexf" in text.lower()

    async def test_export_adjacency_roundtrip(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Export to adjacency JSON and re-import: node/edge counts match."""
        export_tool = _tool(runtime, "kaos-graph-export-adjacency")
        load_tool = _tool(runtime, "kaos-graph-load-adjacency")

        export_result = await export_tool.execute({"graph_json": graph_data})
        assert not export_result.isError

        adjacency_str = export_result.text or ""
        load_result = await load_tool.execute({"adjacency_json": adjacency_str})
        assert not load_result.isError
        load_sc = _structured(load_result)
        assert load_sc["n_nodes"] == 7
        assert load_sc["n_edges"] == 8


# ---------------------------------------------------------------------------
# 6. Visualize
# ---------------------------------------------------------------------------


class TestVisualize:
    async def test_visualize_default(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Visualize produces Mermaid output with all nodes."""
        tool = _tool(runtime, "kaos-graph-visualize")
        result = await tool.execute({"graph_json": graph_data})

        assert not result.isError
        text = result.text or ""
        assert "flowchart" in text
        assert "ceo" in text

    async def test_visualize_with_direction(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Visualize respects the direction parameter."""
        tool = _tool(runtime, "kaos-graph-visualize")
        result = await tool.execute({"graph_json": graph_data, "direction": "LR"})

        assert not result.isError
        text = result.text or ""
        assert "LR" in text


# ---------------------------------------------------------------------------
# 7. Transform
# ---------------------------------------------------------------------------


class TestTransform:
    async def test_subgraph_extraction(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Extract a subgraph and verify only requested nodes + internal edges."""
        tool = _tool(runtime, "kaos-graph-transform")
        result = await tool.execute(
            {
                "graph_json": graph_data,
                "operation": "subgraph",
                "nodes": ["vp_eng", "lead_a", "lead_b"],
            }
        )

        assert not result.isError
        sc = _structured(result)
        assert sc["n_nodes"] == 3
        # Only internal edges: vp_eng->lead_a and vp_eng->lead_b
        assert sc["n_edges"] == 2

    async def test_ego_graph(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Ego graph around lead_a with radius=1 includes neighbors."""
        tool = _tool(runtime, "kaos-graph-transform")
        result = await tool.execute(
            {
                "graph_json": graph_data,
                "operation": "ego_graph",
                "center": "lead_a",
                "radius": 1,
            }
        )

        assert not result.isError
        sc = _structured(result)
        # lead_a neighbors: vp_eng (in), dev_1 (out), dev_2 (out) + lead_a itself
        assert sc["n_nodes"] == 4
        # Verify the subgraph is valid
        sub_g = Graph.from_json(sc["graph_data"])
        assert sub_g.has_node("lead_a")
        assert sub_g.has_node("vp_eng")
        assert sub_g.has_node("dev_1")
        assert sub_g.has_node("dev_2")

    async def test_reverse(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Reverse flips all edge directions."""
        tool = _tool(runtime, "kaos-graph-transform")
        result = await tool.execute({"graph_json": graph_data, "operation": "reverse"})

        assert not result.isError
        sc = _structured(result)
        assert sc["n_nodes"] == 7
        assert sc["n_edges"] == 8
        # Verify an edge is reversed: ceo->vp_eng becomes vp_eng->ceo
        reversed_g = Graph.from_json(sc["graph_data"])
        assert reversed_g.has_edge("vp_eng", "ceo")
        assert not reversed_g.has_edge("ceo", "vp_eng")

    async def test_to_undirected(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Converting to undirected preserves connectivity."""
        tool = _tool(runtime, "kaos-graph-transform")
        result = await tool.execute({"graph_json": graph_data, "operation": "to_undirected"})

        assert not result.isError
        sc = _structured(result)
        assert sc["n_nodes"] == 7
        assert sc["is_directed"] is False
        # Undirected should have at least as many edges
        assert sc["n_edges"] >= 8

    async def test_condensation(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Condensation of a DAG: each node becomes its own SCC."""
        tool = _tool(runtime, "kaos-graph-transform")
        result = await tool.execute({"graph_json": graph_data, "operation": "condensation"})

        assert not result.isError
        sc = _structured(result)
        # DAG condensation: n SCCs = n nodes
        assert sc["n_nodes"] == 7


# ---------------------------------------------------------------------------
# 8. Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    async def test_valid_schema(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Graph validates against a matching schema."""
        tool = _tool(runtime, "kaos-graph-validate-schema")
        schema = json.dumps(
            {
                "node_types": [
                    {"name": "person", "required_properties": ["role", "department"]},
                ],
                "edge_types": [
                    {"name": "manages", "source_type": "person", "target_type": "person"},
                    {"name": "collaborates", "source_type": "person", "target_type": "person"},
                ],
            }
        )
        result = await tool.execute({"graph_json": graph_data, "schema_json": schema})

        assert not result.isError
        sc = _structured(result)
        assert sc["valid"] is True
        assert sc["violation_count"] == 0

    async def test_schema_violations(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Schema validation finds missing required properties."""
        tool = _tool(runtime, "kaos-graph-validate-schema")
        schema = json.dumps(
            {
                "node_types": [
                    {
                        "name": "person",
                        "required_properties": ["role", "department", "email"],
                    },
                ],
            }
        )
        result = await tool.execute({"graph_json": graph_data, "schema_json": schema})

        assert not result.isError
        sc = _structured(result)
        assert sc["valid"] is False
        assert sc["violation_count"] > 0
        # All violations should be about missing 'email'
        for v in sc["violations"]:
            assert "email" in v["message"]
            assert v["kind"] == "missing_property"


# ---------------------------------------------------------------------------
# 9. Find patterns
# ---------------------------------------------------------------------------


class TestFindPatterns:
    async def test_find_nodes_by_department(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Find all engineering department nodes."""
        tool = _tool(runtime, "kaos-graph-find-patterns")
        result = await tool.execute(
            {"graph_json": graph_data, "node_filters": {"department": "eng"}}
        )

        assert not result.isError
        sc = _structured(result)
        # eng department: vp_eng, lead_a, lead_b, dev_1, dev_2
        assert sc["node_count"] == 5
        assert set(sc["matching_nodes"]) == {"vp_eng", "lead_a", "lead_b", "dev_1", "dev_2"}

    async def test_find_nodes_by_role(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Find all nodes with role=lead."""
        tool = _tool(runtime, "kaos-graph-find-patterns")
        result = await tool.execute({"graph_json": graph_data, "node_filters": {"role": "lead"}})

        assert not result.isError
        sc = _structured(result)
        assert sc["node_count"] == 2
        assert set(sc["matching_nodes"]) == {"lead_a", "lead_b"}

    async def test_find_edges_by_type(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Find all 'collaborates' edges."""
        tool = _tool(runtime, "kaos-graph-find-patterns")
        result = await tool.execute(
            {"graph_json": graph_data, "edge_filters": {"type": "collaborates"}}
        )

        assert not result.isError
        sc = _structured(result)
        assert sc["edge_count"] == 2
        edges = sc["matching_edges"]
        targets = {e["target"] for e in edges}
        assert "dev_2" in targets

    async def test_find_nodes_and_edges_combined(
        self, runtime: KaosRuntime, graph_data: str
    ) -> None:
        """Find nodes and edges simultaneously."""
        tool = _tool(runtime, "kaos-graph-find-patterns")
        result = await tool.execute(
            {
                "graph_json": graph_data,
                "node_filters": {"role": "VP"},
                "edge_filters": {"type": "manages"},
            }
        )

        assert not result.isError
        sc = _structured(result)
        assert sc["node_count"] == 2  # vp_eng, vp_sales
        assert sc["edge_count"] == 6  # all 'manages' edges


# ---------------------------------------------------------------------------
# 10. Critical path
# ---------------------------------------------------------------------------


class TestCriticalPath:
    async def test_critical_path_pipeline(self, runtime: KaosRuntime) -> None:
        """Critical path through a pipeline DAG with latency weights."""
        tool = _tool(runtime, "kaos-graph-critical-path")
        result = await tool.execute({"graph_json": _make_dag_with_weights()})

        assert not result.isError
        sc = _structured(result)
        assert sc["weight_key"] == "latency_ms"
        # Critical path: ingest(10) -> parse(50) -> enrich(80) -> store(15) = 155
        # or ingest(10) -> validate(30) -> enrich(80) -> store(15) = 135
        # So critical path should be through parse
        assert sc["total_cost"] == 155.0
        assert sc["path"] == ["ingest", "parse", "enrich", "store"]
        assert sc["path_length"] == 4

    async def test_critical_path_org_chart(self, runtime: KaosRuntime, graph_data: str) -> None:
        """Critical path through the org chart DAG."""
        tool = _tool(runtime, "kaos-graph-critical-path")
        result = await tool.execute({"graph_json": graph_data})

        assert not result.isError
        sc = _structured(result)
        assert sc["weight_key"] == "latency_ms"
        assert sc["total_cost"] > 0
        assert len(sc["path"]) >= 2
        # Path should start from ceo (highest aggregate weight upstream)
        assert sc["path"][0] == "ceo"

    async def test_critical_path_cyclic_graph_returns_error(self, runtime: KaosRuntime) -> None:
        """Critical path on a cyclic graph returns error."""
        g = Graph(directed=True, name="cycle")
        g.add_node("a", latency_ms=10.0)
        g.add_node("b", latency_ms=20.0)
        g.add_edge("a", "b")
        g.add_edge("b", "a")

        tool = _tool(runtime, "kaos-graph-critical-path")
        result = await tool.execute({"graph_json": g.to_json()})
        assert result.isError


# ---------------------------------------------------------------------------
# 11. RDF string loading
# ---------------------------------------------------------------------------


class TestLoadRdfString:
    async def test_load_turtle_string(self, runtime: KaosRuntime) -> None:
        """Load an RDF Turtle string and verify graph structure."""
        turtle_data = (
            "@prefix ex: <http://example.org/> .\n"
            "ex:Alice ex:knows ex:Bob .\n"
            "ex:Bob ex:knows ex:Charlie .\n"
            "ex:Alice ex:likes ex:Charlie .\n"
        )
        tool = _tool(runtime, "kaos-graph-load-rdf-string")
        result = await tool.execute({"rdf_data": turtle_data, "format": "turtle"})

        assert not result.isError
        sc = _structured(result)
        assert sc["n_nodes"] >= 3
        assert sc["n_edges"] >= 3
        assert sc["stats"]["total_triples"] >= 3

    async def test_load_ntriples_string(self, runtime: KaosRuntime) -> None:
        """Load N-Triples format."""
        ntriples = (
            "<http://example.org/Alice> <http://example.org/knows> <http://example.org/Bob> .\n"
            "<http://example.org/Bob> <http://example.org/knows> <http://example.org/Charlie> .\n"
        )
        tool = _tool(runtime, "kaos-graph-load-rdf-string")
        result = await tool.execute({"rdf_data": ntriples, "format": "ntriples"})

        assert not result.isError
        sc = _structured(result)
        assert sc["n_nodes"] >= 2
        assert sc["n_edges"] >= 2


# ---------------------------------------------------------------------------
# 12. End-to-end pipeline: create -> algorithm -> transform -> export
# ---------------------------------------------------------------------------


class TestEndToEndPipeline:
    async def test_create_analyze_transform_export(self, runtime: KaosRuntime) -> None:
        """Full pipeline: create graph, run PageRank, extract subgraph, export."""
        # Step 1: Create graph
        create_tool = _tool(runtime, "kaos-graph-create")
        create_result = await create_tool.execute({"graph_json": _ORG_GRAPH_JSON})
        assert not create_result.isError
        create_sc = _structured(create_result)
        gdata = create_sc["graph_data"]

        # Step 2: Run PageRank to find top nodes
        algo_tool = _tool(runtime, "kaos-graph-algorithm")
        pr_result = await algo_tool.execute({"graph_json": gdata, "algorithm": "pagerank"})
        assert not pr_result.isError
        pr_sc = _structured(pr_result)
        top_nodes = [r["node_id"] for r in pr_sc["results"][:3]]
        assert len(top_nodes) == 3

        # Step 3: Extract subgraph of top-3 nodes
        transform_tool = _tool(runtime, "kaos-graph-transform")
        sub_result = await transform_tool.execute(
            {"graph_json": gdata, "operation": "subgraph", "nodes": top_nodes}
        )
        assert not sub_result.isError
        sub_sc = _structured(sub_result)
        sub_data = sub_sc["graph_data"]
        assert sub_sc["n_nodes"] == 3

        # Step 4: Get info on subgraph
        info_tool = _tool(runtime, "kaos-graph-info")
        info_result = await info_tool.execute({"graph_json": sub_data})
        assert not info_result.isError
        assert _structured(info_result)["n_nodes"] == 3

        # Step 5: Export subgraph to Mermaid
        export_tool = _tool(runtime, "kaos-graph-export")
        export_result = await export_tool.execute({"graph_json": sub_data, "format": "mermaid"})
        assert not export_result.isError
        assert "flowchart" in (export_result.text or "")

    async def test_create_stats_find_patterns(self, runtime: KaosRuntime) -> None:
        """Pipeline: create -> stats -> find patterns -> query specific node."""
        # Create
        create_tool = _tool(runtime, "kaos-graph-create")
        create_result = await create_tool.execute({"graph_json": _ORG_GRAPH_JSON})
        assert not create_result.isError
        gdata = _structured(create_result)["graph_data"]

        # Stats
        stats_tool = _tool(runtime, "kaos-graph-stats")
        stats_result = await stats_tool.execute({"graph_json": gdata})
        assert not stats_result.isError
        assert _structured(stats_result)["node_count"] == 7

        # Find all leads
        pattern_tool = _tool(runtime, "kaos-graph-find-patterns")
        pattern_result = await pattern_tool.execute(
            {"graph_json": gdata, "node_filters": {"role": "lead"}}
        )
        assert not pattern_result.isError
        leads = _structured(pattern_result)["matching_nodes"]
        assert len(leads) == 2

        # Query the first lead's neighbors
        query_tool = _tool(runtime, "kaos-graph-query")
        query_result = await query_tool.execute(
            {"graph_json": gdata, "node_id": leads[0], "query_type": "neighbors"}
        )
        assert not query_result.isError
        assert _structured(query_result)["count"] >= 2
