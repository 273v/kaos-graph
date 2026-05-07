"""Algorithm-oriented MCP tools.

Tools registered here:

- ``kaos-graph-algorithm``     — pagerank, shortest_path, BFS/DFS, centralities, …
- ``kaos-graph-critical-path`` — weighted longest path on a DAG
- ``kaos-graph-find-patterns`` — node/edge property filters
- ``kaos-graph-stats``         — aggregated graph statistics
"""

from __future__ import annotations

from typing import Any

from kaos_graph.tools._common import (
    _ALGORITHMS,
    _MODULE,
    _VERSION,
    get_logger,
    readonly_annotations,
    settings_for,
)

__all__ = ["register_algorithm_tools"]

logger = get_logger()


def register_algorithm_tools(runtime: Any) -> int:
    """Register the 4 algorithm-oriented tools with ``runtime``."""
    from kaos_core.base.context import KaosContext
    from kaos_core.base.tool import KaosTool
    from kaos_core.types.enums import ToolCapability, ToolCategory
    from kaos_core.types.metadata import ToolMetadata
    from kaos_core.types.parameters import ParameterSchema
    from kaos_core.types.results import ToolResult

    _READONLY = readonly_annotations()

    # ── kaos-graph-algorithm ───────────────────────────────────────────

    class GraphAlgorithmTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-algorithm",
                display_name="Run Graph Algorithm",
                description=(
                    "Run a graph algorithm: pagerank, shortest_path, bfs, dfs, "
                    "topological_sort, scc, betweenness_centrality, closeness_centrality, "
                    "eigenvector_centrality, degree_centrality, louvain, label_propagation, "
                    "longest_path, ancestors, descendants. "
                    "Requires a graph_json. Some algorithms need a source node_id."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.ANALYZE,
                module_name=_MODULE,
                version=_VERSION,
                annotations=_READONLY,
                input_schema=[
                    ParameterSchema(
                        name="graph_json",
                        type="string",
                        description="JSON graph data (from kaos-graph-create result).",
                    ),
                    ParameterSchema(
                        name="algorithm",
                        type="string",
                        description="Algorithm to run.",
                        constraints={"enum": _ALGORITHMS},
                    ),
                    ParameterSchema(
                        name="source",
                        type="string",
                        description="Source node ID (for path/traversal algorithms).",
                        required=False,
                    ),
                    ParameterSchema(
                        name="target",
                        type="string",
                        description="Target node ID (for shortest_path).",
                        required=False,
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            from kaos_graph import algorithms
            from kaos_graph.graph import Graph

            try:
                g = Graph.from_json(inputs["graph_json"], settings=settings_for(context))
            except Exception as exc:
                logger.debug("Failed to load graph in kaos-graph-algorithm: %s", exc)
                return ToolResult.create_error(
                    f"Failed to load graph: {exc}. "
                    "Pass the 'graph_data' field from a kaos-graph-create or "
                    "kaos-graph-load-rdf result. "
                    "Alternatively, call kaos-graph-create with a new JSON definition."
                )

            algo = inputs["algorithm"]
            source = inputs.get("source")
            target = inputs.get("target")

            try:
                if algo == "pagerank":
                    ranks = algorithms.pagerank(g)
                    data = [{"node_id": r.node_id, "score": r.score} for r in ranks[:20]]
                    summary = (
                        f"PageRank: top node '{ranks[0].node_id}' (score={ranks[0].score:.4f})"
                        if ranks
                        else "PageRank: empty graph"
                    )
                    return ToolResult.create_success(
                        {"algorithm": "pagerank", "results": data, "total": len(ranks)},
                        summary=summary,
                    )

                elif algo == "shortest_path":
                    if not source or not target:
                        return ToolResult.create_error(
                            "shortest_path requires both 'source' and 'target' node IDs. "
                            "Pass them as the 'source' and 'target' parameters. "
                            "For algorithms that don't need specific nodes, try pagerank, "
                            "louvain, or betweenness_centrality."
                        )
                    result = algorithms.astar_path(g, source, target)
                    if result is None:
                        return ToolResult.create_success(
                            {"algorithm": "shortest_path", "reachable": False},
                            summary=f"No path from '{source}' to '{target}'.",
                        )
                    return ToolResult.create_success(
                        {
                            "algorithm": "shortest_path",
                            "reachable": True,
                            "cost": result.cost,
                            "path": result.path,
                        },
                        summary=f"Shortest path: {' -> '.join(result.path)} (cost={result.cost})",
                    )

                elif algo == "bfs":
                    if not source:
                        return ToolResult.create_error(
                            "bfs requires a 'source' node ID. "
                            "Pass it as the 'source' parameter. "
                            "For algorithms that don't need a source, try pagerank or louvain."
                        )
                    order = algorithms.bfs(g, source)
                    return ToolResult.create_success(
                        {"algorithm": "bfs", "order": order},
                        summary=f"BFS from '{source}': {len(order)} nodes visited.",
                    )

                elif algo == "dfs":
                    if not source:
                        return ToolResult.create_error(
                            "dfs requires a 'source' node ID. "
                            "Pass it as the 'source' parameter. "
                            "For algorithms that don't need a source, try pagerank or louvain."
                        )
                    order = algorithms.dfs(g, source)
                    return ToolResult.create_success(
                        {"algorithm": "dfs", "order": order},
                        summary=f"DFS from '{source}': {len(order)} nodes visited.",
                    )

                elif algo == "topological_sort":
                    order = algorithms.topological_sort(g)
                    return ToolResult.create_success(
                        {"algorithm": "topological_sort", "order": order},
                        summary=f"Topological sort: {len(order)} nodes.",
                    )

                elif algo == "scc":
                    components = algorithms.strongly_connected_components(g)
                    return ToolResult.create_success(
                        {"algorithm": "scc", "components": components, "count": len(components)},
                        summary=f"Found {len(components)} strongly connected component(s).",
                    )

                elif algo in (
                    "betweenness_centrality",
                    "closeness_centrality",
                    "eigenvector_centrality",
                    "degree_centrality",
                ):
                    func = getattr(algorithms, algo)
                    ranks = func(g)
                    data = [{"node_id": r.node_id, "score": r.score} for r in ranks[:20]]
                    summary = (
                        f"{algo}: top node '{ranks[0].node_id}' (score={ranks[0].score:.4f})"
                        if ranks
                        else f"{algo}: empty graph"
                    )
                    return ToolResult.create_success(
                        {"algorithm": algo, "results": data, "total": len(ranks)},
                        summary=summary,
                    )

                elif algo == "louvain":
                    communities = algorithms.louvain_communities(g)
                    return ToolResult.create_success(
                        {
                            "algorithm": "louvain",
                            "communities": communities,
                            "count": len(communities),
                        },
                        summary=f"Louvain: {len(communities)} community(ies).",
                    )

                elif algo == "label_propagation":
                    communities = algorithms.label_propagation(g)
                    return ToolResult.create_success(
                        {
                            "algorithm": "label_propagation",
                            "communities": communities,
                            "count": len(communities),
                        },
                        summary=f"Label propagation: {len(communities)} community(ies).",
                    )

                elif algo == "longest_path":
                    result = algorithms.longest_path(g)
                    return ToolResult.create_success(
                        {
                            "algorithm": "longest_path",
                            "length": result.length,
                            "path": result.path,
                        },
                        summary=f"Longest path: length={result.length}, "
                        f"path={' -> '.join(result.path)}",
                    )

                elif algo == "ancestors":
                    if not source:
                        return ToolResult.create_error(
                            "ancestors requires a 'source' node ID. "
                            "Pass it as the 'source' parameter. "
                            "For graph-wide analysis, try pagerank or scc instead."
                        )
                    anc = algorithms.ancestors(g, source)
                    return ToolResult.create_success(
                        {"algorithm": "ancestors", "node_id": source, "ancestors": anc},
                        summary=f"Node '{source}' has {len(anc)} ancestor(s).",
                    )

                elif algo == "descendants":
                    if not source:
                        return ToolResult.create_error(
                            "descendants requires a 'source' node ID. "
                            "Pass it as the 'source' parameter. "
                            "For graph-wide analysis, try pagerank or scc instead."
                        )
                    desc = algorithms.descendants(g, source)
                    return ToolResult.create_success(
                        {"algorithm": "descendants", "node_id": source, "descendants": desc},
                        summary=f"Node '{source}' has {len(desc)} descendant(s).",
                    )

                else:
                    return ToolResult.create_error(
                        f"Unknown algorithm '{algo}'. Supported: {', '.join(_ALGORITHMS)}"
                    )

            except (ValueError, KeyError) as exc:
                return ToolResult.create_error(
                    f"Algorithm '{algo}' failed: {exc}. "
                    "Check that the graph structure is compatible with this algorithm "
                    "(e.g., topological_sort and longest_path require a DAG)."
                )

    # ── kaos-graph-critical-path ─────────────────────────────────────

    class CriticalPathTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-critical-path",
                display_name="Critical Path",
                description=(
                    "Find the critical path (weighted longest path) in a DAG. "
                    "Uses node property values as weights to find the bottleneck path. "
                    "Useful for analyzing workflow/pipeline execution times. "
                    "The graph must be a DAG (no cycles). "
                    "Follow up with kaos-graph-trace-to-graph to convert execution traces."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.ANALYZE,
                module_name=_MODULE,
                version=_VERSION,
                annotations=_READONLY,
                input_schema=[
                    ParameterSchema(
                        name="graph_json",
                        type="string",
                        description=(
                            "JSON graph data (from kaos-graph-create result). Must be a DAG."
                        ),
                    ),
                    ParameterSchema(
                        name="weight",
                        type="string",
                        description="Node property key to use as weight (default 'latency_ms').",
                        required=False,
                        default="latency_ms",
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            from kaos_graph import algorithms
            from kaos_graph.graph import Graph

            try:
                g = Graph.from_json(inputs["graph_json"], settings=settings_for(context))
            except Exception as exc:
                logger.debug("Failed to load graph in kaos-graph-critical-path: %s", exc)
                return ToolResult.create_error(
                    f"Failed to load graph: {exc}. "
                    "Pass the 'graph_data' field from a kaos-graph-create or "
                    "kaos-graph-trace-to-graph result. "
                    "Alternatively, call kaos-graph-create with a new JSON definition."
                )

            weight = inputs.get("weight", "latency_ms")

            try:
                result = algorithms.critical_path(g, weight=weight)
            except ValueError as exc:
                return ToolResult.create_error(
                    f"Critical path failed: {exc}. "
                    "The graph must be a DAG (no cycles). "
                    "Use kaos-graph-info to check if is_dag is true."
                )

            info = {
                "path": result.path,
                "total_cost": result.cost,
                "weight_key": weight,
                "path_length": len(result.path),
            }
            summary = (
                f"Critical path ({weight}): "
                f"cost={result.cost:.2f}, "
                f"path={' -> '.join(result.path)}."
            )
            return ToolResult.create_success(info, summary=summary)

    # ── kaos-graph-find-patterns ─────────────────────────────────────

    class FindPatternsTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-find-patterns",
                display_name="Find Patterns",
                description=(
                    "Find nodes and edges matching property filters. "
                    "Specify node_filters and/or edge_filters as key-value pairs; "
                    "all specified properties must match (AND logic). "
                    "Returns matching node IDs and edges. "
                    "For SPARQL-based queries, use kaos-graph-sparql instead."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.QUERY,
                module_name=_MODULE,
                version=_VERSION,
                annotations=_READONLY,
                input_schema=[
                    ParameterSchema(
                        name="graph_json",
                        type="string",
                        description="JSON graph data (from kaos-graph-create result).",
                    ),
                    ParameterSchema(
                        name="node_filters",
                        type="object",
                        description=(
                            "Property key-value pairs to filter nodes. "
                            'Example: {"type": "person", "active": true}'
                        ),
                        required=False,
                    ),
                    ParameterSchema(
                        name="edge_filters",
                        type="object",
                        description=(
                            "Property key-value pairs to filter edges. "
                            'Example: {"type": "knows", "weight": 1.0}'
                        ),
                        required=False,
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            from kaos_graph.graph import Graph

            try:
                g = Graph.from_json(inputs["graph_json"], settings=settings_for(context))
            except Exception as exc:
                logger.debug("Failed to load graph in kaos-graph-find-patterns: %s", exc)
                return ToolResult.create_error(
                    f"Failed to load graph: {exc}. "
                    "Pass the 'graph_data' field from a kaos-graph-create or "
                    "kaos-graph-load-rdf result. "
                    "Alternatively, call kaos-graph-create with a new JSON definition."
                )

            node_filters = inputs.get("node_filters") or {}
            edge_filters = inputs.get("edge_filters") or {}

            if not node_filters and not edge_filters:
                return ToolResult.create_error(
                    "Provide at least one of 'node_filters' or 'edge_filters'. "
                    "Each is a dict of property key-value pairs to match."
                )

            matching_nodes: list[str] = []
            if node_filters:
                matching_nodes = g.nodes(**node_filters)

            matching_edges: list[dict[str, Any]] = []
            if edge_filters:
                edges = g.edges(**edge_filters)
                matching_edges = [
                    {
                        "source": e.source,
                        "target": e.target,
                        "properties": e.properties,
                    }
                    for e in edges
                ]

            info = {
                "matching_nodes": matching_nodes,
                "matching_edges": matching_edges,
                "node_count": len(matching_nodes),
                "edge_count": len(matching_edges),
            }
            summary = (
                f"Found {len(matching_nodes)} matching node(s) "
                f"and {len(matching_edges)} matching edge(s)."
            )
            return ToolResult.create_success(info, summary=summary)

    # ── kaos-graph-stats ─────────────────────────────────────────────

    class GraphStatsTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-stats",
                display_name="Graph Statistics",
                description=(
                    "Compute comprehensive statistics for a graph: "
                    "node_count, edge_count, density, avg_degree, max_degree, "
                    "is_dag, connected_components count. "
                    "For basic info, use kaos-graph-info. "
                    "For algorithm results, use kaos-graph-algorithm."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.ANALYZE,
                module_name=_MODULE,
                version=_VERSION,
                annotations=_READONLY,
                input_schema=[
                    ParameterSchema(
                        name="graph_json",
                        type="string",
                        description="JSON graph data (from kaos-graph-create result).",
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            from kaos_graph import algorithms
            from kaos_graph.graph import Graph

            try:
                g = Graph.from_json(inputs["graph_json"], settings=settings_for(context))
            except Exception as exc:
                logger.debug("Failed to load graph in kaos-graph-stats: %s", exc)
                return ToolResult.create_error(
                    f"Failed to load graph: {exc}. "
                    "Pass the 'graph_data' field from a kaos-graph-create or "
                    "kaos-graph-load-rdf result. "
                    "Alternatively, call kaos-graph-create with a new JSON definition."
                )

            n_nodes = g.n_nodes
            n_edges = g.n_edges
            graph_density = algorithms.density(g)
            is_dag = g.is_dag()
            n_components = algorithms.num_connected_components(g)

            if n_nodes > 0:
                degrees = [g.degree(nid) for nid in g.node_ids()]
                avg_degree = sum(degrees) / len(degrees)
                max_degree = max(degrees)
            else:
                avg_degree = 0.0
                max_degree = 0

            info = {
                "node_count": n_nodes,
                "edge_count": n_edges,
                "density": graph_density,
                "avg_degree": round(avg_degree, 4),
                "max_degree": max_degree,
                "is_dag": is_dag,
                "connected_components": n_components,
                "is_directed": g.is_directed,
            }
            summary = (
                f"Graph stats: {n_nodes} nodes, {n_edges} edges, "
                f"density={graph_density:.4f}, avg_degree={avg_degree:.2f}, "
                f"max_degree={max_degree}, "
                f"dag={is_dag}, components={n_components}."
            )
            return ToolResult.create_success(info, summary=summary)

    # ── Registration ──────────────────────────────────────────────────

    tool_classes: list[type[KaosTool]] = [
        GraphAlgorithmTool,
        CriticalPathTool,
        FindPatternsTool,
        GraphStatsTool,
    ]
    for cls in tool_classes:
        runtime.tools.register_tool(cls())
    return len(tool_classes)
