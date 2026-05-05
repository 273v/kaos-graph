"""High-level Graph class wrapping the Rust PyGraph."""

from __future__ import annotations

from typing import Any

from kaos_graph._rust.graph import PyGraph
from kaos_graph.types import Edge, Node

__all__ = ["Graph"]


# Conservative defaults used when no KaosGraphSettings is supplied. They cap
# memory growth from a single ``Graph.from_json(str)`` call without preventing
# legitimate scientific workloads. MCP/runtime callers override via settings.
_DEFAULT_MAX_BYTES = 64 * 1024 * 1024  # 64 MiB
_DEFAULT_MAX_NODES = 1_000_000
_DEFAULT_MAX_EDGES = 10_000_000


def _resolve_graph_caps(settings: Any) -> tuple[int, int, int]:
    """Pull (max_bytes, max_nodes, max_edges) from a settings-like object."""
    if settings is None:
        return (_DEFAULT_MAX_BYTES, _DEFAULT_MAX_NODES, _DEFAULT_MAX_EDGES)
    return (
        int(getattr(settings, "max_bytes", _DEFAULT_MAX_BYTES)),
        int(getattr(settings, "max_nodes", _DEFAULT_MAX_NODES)),
        int(getattr(settings, "max_edges", _DEFAULT_MAX_EDGES)),
    )


class Graph:
    """A property graph backed by petgraph's StableDiGraph.

    Nodes have string IDs and arbitrary JSON-compatible properties.
    Edges have arbitrary JSON-compatible properties.
    """

    __slots__ = ("_inner",)

    def __init__(self, directed: bool = True, name: str | None = None, multi: bool = False) -> None:
        self._inner = PyGraph(directed=directed, name=name, multi=multi)

    @classmethod
    def _from_inner(cls, inner: PyGraph) -> Graph:
        g = cls.__new__(cls)
        g._inner = inner
        return g

    # --- Mutation ---

    def add_node(self, id: str, **properties: Any) -> None:
        """Add a node with the given ID and optional keyword properties."""
        self._inner.add_node(id, properties if properties else None)

    def add_edge(self, source: str, target: str, **properties: Any) -> None:
        """Add an edge from source to target with optional keyword properties."""
        self._inner.add_edge(source, target, properties if properties else None)

    def remove_node(self, id: str) -> Node:
        """Remove a node and all incident edges. Returns the removed Node."""
        props = self._inner.remove_node(id)
        return Node(id=id, properties=props)

    def remove_edge(self, source: str, target: str) -> None:
        """Remove an edge."""
        self._inner.remove_edge(source, target)

    def update_node(self, id: str, **properties: Any) -> None:
        """Merge properties into an existing node.

        Existing properties are preserved unless overwritten by the new values.
        Raises KeyError if the node does not exist.
        """
        self._inner.update_node(id, properties if properties else None)

    def set_node_property(self, id: str, key: str, value: Any) -> None:
        """Set a single property on an existing node.

        Raises KeyError if the node does not exist.
        """
        self._inner.set_node_property(id, key, value)

    # --- Query ---

    def node(self, id: str) -> Node | None:
        """Get a Node, or None if not found."""
        props = self._inner.node(id)
        if props is None:
            return None
        return Node(id=id, properties=props)

    def node_ids(self) -> list[str]:
        """List all node IDs."""
        return self._inner.node_ids()

    def nodes(self, **filter: Any) -> list[str]:
        """List node IDs, optionally filtered by property key=value.

        With no filter kwargs, returns all node IDs (same as ``node_ids()``).
        With filter kwargs, returns nodes where *all* specified properties match
        (AND semantics). Once the running intersection is empty we short-circuit
        and skip the remaining ``nodes_filtered`` calls — without this, a long
        filter dict against a sparse graph is O(N·k) per call (audit A2-#11).
        """
        if not filter:
            return self._inner.node_ids()
        result_set: set[str] | None = None
        for key, value in filter.items():
            matching = set(self._inner.nodes_filtered(key, value))
            if result_set is None:
                result_set = matching
            else:
                result_set &= matching
            if not result_set:
                # Empty intersection — every subsequent filter would AND to zero.
                return []
        return sorted(result_set) if result_set is not None else []

    def edges(self, **filter: Any) -> list[Edge]:
        """List edges as Edge objects.

        With no filter kwargs, returns all edges.
        With filter kwargs, returns edges where *all* specified properties match.
        Each edge is checked individually — parallel edges in multigraphs are
        handled correctly.
        """
        if not filter:
            return [Edge(source=s, target=t, properties=p) for s, t, p in self._inner.edges()]
        # Check each edge against ALL filter conditions.
        result = []
        for src, tgt, props in self._inner.edges():
            if all(props.get(k) == v for k, v in filter.items()):
                result.append(Edge(source=src, target=tgt, properties=props))
        return result

    def successors(self, id: str) -> list[str]:
        """Outgoing neighbors."""
        return self._inner.successors(id)

    def predecessors(self, id: str) -> list[str]:
        """Incoming neighbors."""
        return self._inner.predecessors(id)

    def neighbors(self, id: str) -> list[str]:
        """All neighbors (both directions for directed graphs)."""
        return self._inner.neighbors(id)

    def degree(self, id: str) -> int:
        """Degree of a node."""
        return self._inner.degree(id)

    def has_node(self, id: str) -> bool:
        """Check if a node exists."""
        return self._inner.has_node(id)

    def has_edge(self, source: str, target: str) -> bool:
        """Check if an edge exists."""
        return self._inner.has_edge(source, target)

    # --- Properties ---

    @property
    def n_nodes(self) -> int:
        return self._inner.n_nodes

    @property
    def n_edges(self) -> int:
        return self._inner.n_edges

    @property
    def is_directed(self) -> bool:
        return self._inner.is_directed

    @property
    def is_multi(self) -> bool:
        return self._inner.is_multi

    @property
    def name(self) -> str:
        return self._inner.name

    def is_dag(self) -> bool:
        """Check if the graph is a DAG."""
        return self._inner.is_dag()

    # --- Graph transforms ---

    def subgraph(self, node_ids: list[str]) -> Graph:
        """Extract a subgraph containing only the specified node IDs and edges between them."""
        return Graph._from_inner(self._inner.subgraph(node_ids))

    def ego_graph(self, center: str, radius: int = 1) -> Graph:
        """Extract the ego graph: all nodes within *radius* hops of *center*."""
        return Graph._from_inner(self._inner.ego_graph(center, radius))

    def is_connected(self) -> bool:
        """Whether the graph is (weakly) connected."""
        return self._inner.is_connected()

    def is_tree(self) -> bool:
        """Whether the graph is a tree (connected, |E| = |V| - 1, acyclic)."""
        return self._inner.is_tree()

    def reverse(self) -> Graph:
        """Return a new graph with all edge directions reversed."""
        return Graph._from_inner(self._inner.reverse())

    def to_undirected(self) -> Graph:
        """Convert to an undirected graph (add reverse edges where missing)."""
        return Graph._from_inner(self._inner.to_undirected())

    # --- Serialization ---

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return self._inner.to_json()

    @classmethod
    def from_json(cls, data: str, *, settings: Any = None) -> Graph:
        """Deserialize from JSON string.

        Audit A2-#3: caps are mandatory at the FFI boundary; if no settings
        instance is supplied we fall back to conservative built-in defaults
        so the standalone Python surface is bounded by default. MCP / runtime
        callers should pass ``settings=KaosGraphSettings.from_context(ctx)``.
        """
        max_bytes, max_nodes, max_edges = _resolve_graph_caps(settings)
        return cls._from_inner(PyGraph.from_json(data, max_bytes, max_nodes, max_edges))

    # --- Dunder ---

    def __len__(self) -> int:
        return self._inner.n_nodes

    def __contains__(self, id: str) -> bool:
        return self._inner.has_node(id)

    def __repr__(self) -> str:
        return f"Graph(nodes={self.n_nodes}, edges={self.n_edges}, directed={self.is_directed})"
