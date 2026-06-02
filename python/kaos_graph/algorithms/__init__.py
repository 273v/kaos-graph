"""Graph algorithms — typed Python wrappers over petgraph's Rust implementations."""

from __future__ import annotations

from collections.abc import Sequence

from kaos_graph._rust import algorithms as _raw
from kaos_graph._rust.graph import PyGraph
from kaos_graph.errors import KaosGraphError
from kaos_graph.graph import Graph
from kaos_graph.types import BfsNode, DfsEvent, LongestPathResult, NodeRank, PathResult


def _coerce_weight(node_id: str, raw: object, weight_key: str) -> float:
    """Coerce a node-property weight to ``float``, with a typed error.

    A2-#13: surface non-numeric weights as ``KaosGraphError`` instead of
    letting ``float(...)`` raise a generic ``ValueError`` from deep inside
    a hot loop.
    """
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError as exc:
            raise KaosGraphError(
                f"Node {node_id!r} has non-numeric string value {raw!r} for "
                f"weight property {weight_key!r}; critical_path requires int "
                "or float weights."
            ) from exc
    try:
        return float(str(raw))
    except (TypeError, ValueError) as exc:
        raise KaosGraphError(
            f"Node {node_id!r} has non-numeric value {raw!r} for weight property "
            f"{weight_key!r}; critical_path requires int or float weights. "
            "Cast the property to a number before calling, or pick a different "
            "weight key."
        ) from exc


def _g(graph: Graph) -> PyGraph:
    """Extract the inner PyGraph from a Graph."""
    return graph._inner


# ─── Traversal ──────────────────────────────────────────────────────────────


def bfs(graph: Graph, source: str) -> list[str]:
    """BFS traversal from source. Returns node IDs in BFS order."""
    return _raw.bfs(_g(graph), source)


def dfs(graph: Graph, source: str) -> list[str]:
    """DFS traversal from source. Returns node IDs in DFS (preorder)."""
    return _raw.dfs(_g(graph), source)


def bfs_with_depth(graph: Graph, source: str) -> list[BfsNode]:
    """BFS returning BfsNode(node_id, depth) results."""
    return [BfsNode(node_id=nid, depth=d) for nid, d in _raw.bfs_with_depth(_g(graph), source)]


def bfs_at_depth(graph: Graph, source: str, depth: int) -> list[str]:
    """Nodes at exactly the given depth from source."""
    return _raw.bfs_at_depth(_g(graph), source, depth)


def dfs_events(graph: Graph, source: str) -> list[DfsEvent]:
    """DFS with enter/exit events.

    Returns DfsEvent(node_id, event) results where event is "enter" or "exit".
    Enter events correspond to preorder, exit events to postorder.
    """
    return [DfsEvent(node_id=nid, event=ev) for nid, ev in _raw.dfs_events(_g(graph), source)]


# ─── Paths ──────────────────────────────────────────────────────────────────


def shortest_paths(
    graph: Graph,
    source: str,
    target: str | None = None,
    weight_key: str | None = None,
) -> dict[str, float]:
    """Single-source shortest paths via Dijkstra. Returns {node_id: cost}."""
    return _raw.shortest_paths(_g(graph), source, target, weight_key)


def shortest_path_length(
    graph: Graph,
    source: str,
    target: str,
    weight_key: str | None = None,
) -> float | None:
    """Shortest path distance between two nodes, or None if unreachable."""
    return _raw.shortest_path_length(_g(graph), source, target, weight_key)


def has_path(graph: Graph, source: str, target: str) -> bool:
    """Check if a path exists between two nodes."""
    return _raw.has_path(_g(graph), source, target)


def astar_path(
    graph: Graph,
    source: str,
    target: str,
    weight_key: str | None = None,
) -> PathResult | None:
    """A* shortest path. Returns PathResult or None if unreachable."""
    result = _raw.astar_path(_g(graph), source, target, weight_key)
    if result is None:
        return None
    return PathResult(cost=result["cost"], path=result["path"])


def bellman_ford_paths(
    graph: Graph,
    source: str,
    weight_key: str | None = None,
) -> dict[str, float]:
    """Bellman-Ford shortest paths. Supports negative weights."""
    return _raw.bellman_ford_paths(_g(graph), source, weight_key)


def all_simple_paths(
    graph: Graph,
    source: str,
    target: str,
    max_depth: int | None = None,
    max_paths: int = 10_000,
) -> list[list[str]]:
    """All simple (non-repeating) paths from source to target.

    Audit A2-#3: ``max_depth`` defaults to ``32`` (was effectively unbounded).
    ``max_paths`` truncates the result list to ``10_000`` by default to bound
    peak memory on dense graphs. Pass explicit larger values when the input
    is trusted and the result genuinely exceeds the cap.
    """
    depth = 32 if max_depth is None else max_depth
    return _raw.all_simple_paths(_g(graph), source, target, depth, max_paths)


def find_cycles(graph: Graph) -> list[list[str]]:
    """Find all cycles in the graph (SCC-based).

    Returns list of node-ID lists, one per strongly connected component
    that contains a cycle. Single-node self-loops are included.
    """
    return _raw.find_cycles(_g(graph))


def find_cycle_paths(graph: Graph) -> list[list[str]]:
    """Find one representative cycle path per SCC.

    Returns list of ordered cycle paths. Each path is a sequence of node IDs
    forming a cycle (the last node connects back to the first). Self-loops
    are represented as single-element lists.
    """
    return _raw.find_cycle_paths(_g(graph))


# ─── Components ─────────────────────────────────────────────────────────────


def strongly_connected_components(graph: Graph) -> list[list[str]]:
    """Strongly connected components via Tarjan's algorithm."""
    return _raw.strongly_connected_components(_g(graph))


def num_connected_components(graph: Graph) -> int:
    """Number of weakly connected components."""
    return _raw.num_connected_components(_g(graph))


def weakly_connected_components(graph: Graph) -> list[list[str]]:
    """Weakly connected components as lists of node IDs."""
    return _raw.weakly_connected_components(_g(graph))


def connected_components_from_edges(
    n_nodes: int,
    edges: Sequence[tuple[int, int]],
) -> list[int]:
    """Label connected components from an integer edge list (no Graph build).

    The array fast path. Takes contiguous integer node ids
    (``0 .. n_nodes - 1``) plus any ``(m, 2)`` integer edge container —
    a numpy array, a list of pairs, etc. — and returns a component label
    per node, **without** the cost of constructing and string-keying a
    property :class:`Graph` edge by edge. Designed to consume the
    ``(m, 2)`` ``uint32`` edges produced by
    ``kaos_nlp_core.similarity.near_duplicates`` (``.pairs``) and
    ``knn_graph`` (``KnnGraph.edges()``) — the embedding → similarity →
    clustering pipeline.

    Each node carries the **smallest node id in its component** — a
    canonical, deterministic label independent of edge order; isolated
    nodes label to themselves.

    Args:
        n_nodes: total node count; nodes are ``0 .. n_nodes - 1``.
        edges: any ``(m, 2)`` integer edge container. Each row is an
            undirected ``(a, b)`` edge.

    Returns:
        A length-``n_nodes`` list of ``int`` component labels.

    Raises:
        ValueError: if an edge references a node ``>= n_nodes``.
    """
    pairs = [(int(a), int(b)) for a, b in edges]
    return _raw.connected_components_from_edges(n_nodes, pairs)


def is_strongly_connected(graph: Graph) -> bool:
    """Check if every node is reachable from every other."""
    return _raw.is_strongly_connected(_g(graph))


def is_weakly_connected(graph: Graph) -> bool:
    """Check if the graph is weakly connected."""
    return _raw.is_weakly_connected(_g(graph))


# ─── DAG ────────────────────────────────────────────────────────────────────


def topological_sort(graph: Graph) -> list[str]:
    """Topological sort. Raises ValueError if graph has cycles."""
    return _raw.topological_sort(_g(graph))


def ancestors(graph: Graph, id: str) -> list[str]:
    """All ancestors of a node (nodes that can reach it)."""
    return _raw.ancestors(_g(graph), id)


def descendants(graph: Graph, id: str) -> list[str]:
    """All descendants of a node (nodes reachable from it)."""
    return _raw.descendants(_g(graph), id)


def longest_path(graph: Graph) -> LongestPathResult:
    """Longest path in a DAG (unweighted). Raises ValueError if cycles exist."""
    result = _raw.longest_path(_g(graph))
    return LongestPathResult(length=result["length"], path=result["path"])


def critical_path(graph: Graph, weight: str = "latency_ms") -> PathResult:
    """Weighted longest path in a DAG (critical path).

    Finds the path with the maximum sum of node ``weight`` properties.
    This is the bottleneck path in a workflow/program execution graph.

    Args:
        graph: A directed acyclic graph.
        weight: Node property key to use as weight (default: ``"latency_ms"``).

    Returns:
        PathResult with ``cost`` (total weight) and ``path`` (node IDs).

    Raises:
        ValueError: If the graph has cycles.
    """
    order = topological_sort(graph)
    if not order:
        return PathResult(cost=0.0, path=[])

    # DP: dist[node] = max total weight to reach this node
    dist: dict[str, float] = {}
    prev: dict[str, str | None] = {}
    for nid in order:
        node = graph.node(nid)
        w = _coerce_weight(nid, node.get(weight, 0.0), weight) if node else 0.0
        dist[nid] = w
        prev[nid] = None

    for nid in order:
        for succ in graph.successors(nid):
            succ_node = graph.node(succ)
            succ_w = _coerce_weight(succ, succ_node.get(weight, 0.0), weight) if succ_node else 0.0
            candidate = dist[nid] + succ_w
            if candidate > dist[succ]:
                dist[succ] = candidate
                prev[succ] = nid

    # Find the node with maximum distance. dist is non-empty because order is.
    best_node = max(dist, key=lambda n: dist[n])
    best_cost = dist[best_node]

    # Reconstruct path
    path: list[str] = []
    cur: str | None = best_node
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()

    return PathResult(cost=best_cost, path=path)


# ─── Centrality ─────────────────────────────────────────────────────────────


def pagerank(
    graph: Graph,
    damping_factor: float = 0.85,
    iterations: int = 100,
) -> list[NodeRank]:
    """PageRank centrality. Returns sorted list of NodeRank (descending)."""
    return [
        NodeRank(node_id=id, score=r)
        for id, r in _raw.pagerank(_g(graph), damping_factor, iterations)
    ]


def degree_centrality(graph: Graph) -> list[NodeRank]:
    """Degree centrality. Returns sorted list of NodeRank (descending)."""
    return [NodeRank(node_id=id, score=r) for id, r in _raw.degree_centrality(_g(graph))]


def in_degree_centrality(graph: Graph) -> list[NodeRank]:
    """In-degree centrality. Returns sorted list of NodeRank (descending)."""
    return [NodeRank(node_id=id, score=r) for id, r in _raw.in_degree_centrality(_g(graph))]


def out_degree_centrality(graph: Graph) -> list[NodeRank]:
    """Out-degree centrality. Returns sorted list of NodeRank (descending)."""
    return [NodeRank(node_id=id, score=r) for id, r in _raw.out_degree_centrality(_g(graph))]


def betweenness_centrality(
    graph: Graph,
    normalized: bool = True,
) -> list[NodeRank]:
    """Betweenness centrality (Brandes algorithm, O(VE)).

    Measures how often a node lies on shortest paths between other nodes.
    If normalized, divides by (V-1)(V-2) for directed graphs.
    """
    return [
        NodeRank(node_id=id, score=r)
        for id, r in _raw.betweenness_centrality(_g(graph), normalized)
    ]


def closeness_centrality(graph: Graph) -> list[NodeRank]:
    """Closeness centrality (Wasserman-Faust normalization).

    For each node: (reachable_count - 1) / sum_of_distances.
    Isolated nodes get centrality 0.
    """
    return [NodeRank(node_id=id, score=r) for id, r in _raw.closeness_centrality(_g(graph))]


def eigenvector_centrality(
    graph: Graph,
    iterations: int = 100,
    tolerance: float = 1e-6,
) -> list[NodeRank]:
    """Eigenvector centrality via power iteration.

    Nodes connected to high-scoring nodes get higher scores.
    Converges when L2 change < tolerance or iterations exhausted.
    """
    return [
        NodeRank(node_id=id, score=r)
        for id, r in _raw.eigenvector_centrality(_g(graph), iterations, tolerance)
    ]


# ─── Community ─────────────────────────────────────────────────────────────


def louvain_communities(graph: Graph) -> list[list[str]]:
    """Louvain community detection (modularity optimization).

    Two-phase iterative algorithm: greedily move nodes to maximize modularity,
    then contract communities into super-nodes. Repeat until stable.

    Returns list of communities, each a sorted list of node IDs.
    """
    return _raw.louvain_communities(_g(graph))


def label_propagation(graph: Graph) -> list[list[str]]:
    """Label propagation community detection.

    Each node starts with its own label. Iteratively, each node adopts the
    most common label among its neighbors (ties broken by smallest label).

    Returns list of communities, each a sorted list of node IDs.
    """
    return _raw.label_propagation(_g(graph))


# ─── Structure ──────────────────────────────────────────────────────────────


def bridges(graph: Graph) -> list[tuple[str, str]]:
    """Find bridge edges. Returns (source, target) pairs."""
    return _raw.bridges(_g(graph))


def greedy_matching(graph: Graph) -> list[tuple[str, str]]:
    """Greedy matching. O(|V|+|E|) time."""
    return _raw.greedy_matching(_g(graph))


def maximum_matching(graph: Graph) -> list[tuple[str, str]]:
    """Maximum matching via Gabow's algorithm. O(|V|^3) time."""
    return _raw.maximum_matching(_g(graph))


def maximal_cliques(
    graph: Graph,
    max_input_nodes: int = 1000,
    max_cliques: int = 10_000,
) -> list[list[str]]:
    """Maximal cliques via Bron-Kerbosch with pivoting.

    Bron-Kerbosch's worst case is 3^(N/3) cliques on Turán graphs.
    ``max_input_nodes`` (default 1000) is an upfront refuse-gate so peak
    CPU and memory are bounded at entry; ``max_cliques`` (default 10_000)
    truncates the result list as a second guard. Raise either explicitly
    when input shape is trusted (audit follow-up #2).
    """
    return _raw.maximal_cliques(_g(graph), max_input_nodes, max_cliques)


def density(graph: Graph) -> float:
    """Graph density."""
    return _raw.density(_g(graph))


def is_bipartite(graph: Graph) -> bool:
    """Check if the graph is bipartite (2-colorable)."""
    return _raw.is_bipartite(_g(graph))


def transitive_closure(graph: Graph) -> Graph:
    """Transitive closure: add edge (u,v) for every pair where v is reachable from u.

    Returns a new graph with all original edges plus transitive edges.
    """
    return Graph._from_inner(_raw.transitive_closure(_g(graph)))


def condensation(graph: Graph) -> Graph:
    """Condensation: contract SCCs into single nodes. Returns a new DAG."""
    return Graph._from_inner(_raw.condensation(_g(graph)))


def articulation_points(graph: Graph) -> list[str]:
    """Find articulation points (cut vertices).

    An articulation point is a node whose removal increases the number
    of connected components. Returns sorted list of node IDs.
    """
    return _raw.articulation_points(_g(graph))


def k_clique_communities(graph: Graph, k: int) -> list[list[str]]:
    """k-clique communities.

    Finds overlapping communities based on clique percolation:
    1. Find all maximal cliques of size >= k.
    2. Two cliques are connected if they share k-1 or more nodes.
    3. Connected components of the clique overlap graph = communities.
    4. Each community is the union of its constituent cliques' nodes.

    Returns list of communities, each a sorted list of node IDs.
    """
    return _raw.k_clique_communities(_g(graph), k)


__all__ = [
    "all_simple_paths",
    "ancestors",
    "articulation_points",
    "astar_path",
    "bellman_ford_paths",
    "betweenness_centrality",
    "bfs",
    "bfs_at_depth",
    "bfs_with_depth",
    "bridges",
    "closeness_centrality",
    "condensation",
    "connected_components_from_edges",
    "critical_path",
    "degree_centrality",
    "density",
    "descendants",
    "dfs",
    "dfs_events",
    "eigenvector_centrality",
    "find_cycle_paths",
    "find_cycles",
    "greedy_matching",
    "has_path",
    "in_degree_centrality",
    "is_bipartite",
    "is_strongly_connected",
    "is_weakly_connected",
    "k_clique_communities",
    "label_propagation",
    "longest_path",
    "louvain_communities",
    "maximal_cliques",
    "maximum_matching",
    "num_connected_components",
    "out_degree_centrality",
    "pagerank",
    "shortest_path_length",
    "shortest_paths",
    "strongly_connected_components",
    "topological_sort",
    "transitive_closure",
    "weakly_connected_components",
]
