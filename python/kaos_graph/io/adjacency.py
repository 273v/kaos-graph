"""Adjacency-list JSON serialization for kaos-graph.

Format::

    {
        "directed": true,
        "nodes": {"a": {"prop": "val"}, "b": {}},
        "edges": {"a": [["b", {"weight": 1.0}]]}
    }

Each key in ``edges`` maps to a list of ``[target, properties]`` pairs.
"""

from __future__ import annotations

import json
from typing import Any

from kaos_graph.graph import Graph, _resolve_graph_caps

__all__ = ["load_adjacency_json", "to_adjacency_json"]


def load_adjacency_json(data: str, *, settings: Any = None) -> Graph:
    """Load a graph from adjacency-list JSON format.

    Expected schema::

        {
            "directed": true,          // optional, default true
            "nodes": {"id": {...}},    // node_id -> properties
            "edges": {"id": [["target", {...}], ...]}  // source -> [(target, props)]
        }

    Audit KG-001: this loader is reachable from MCP, so it enforces the same
    byte / node / edge caps as :meth:`Graph.from_json`. Caps are resolved from
    ``settings`` (a :class:`KaosGraphSettings`-like object); if omitted,
    conservative built-in defaults apply so the standalone Python surface
    stays bounded by default.

    Args:
        data: JSON string in adjacency-list format.
        settings: Optional ``KaosGraphSettings`` (or compatible duck-typed
            object exposing ``max_bytes``/``max_nodes``/``max_edges``)
            controlling the cap thresholds.

    Returns:
        A new :class:`Graph` built from the adjacency data.

    Raises:
        ValueError: If the JSON is malformed, the input exceeds ``max_bytes``,
            the resulting graph would exceed ``max_nodes`` or ``max_edges``,
            or the top-level structure is not the expected mapping shape.
    """
    max_bytes, max_nodes, max_edges = _resolve_graph_caps(settings)

    # Pre-validate size before any parse so an oversized payload is refused
    # before we materialize the JSON tree.
    data_n_bytes = len(data.encode("utf-8"))
    if data_n_bytes > max_bytes:
        raise ValueError(f"adjacency_json is {data_n_bytes} bytes; max_bytes is {max_bytes}.")

    try:
        obj = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(obj, dict):
        raise ValueError("Expected a JSON object at top level")

    directed = obj.get("directed", True)
    nodes_raw: Any = obj.get("nodes", {})
    edges_raw: Any = obj.get("edges", {})

    if not isinstance(nodes_raw, dict):
        raise ValueError("'nodes' must be a JSON object mapping id -> properties.")
    if not isinstance(edges_raw, dict):
        raise ValueError(
            "'edges' must be a JSON object mapping source -> [[target, properties], ...]."
        )

    nodes: dict[str, dict[str, Any]] = nodes_raw
    edges: dict[str, list[Any]] = edges_raw

    g = Graph(directed=directed)

    node_count = 0
    edge_count = 0

    def _ensure_node(node_id: str) -> None:
        nonlocal node_count
        if g.has_node(node_id):
            return
        if node_count >= max_nodes:
            raise ValueError(
                f"adjacency_json would create more than {max_nodes} nodes; "
                "raise KAOS_GRAPH_MAX_NODES to load larger graphs."
            )
        g.add_node(node_id)
        node_count += 1

    for node_id, props in nodes.items():
        if node_count >= max_nodes:
            raise ValueError(
                f"adjacency_json defines more than {max_nodes} nodes; "
                "raise KAOS_GRAPH_MAX_NODES to load larger graphs."
            )
        g.add_node(node_id, **(props if isinstance(props, dict) else {}))
        node_count += 1

    for source, targets in edges.items():
        _ensure_node(source)
        if not isinstance(targets, list):
            continue
        for entry in targets:
            if isinstance(entry, list) and len(entry) >= 1:
                target = entry[0]
                props = entry[1] if len(entry) > 1 and isinstance(entry[1], dict) else {}
            elif isinstance(entry, str):
                target = entry
                props = {}
            else:
                continue
            _ensure_node(target)
            if edge_count >= max_edges:
                raise ValueError(
                    f"adjacency_json would create more than {max_edges} edges; "
                    "raise KAOS_GRAPH_MAX_EDGES to load larger graphs."
                )
            g.add_edge(source, target, **props)
            edge_count += 1

    return g


def to_adjacency_json(graph: Graph) -> str:
    """Export a graph to adjacency-list JSON format.

    Args:
        graph: The graph to export.

    Returns:
        JSON string in adjacency-list format.
    """
    nodes: dict[str, dict[str, Any]] = {}
    for node_id in graph.node_ids():
        node = graph.node(node_id)
        nodes[node_id] = node.properties if node else {}

    edges: dict[str, list[list[Any]]] = {}
    for edge in graph.edges():
        if edge.source not in edges:
            edges[edge.source] = []
        edges[edge.source].append([edge.target, edge.properties if edge.properties else {}])

    obj = {
        "directed": graph.is_directed,
        "nodes": nodes,
        "edges": edges,
    }
    return json.dumps(obj, indent=2)
