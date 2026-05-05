"""Knowledge graph operations -- typed Python wrappers over Rust implementations.

Provides: merge, diff, subgraph extraction by property, triple projection,
graph construction from triples, transitive type inference, and structural
analysis (orphans, hubs, degree distribution).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kaos_graph._rust import knowledge as _raw
from kaos_graph.graph import Graph
from kaos_graph.types import Triple


@dataclass(slots=True, frozen=True)
class GraphDiff:
    """Diff between two graphs."""

    added_nodes: list[str] = field(default_factory=list)
    removed_nodes: list[str] = field(default_factory=list)
    added_edges: list[tuple[str, str]] = field(default_factory=list)
    removed_edges: list[tuple[str, str]] = field(default_factory=list)
    changed_node_properties: list[str] = field(default_factory=list)


def _to_diff(d: dict[str, Any]) -> GraphDiff:
    """Convert the raw dict from Rust into a typed GraphDiff."""
    return GraphDiff(
        added_nodes=d["added_nodes"],
        removed_nodes=d["removed_nodes"],
        added_edges=[tuple(e) for e in d["added_edges"]],
        removed_edges=[tuple(e) for e in d["removed_edges"]],
        changed_node_properties=d["changed_node_properties"],
    )


def merge_graphs(
    base: Graph,
    other: Graph,
    conflict: str = "keep_latest",
) -> Graph:
    """Merge two graphs with a configurable conflict strategy.

    Args:
        base: The base graph.
        other: The graph to merge into *base*.
        conflict: Conflict resolution strategy:
            - ``"keep_first"`` -- keep base's properties on overlap.
            - ``"keep_latest"`` -- keep other's properties on overlap (default).
            - ``"merge"`` -- merge property maps; other's keys overwrite
              individual keys in base, but keys only in base are preserved.

    Returns:
        A new merged graph.
    """
    return Graph._from_inner(_raw.merge_graphs(base._inner, other._inner, conflict))


def diff_graphs(old: Graph, new: Graph) -> GraphDiff:
    """Diff two graphs.

    Returns added/removed nodes, added/removed edges, and node IDs whose
    properties changed.

    Args:
        old: The old (baseline) graph.
        new: The new graph.

    Returns:
        A :class:`GraphDiff` with the differences.
    """
    return _to_diff(_raw.diff_graphs(old._inner, new._inner))


def densify(graph: Graph, predicate: str) -> Graph:
    """Add transitive closure edges for a specific relationship type.

    If A->B and B->C both have the given *predicate*, adds A->C with
    that predicate.  This is functionally identical to :func:`infer_types`
    but named for non-type-hierarchy use cases.

    Args:
        graph: The source graph.
        predicate: The predicate/relationship to compute transitive closure over.

    Returns:
        A new graph with original edges plus inferred transitive edges.
    """
    return Graph._from_inner(_raw.densify(graph._inner, predicate))


def extract_subgraph_by_types(graph: Graph, types: list[str]) -> Graph:
    """Extract subgraph of nodes whose ``type`` property matches any value in *types*.

    All edges between matching nodes are preserved.

    Args:
        graph: The source graph.
        types: List of type values to include.

    Returns:
        A new subgraph containing only nodes with matching types.
    """
    return Graph._from_inner(_raw.extract_subgraph_by_types(graph._inner, types))


def extract_subgraph(
    graph: Graph,
    *,
    node_types: list[str] | None = None,
    edge_types: list[str] | None = None,
    **property_filter: Any,
) -> Graph:
    """Flexible subgraph extraction.

    Filters can be combined. Node type filtering is applied first, then
    edge type filtering, then arbitrary property filters.

    Args:
        graph: The source graph.
        node_types: If given, keep only nodes whose ``type`` property
            matches one of these values.
        edge_types: If given, after node filtering, remove edges whose
            ``type``/``predicate`` property does not match one of these values.
        **property_filter: Additional key=value filters on node properties.
            A node is kept only if it has the property with the exact value.

    Returns:
        A new subgraph.
    """
    # Start with node_types if given, otherwise copy the graph to avoid mutating the original
    if node_types is not None:
        result = extract_subgraph_by_types(graph, node_types)
    else:
        # Copy the graph so edge-type filtering doesn't mutate the caller's graph
        result = Graph.from_json(graph.to_json())

    # Apply arbitrary property filters
    for key, value in property_filter.items():
        result = extract_subgraph_by_property(result, key, value)

    # Apply edge type filtering by rebuilding with only matching edges.
    # This is multigraph-safe (remove_edge by endpoints is ambiguous for parallel edges).
    if edge_types is not None:
        edge_type_set = set(edge_types)
        filtered = Graph(directed=result.is_directed, name=result.name, multi=result.is_multi)
        for nid in result.node_ids():
            node = result.node(nid)
            if node:
                filtered.add_node(nid, **node.properties)
            else:
                filtered.add_node(nid)
        for edge in result.edges():
            edge_pred = edge.properties.get("predicate") or edge.properties.get("type")
            if edge_pred in edge_type_set:
                filtered.add_edge(edge.source, edge.target, **edge.properties)
        result = filtered

    return result


def extract_subgraph_by_property(graph: Graph, key: str, value: Any) -> Graph:
    """Extract a subgraph of nodes matching a property value.

    For example, ``extract_subgraph_by_property(g, "type", "person")``
    returns a subgraph of all nodes whose ``type`` property equals
    ``"person"``, plus all edges between them.

    Args:
        graph: The source graph.
        key: Property key to filter on.
        value: Property value to match.

    Returns:
        A new graph containing only matching nodes and their inter-edges.
    """
    return Graph._from_inner(_raw.extract_subgraph_by_property(graph._inner, key, value))


def project_triples(graph: Graph) -> list[Triple]:
    """Project graph edges as Triple(subject, predicate, object) results.

    Uses the edge's ``predicate`` property if present, otherwise
    ``"relatedTo"``.

    Args:
        graph: The source graph.

    Returns:
        List of :class:`Triple` results.
    """
    return [
        Triple(subject=s, predicate=p, object=o) for s, p, o in _raw.project_triples(graph._inner)
    ]


def from_triples(
    triples: list[Triple] | list[tuple[str, str, str]],
    *,
    directed: bool = True,
) -> Graph:
    """Build a graph from (subject, predicate, object) triples.

    Each unique subject/object becomes a node. Each triple becomes an edge
    with a ``predicate`` property.

    Accepts either :class:`Triple` dataclasses or plain ``(s, p, o)`` tuples
    for backward compatibility.

    Args:
        triples: List of :class:`Triple` or ``(subject, predicate, object)`` tuples.
        directed: Whether the resulting graph is directed (default True).

    Returns:
        A new graph built from the triples.
    """
    raw: list[tuple[str, str, str]] = [
        (t.subject, t.predicate, t.object) if isinstance(t, Triple) else t for t in triples
    ]
    return Graph._from_inner(_raw.from_triples(raw, directed))


def infer_types(graph: Graph, predicate_iri: str) -> Graph:
    """Infer transitive types via a specific predicate.

    If A->B via *predicate_iri* and B->C via *predicate_iri*, adds A->C
    via *predicate_iri*.

    Args:
        graph: The source graph.
        predicate_iri: The predicate to compute transitive closure over
            (e.g., ``"subClassOf"``).

    Returns:
        A new graph with original edges plus inferred transitive edges.
    """
    return Graph._from_inner(_raw.infer_types(graph._inner, predicate_iri))


def find_orphan_nodes(graph: Graph) -> list[str]:
    """Find orphan nodes (degree 0 -- no incident edges).

    Args:
        graph: The source graph.

    Returns:
        List of node IDs with no edges.
    """
    return _raw.find_orphan_nodes(graph._inner)


def find_hub_nodes(graph: Graph, threshold: int) -> list[str]:
    """Find hub nodes (degree > *threshold*).

    Args:
        graph: The source graph.
        threshold: Minimum degree (exclusive) to qualify as a hub.

    Returns:
        List of node IDs with degree exceeding *threshold*.
    """
    return _raw.find_hub_nodes(graph._inner, threshold)


def degree_distribution(graph: Graph) -> dict[int, int]:
    """Compute degree distribution.

    Args:
        graph: The source graph.

    Returns:
        Dict mapping degree to the count of nodes with that degree.
    """
    return _raw.degree_distribution(graph._inner)


__all__ = [
    "GraphDiff",
    "Triple",
    "degree_distribution",
    "densify",
    "diff_graphs",
    "extract_subgraph",
    "extract_subgraph_by_property",
    "extract_subgraph_by_types",
    "find_hub_nodes",
    "find_orphan_nodes",
    "from_triples",
    "infer_types",
    "merge_graphs",
    "project_triples",
]
