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

from kaos_graph.graph import Graph

__all__ = ["load_adjacency_json", "to_adjacency_json"]


def load_adjacency_json(data: str) -> Graph:
    """Load a graph from adjacency-list JSON format.

    Expected schema::

        {
            "directed": true,          // optional, default true
            "nodes": {"id": {...}},    // node_id -> properties
            "edges": {"id": [["target", {...}], ...]}  // source -> [(target, props)]
        }

    Args:
        data: JSON string in adjacency-list format.

    Returns:
        A new :class:`Graph` built from the adjacency data.

    Raises:
        ValueError: If the JSON is malformed or missing required keys.
    """
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(obj, dict):
        raise ValueError("Expected a JSON object at top level")

    directed = obj.get("directed", True)
    nodes: dict[str, dict[str, Any]] = obj.get("nodes", {})
    edges: dict[str, list[Any]] = obj.get("edges", {})

    g = Graph(directed=directed)

    for node_id, props in nodes.items():
        g.add_node(node_id, **(props if isinstance(props, dict) else {}))

    for source, targets in edges.items():
        # Ensure source node exists
        if not g.has_node(source):
            g.add_node(source)
        for entry in targets:
            if isinstance(entry, list) and len(entry) >= 1:
                target = entry[0]
                props = entry[1] if len(entry) > 1 and isinstance(entry[1], dict) else {}
            elif isinstance(entry, str):
                target = entry
                props = {}
            else:
                continue
            if not g.has_node(target):
                g.add_node(target)
            g.add_edge(source, target, **props)

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
