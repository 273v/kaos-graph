"""kaos-graph MCP tools.

Defines 17 MCP tools for graph operations. All kaos-core imports are lazy
(inside ``register_graph_tools``) so that kaos-graph can be used standalone
without kaos-core installed (audit A2-#2). At module-import time we only need
``json``, ``logging``, and ``typing``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol


def _get_logger() -> logging.Logger:
    """Return a kaos-* logger when kaos-core is installed, else stdlib.

    Keeps the module import-clean for standalone consumers (A2-#2), while
    preserving session/trace correlation for MCP-aware deployments.
    """
    try:
        from kaos_core.logging import get_logger  # type: ignore[import-not-found]

        return get_logger(__name__)
    except ImportError:
        return logging.getLogger(__name__)


logger = _get_logger()

_MODULE = "kaos-graph"
_VERSION = "0.1.0a1"

# Supported algorithm names for kaos-graph-algorithm
_ALGORITHMS = [
    "pagerank",
    "shortest_path",
    "bfs",
    "dfs",
    "topological_sort",
    "scc",
    "betweenness_centrality",
    "closeness_centrality",
    "eigenvector_centrality",
    "degree_centrality",
    "louvain",
    "label_propagation",
    "longest_path",
    "ancestors",
    "descendants",
]

# Supported export formats for kaos-graph-export
_EXPORT_FORMATS = ["json", "mermaid", "dot", "turtle", "ntriples", "graphml", "gexf"]


class _RuntimeLike(Protocol):
    # Duck-typed: anything with a ``tools`` attribute that supports
    # ``.register_tool(tool)`` works. Declared as Any to keep MockRuntime
    # / KaosRuntime / partial fakes in tests assignable without casting.
    tools: Any


def register_graph_tools(runtime: _RuntimeLike) -> int:
    """Register kaos-graph MCP tools with a KaosRuntime.

    All 7 tools are defined inside this function to keep kaos-core imports
    lazy. The function returns the count of registered tools.

    Args:
        runtime: A ``KaosRuntime`` instance.

    Returns:
        Number of tools registered.

    Raises:
        ImportError: If kaos-core is not installed.
    """
    try:
        from kaos_core.base.context import KaosContext
        from kaos_core.base.tool import KaosTool
        from kaos_core.types.annotations import ToolAnnotations
        from kaos_core.types.enums import ToolCapability, ToolCategory
        from kaos_core.types.metadata import ToolMetadata
        from kaos_core.types.parameters import ParameterSchema
        from kaos_core.types.results import ToolResult
    except ImportError as e:
        raise ImportError(
            "kaos-core is required for MCP tool registration. Install with: pip install kaos-core"
        ) from e

    # Shared annotations: all graph tools are read-only and local-only
    _READONLY = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )

    # ── Helpers ────────────────────────────────────────────────────────

    def _settings_for(context: KaosContext | None) -> Any:
        """Settings instance scoped to the current MCP context.

        Audit follow-up #3: every MCP handler must thread the request's
        ``KaosGraphSettings`` through to ``Graph.from_json`` so caps reflect
        the configured / per-request overrides instead of the standalone
        defaults.
        """
        from kaos_graph.settings import KaosGraphSettings

        return KaosGraphSettings.from_context(context)

    def _capped_json_loads(
        data: str,
        context: KaosContext | None,
        kind: str,
    ) -> Any:
        """``json.loads`` gated by ``KaosGraphSettings.max_bytes``.

        A2-followup-#2: the audit follow-up #3 fix capped ``Graph.from_json``,
        but the three raw ``json.loads`` paths (adjacency, trace, schema) were
        missed. This helper wraps every MCP-side ``json.loads`` so they share
        the same byte cap as ``Graph.from_json``. ``kind`` appears in error
        messages so the agent knows which input was rejected.
        """
        settings = _settings_for(context)
        max_bytes = int(getattr(settings, "max_bytes", 64 * 1024 * 1024))
        if len(data) > max_bytes:
            raise ValueError(
                f"{kind} JSON is {len(data)} bytes; max_bytes is {max_bytes}. "
                "Raise KAOS_GRAPH_MAX_BYTES if intended."
            )
        return json.loads(data)

    def _graph_from_json(data: str, context: KaosContext | None = None) -> Any:
        """Parse a JSON graph definition into a Graph (capped via settings).

        Audit follow-up #3: replaces the raw ``json.loads`` path that bypassed
        ``Graph.from_json`` and its byte/node/edge caps. Even the
        ``kaos-graph-create`` schema (top-level ``nodes``/``edges`` arrays)
        is canonicalized to the standard wire shape so a single capped
        codepath handles every MCP entry.
        """
        from kaos_graph.graph import Graph

        # Pre-validate size before any parse; cheap and refuses obviously
        # oversized payloads even if json.loads has a deeper structural
        # issue further in.
        settings = _settings_for(context)
        max_bytes = int(getattr(settings, "max_bytes", 64 * 1024 * 1024))
        if len(data) > max_bytes:
            raise ValueError(f"graph_json is {len(data)} bytes; max_bytes is {max_bytes}.")

        parsed = json.loads(data)
        # Translate the kaos-graph-create wire shape (nodes is list of
        # ``{id, ...props}`` dicts; edges is list of ``{source, target,
        # ...props}``) into the canonical Graph.to_json() shape so we can
        # re-feed Graph.from_json and reuse its caps.
        canonical = {
            "directed": parsed.get("directed", True),
            "multi": parsed.get("multi", False),
            "name": parsed.get("name") or "",
            "nodes": [
                {"id": n["id"], "properties": {k: v for k, v in n.items() if k != "id"}}
                for n in parsed.get("nodes", [])
            ],
            "edges": [
                {
                    "source": e["source"],
                    "target": e["target"],
                    "properties": {k: v for k, v in e.items() if k not in ("source", "target")},
                }
                for e in parsed.get("edges", [])
            ],
        }
        return Graph.from_json(json.dumps(canonical), settings=settings)

    def _stub_result(tool_name: str) -> ToolResult:
        return ToolResult.create_error(
            f"{tool_name} is not yet fully implemented. "
            "Use kaos-graph-info or kaos-graph-visualize for working tools."
        )

    # ── 1. kaos-graph-create ──────────────────────────────────────────

    class GraphCreateTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-create",
                display_name="Create Graph",
                description=(
                    "Create a new graph from a JSON definition. "
                    "Input: JSON with 'nodes' (list of {id, ...props}) "
                    "and 'edges' (list of {source, target, ...props}). "
                    "Optional: 'directed' (bool, default true), 'name' (string). "
                    "Returns graph info summary. "
                    "Follow up with kaos-graph-info or kaos-graph-visualize."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.TRANSFORM,
                module_name=_MODULE,
                version=_VERSION,
                annotations=_READONLY,
                input_schema=[
                    ParameterSchema(
                        name="graph_json",
                        type="string",
                        description=(
                            "JSON graph definition: "
                            '{"nodes": [{"id": "a"}, {"id": "b"}], '
                            '"edges": [{"source": "a", "target": "b"}], '
                            '"directed": true, "name": "my_graph"}'
                        ),
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            try:
                graph_json = inputs["graph_json"]
                g = _graph_from_json(graph_json, context=context)
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                return ToolResult.create_error(
                    f"Invalid graph JSON: {exc}. "
                    "Provide a JSON object with 'nodes' (list of {{id: ...}}) "
                    "and 'edges' (list of {{source: ..., target: ...}})."
                )

            info = {
                "name": g.name,
                "n_nodes": g.n_nodes,
                "n_edges": g.n_edges,
                "is_directed": g.is_directed,
                "graph_data": g.to_json(),
            }
            summary = (
                f"Created graph '{g.name}' with "
                f"{g.n_nodes} nodes and {g.n_edges} edges "
                f"(directed={g.is_directed})."
            )
            return ToolResult.create_success(info, summary=summary)

    # ── 2. kaos-graph-query ───────────────────────────────────────────

    class GraphQueryTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-query",
                display_name="Query Graph",
                description=(
                    "Query a graph: get node properties, list neighbors, "
                    "successors, or predecessors of a node. "
                    "Requires a graph_json (from kaos-graph-create) and a node_id. "
                    "query_type: 'node', 'neighbors', 'successors', 'predecessors'."
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
                        name="node_id",
                        type="string",
                        description="The node ID to query.",
                    ),
                    ParameterSchema(
                        name="query_type",
                        type="string",
                        description="Query type.",
                        required=False,
                        default="node",
                        constraints={"enum": ["node", "neighbors", "successors", "predecessors"]},
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            from kaos_graph.graph import Graph

            try:
                g = Graph.from_json(inputs["graph_json"], settings=_settings_for(context))
            except Exception as exc:
                logger.debug("Failed to load graph in kaos-graph-query: %s", exc)
                return ToolResult.create_error(
                    f"Failed to load graph: {exc}. "
                    "Pass the 'graph_data' field from a kaos-graph-create or "
                    "kaos-graph-load-rdf result. "
                    "Alternatively, call kaos-graph-create with a new JSON definition."
                )

            node_id = inputs["node_id"]
            if not g.has_node(node_id):
                return ToolResult.create_error(
                    f"Node '{node_id}' not found. "
                    f"Available nodes: {g.node_ids()[:20]}" + (" ..." if g.n_nodes > 20 else "")
                )

            query_type = inputs.get("query_type", "node")
            if query_type == "node":
                node = g.node(node_id)
                props = node.properties if node else {}
                result = {"node_id": node_id, "properties": props, "degree": g.degree(node_id)}
                return ToolResult.create_success(
                    result,
                    summary=f"Node '{node_id}': degree={g.degree(node_id)}, props={props}",
                )
            elif query_type == "neighbors":
                nbrs = g.neighbors(node_id)
                return ToolResult.create_success(
                    {"node_id": node_id, "neighbors": nbrs, "count": len(nbrs)},
                    summary=f"Node '{node_id}' has {len(nbrs)} neighbor(s): {nbrs[:10]}",
                )
            elif query_type == "successors":
                succ = g.successors(node_id)
                return ToolResult.create_success(
                    {"node_id": node_id, "successors": succ, "count": len(succ)},
                    summary=f"Node '{node_id}' has {len(succ)} successor(s): {succ[:10]}",
                )
            elif query_type == "predecessors":
                pred = g.predecessors(node_id)
                return ToolResult.create_success(
                    {"node_id": node_id, "predecessors": pred, "count": len(pred)},
                    summary=f"Node '{node_id}' has {len(pred)} predecessor(s): {pred[:10]}",
                )
            else:
                return ToolResult.create_error(
                    f"Unknown query_type '{query_type}'. "
                    "Use: node, neighbors, successors, predecessors."
                )

    # ── 3. kaos-graph-algorithm ───────────────────────────────────────

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
                g = Graph.from_json(inputs["graph_json"], settings=_settings_for(context))
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

    # ── 4. kaos-graph-load-rdf ────────────────────────────────────────

    class GraphLoadRdfTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-load-rdf",
                display_name="Load RDF/OWL",
                description=(
                    "Load an RDF or OWL file into a graph. "
                    "Supports Turtle (.ttl), N-Triples (.nt), RDF/XML (.rdf, .owl). "
                    "Returns graph info and the graph_data JSON for use with other tools. "
                    "Follow up with kaos-graph-info, kaos-graph-algorithm, "
                    "or kaos-graph-visualize."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.EXTRACT,
                module_name=_MODULE,
                version=_VERSION,
                annotations=_READONLY,
                input_schema=[
                    ParameterSchema(
                        name="path",
                        type="string",
                        description="Path to an RDF/OWL file (.ttl, .nt, .rdf, .owl).",
                    ),
                    ParameterSchema(
                        name="format",
                        type="string",
                        description="Explicit RDF format override.",
                        required=False,
                        constraints={"enum": ["turtle", "ntriples", "rdfxml", "nquads", "trig"]},
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            from kaos_graph.errors import PathTraversalError
            from kaos_graph.rdf import load_rdf
            from kaos_graph.settings import KaosGraphSettings

            path = inputs["path"]
            settings = KaosGraphSettings.from_context(context)

            # A2-#1: the MCP tool surface is the audited boundary, so we
            # enforce ``allowed_root`` here. The library function itself is
            # permissive by default (in-process callers are trusted).
            if settings.allowed_root is None:
                return ToolResult.create_error(
                    "kaos-graph-load-rdf requires KaosGraphSettings.allowed_root "
                    "to be configured before MCP exposure. Set "
                    "KAOS_GRAPH_ALLOWED_ROOT (or pass allowed_root in "
                    "_meta.kaos_config) to a directory containing the RDF/OWL "
                    "files you want to expose."
                )

            try:
                fmt = inputs.get("format")
                g, stats = load_rdf(path, format=fmt, settings=settings, is_path=True)
            except PathTraversalError as exc:
                return ToolResult.create_error(
                    f"{exc}. Configure KAOS_GRAPH_ALLOWED_ROOT in env or pass "
                    "allowed_root in _meta.kaos_config."
                )
            except Exception as exc:
                logger.debug("Failed to load RDF file '%s': %s", path, exc)
                return ToolResult.create_error(
                    f"Failed to load RDF file: {exc}. "
                    "Ensure the file is valid RDF/OWL and the format matches the content. "
                    "Try specifying format= explicitly (turtle, ntriples, rdfxml). "
                    "For inline RDF strings, use kaos-graph-load-rdf-string instead."
                )

            info = {
                "name": g.name,
                "n_nodes": g.n_nodes,
                "n_edges": g.n_edges,
                "is_directed": g.is_directed,
                "stats": {
                    "total_triples": stats.total_triples,
                    "nodes": stats.nodes,
                    "edges": stats.edges,
                    "literal_properties": stats.literal_properties,
                    "load_time_ms": stats.load_time_ms,
                },
                "graph_data": g.to_json(),
            }
            from pathlib import Path as _Path

            summary = (
                f"Loaded RDF from '{_Path(path).name}': "
                f"{stats.total_triples} triples -> "
                f"{g.n_nodes} nodes, {g.n_edges} edges "
                f"(in {stats.load_time_ms}ms)."
            )
            return ToolResult.create_success(info, summary=summary)

    # ── 5. kaos-graph-export ──────────────────────────────────────────

    class GraphExportTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-export",
                display_name="Export Graph",
                description=(
                    "Export a graph to various formats: json, mermaid, dot, "
                    "turtle, ntriples, graphml, gexf. "
                    "Requires graph_json from kaos-graph-create or kaos-graph-load-rdf."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.TRANSFORM,
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
                        name="format",
                        type="string",
                        description="Export format.",
                        constraints={"enum": _EXPORT_FORMATS},
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            from kaos_graph.graph import Graph
            from kaos_graph.io import to_dot, to_mermaid

            try:
                g = Graph.from_json(inputs["graph_json"], settings=_settings_for(context))
            except Exception as exc:
                logger.debug("Failed to load graph in kaos-graph-export: %s", exc)
                return ToolResult.create_error(
                    f"Failed to load graph: {exc}. "
                    "Pass the 'graph_data' field from a kaos-graph-create or "
                    "kaos-graph-load-rdf result. "
                    "Alternatively, call kaos-graph-create with a new JSON definition."
                )

            fmt = inputs["format"]
            try:
                if fmt == "json":
                    output = g.to_json()
                elif fmt == "mermaid":
                    output = to_mermaid(g)
                elif fmt == "dot":
                    output = to_dot(g)
                elif fmt == "turtle":
                    from kaos_graph.rdf import to_turtle

                    output = to_turtle(g)
                elif fmt == "ntriples":
                    from kaos_graph.rdf import to_ntriples

                    output = to_ntriples(g)
                elif fmt == "graphml":
                    from kaos_graph.io import to_graphml

                    output = to_graphml(g)
                elif fmt == "gexf":
                    from kaos_graph.io import to_gexf

                    output = to_gexf(g)
                else:
                    return ToolResult.create_error(
                        f"Unknown format '{fmt}'. Supported: {', '.join(_EXPORT_FORMATS)}"
                    )
            except Exception as exc:
                logger.debug("Export to '%s' failed: %s", fmt, exc)
                return ToolResult.create_error(
                    f"Export to '{fmt}' failed: {exc}. "
                    "Verify the graph data is valid by calling kaos-graph-info first. "
                    "For RDF formats (turtle, ntriples), ensure edges have IRI-compatible IDs. "
                    "Try a different format with kaos-graph-export."
                )

            return ToolResult.create_success(output)

    # ── 6. kaos-graph-info ────────────────────────────────────────────

    class GraphInfoTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-info",
                display_name="Graph Info",
                description=(
                    "Get information about a graph: node count, edge count, "
                    "is_directed, is_dag, is_connected, is_tree, density. "
                    "Requires graph_json from kaos-graph-create or kaos-graph-load-rdf."
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
                g = Graph.from_json(inputs["graph_json"], settings=_settings_for(context))
            except Exception as exc:
                logger.debug("Failed to load graph in kaos-graph-info: %s", exc)
                return ToolResult.create_error(
                    f"Failed to load graph: {exc}. "
                    "Pass the 'graph_data' field from a kaos-graph-create or "
                    "kaos-graph-load-rdf result. "
                    "Alternatively, call kaos-graph-create with a new JSON definition."
                )

            info = {
                "name": g.name,
                "n_nodes": g.n_nodes,
                "n_edges": g.n_edges,
                "is_directed": g.is_directed,
                "is_dag": g.is_dag(),
                "is_connected": g.is_connected(),
                "is_tree": g.is_tree(),
                "density": algorithms.density(g),
            }
            summary = (
                f"Graph '{g.name}': {g.n_nodes} nodes, {g.n_edges} edges, "
                f"directed={g.is_directed}, dag={info['is_dag']}, "
                f"connected={info['is_connected']}, "
                f"density={info['density']:.4f}"
            )
            return ToolResult.create_success(info, summary=summary)

    # ── 7. kaos-graph-visualize ───────────────────────────────────────

    class GraphVisualizeTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-visualize",
                display_name="Visualize Graph",
                description=(
                    "Generate a Mermaid flowchart diagram from a graph. "
                    "The output can be rendered in any Mermaid-compatible viewer. "
                    "Requires graph_json from kaos-graph-create or kaos-graph-load-rdf. "
                    "For other formats, use kaos-graph-export."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.GENERATE,
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
                        name="max_nodes",
                        type="integer",
                        description="Maximum nodes to render (default 50, truncates with note).",
                        required=False,
                        default=50,
                    ),
                    ParameterSchema(
                        name="direction",
                        type="string",
                        description="Flow direction: TB, BT, LR, RL.",
                        required=False,
                        default="TB",
                        constraints={"enum": ["TB", "BT", "LR", "RL"]},
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            from kaos_graph.graph import Graph
            from kaos_graph.io import to_mermaid

            try:
                g = Graph.from_json(inputs["graph_json"], settings=_settings_for(context))
            except Exception as exc:
                logger.debug("Failed to load graph in kaos-graph-visualize: %s", exc)
                return ToolResult.create_error(
                    f"Failed to load graph: {exc}. "
                    "Pass the 'graph_data' field from a kaos-graph-create or "
                    "kaos-graph-load-rdf result. "
                    "Alternatively, call kaos-graph-create with a new JSON definition."
                )

            max_nodes = inputs.get("max_nodes", 50)
            direction = inputs.get("direction", "TB")

            mermaid = to_mermaid(g, max_nodes=max_nodes, direction=direction)
            return ToolResult.create_success(mermaid)

    # ── 8. kaos-graph-transform ──────────────────────────────────────

    class GraphTransformTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-transform",
                display_name="Transform Graph",
                description=(
                    "Apply a structural transformation to a graph. "
                    "Operations: 'subgraph' (extract nodes), 'ego_graph' (neighborhood), "
                    "'reverse' (flip edge directions), 'to_undirected' (drop directionality), "
                    "'condensation' (contract SCCs into single nodes). "
                    "Requires graph_json from kaos-graph-create or kaos-graph-load-rdf. "
                    "Returns the transformed graph as JSON for use with other tools."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.TRANSFORM,
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
                        name="operation",
                        type="string",
                        description="Transformation operation to apply.",
                        constraints={
                            "enum": [
                                "subgraph",
                                "ego_graph",
                                "reverse",
                                "to_undirected",
                                "condensation",
                            ]
                        },
                    ),
                    ParameterSchema(
                        name="nodes",
                        type="array",
                        description="Node IDs for 'subgraph' operation.",
                        required=False,
                    ),
                    ParameterSchema(
                        name="center",
                        type="string",
                        description="Center node ID for 'ego_graph' operation.",
                        required=False,
                    ),
                    ParameterSchema(
                        name="radius",
                        type="integer",
                        description="Radius (hops) for 'ego_graph' operation (default 1).",
                        required=False,
                        default=1,
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            from kaos_graph import algorithms
            from kaos_graph.graph import Graph

            try:
                g = Graph.from_json(inputs["graph_json"], settings=_settings_for(context))
            except Exception as exc:
                logger.debug("Failed to load graph in kaos-graph-transform: %s", exc)
                return ToolResult.create_error(
                    f"Failed to load graph: {exc}. "
                    "Pass the 'graph_data' field from a kaos-graph-create or "
                    "kaos-graph-load-rdf result. "
                    "Alternatively, call kaos-graph-create with a new JSON definition."
                )

            operation = inputs["operation"]
            try:
                if operation == "subgraph":
                    node_ids = inputs.get("nodes")
                    if not node_ids or not isinstance(node_ids, list):
                        return ToolResult.create_error(
                            "'subgraph' requires a 'nodes' array of node IDs. "
                            "Pass a JSON array of node IDs to extract. "
                            "Use kaos-graph-query to list available nodes first."
                        )
                    result_graph = g.subgraph(node_ids)
                elif operation == "ego_graph":
                    center = inputs.get("center")
                    if not center:
                        return ToolResult.create_error(
                            "'ego_graph' requires a 'center' node ID. "
                            "Pass the node ID as the 'center' parameter. "
                            "Use kaos-graph-query to list available nodes first."
                        )
                    if not g.has_node(center):
                        return ToolResult.create_error(
                            f"Center node '{center}' not found in the graph. "
                            "Verify the node ID exists by calling "
                            "kaos-graph-query with query_type='node'. "
                            "Use kaos-graph-info to see the total node count."
                        )
                    radius = inputs.get("radius", 1)
                    result_graph = g.ego_graph(center, radius=radius)
                elif operation == "reverse":
                    result_graph = g.reverse()
                elif operation == "to_undirected":
                    result_graph = g.to_undirected()
                elif operation == "condensation":
                    result_graph = algorithms.condensation(g)
                else:
                    return ToolResult.create_error(
                        f"Unknown operation '{operation}'. "
                        "Supported: subgraph, ego_graph, reverse, to_undirected, condensation."
                    )
            except (ValueError, KeyError) as exc:
                logger.debug("Transform '%s' failed: %s", operation, exc)
                return ToolResult.create_error(
                    f"Transform '{operation}' failed: {exc}. "
                    "Check that the graph and parameters are valid. "
                    "For 'subgraph', ensure all node IDs exist in the graph. "
                    "For 'ego_graph', verify the center node exists. "
                    "Use kaos-graph-info to inspect the graph first."
                )

            info = {
                "operation": operation,
                "n_nodes": result_graph.n_nodes,
                "n_edges": result_graph.n_edges,
                "is_directed": result_graph.is_directed,
                "graph_data": result_graph.to_json(),
            }
            summary = (
                f"Transform '{operation}': "
                f"{result_graph.n_nodes} nodes, {result_graph.n_edges} edges."
            )
            return ToolResult.create_success(info, summary=summary)

    # ── 9. kaos-graph-trace-to-graph ─────────────────────────────────

    class TraceToGraphTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-trace-to-graph",
                display_name="Trace to Graph",
                description=(
                    "Convert a kaos-llm-core ExecutionTrace to a data-flow graph "
                    "with timing and cost properties on each node. "
                    "The resulting DAG supports critical_path analysis via "
                    "kaos-graph-critical-path. "
                    "Requires the 'programs' extra (kaos-llm-core)."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.TRANSFORM,
                module_name=_MODULE,
                version=_VERSION,
                annotations=_READONLY,
                input_schema=[
                    ParameterSchema(
                        name="trace_json",
                        type="string",
                        description=(
                            "JSON-serialized ExecutionTrace from kaos-llm-core. "
                            "Must include call_name, trace_id, children, "
                            "latency_ms, cost_usd, and token counts."
                        ),
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            try:
                from kaos_llm_core.observability.traces import (  # ty: ignore[unresolved-import]
                    ExecutionTrace,
                )
            except ImportError:
                return ToolResult.create_error(
                    "kaos-llm-core is required for trace_to_graph. "
                    "Install with: pip install kaos-graph[programs]"
                )

            try:
                from kaos_graph.programs.convert import trace_to_graph

                trace_data = _capped_json_loads(inputs["trace_json"], context, "trace")
                trace = ExecutionTrace(**trace_data)
                g = trace_to_graph(trace)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                return ToolResult.create_error(
                    f"Failed to parse trace JSON: {exc}. "
                    "Provide a valid ExecutionTrace JSON object."
                )
            except Exception as exc:
                logger.debug("Failed to convert trace to graph: %s", exc)
                return ToolResult.create_error(
                    f"Failed to convert trace to graph: {exc}. "
                    "Ensure the trace JSON has the expected ExecutionTrace structure "
                    "(call_name, trace_id, children, latency_ms, cost_usd, token counts). "
                    "Obtain a valid trace from kaos-llm-core's observability module."
                )

            info = {
                "n_nodes": g.n_nodes,
                "n_edges": g.n_edges,
                "graph_data": g.to_json(),
            }
            summary = f"Converted trace to graph: {g.n_nodes} nodes, {g.n_edges} edges."
            return ToolResult.create_success(info, summary=summary)

    # ── 10. kaos-graph-validate-schema ───────────────────────────────

    class ValidateSchemaTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-validate-schema",
                display_name="Validate Graph Schema",
                description=(
                    "Validate a graph against a schema definition. "
                    "The schema specifies allowed node_types (with required/optional "
                    "properties) and edge_types (with source/target type constraints "
                    "and required properties). "
                    "Returns {valid: bool, violations: [...]}. "
                    "Use after kaos-graph-create or kaos-graph-load-rdf."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.VALIDATE,
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
                        name="schema_json",
                        type="string",
                        description=(
                            'Schema JSON: {"node_types": [{"name": "person", '
                            '"required_properties": ["age"]}], '
                            '"edge_types": [{"name": "knows", '
                            '"source_type": "person", "target_type": "person"}]}'
                        ),
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            from kaos_graph.graph import Graph
            from kaos_graph.schema import EdgeType, GraphSchema, NodeType

            try:
                g = Graph.from_json(inputs["graph_json"], settings=_settings_for(context))
            except Exception as exc:
                logger.debug("Failed to load graph in kaos-graph-validate-schema: %s", exc)
                return ToolResult.create_error(
                    f"Failed to load graph: {exc}. "
                    "Pass the 'graph_data' field from a kaos-graph-create or "
                    "kaos-graph-load-rdf result. "
                    "Alternatively, call kaos-graph-create with a new JSON definition."
                )

            try:
                schema_data = _capped_json_loads(inputs["schema_json"], context, "schema")
            except json.JSONDecodeError as exc:
                return ToolResult.create_error(
                    f"Invalid schema JSON: {exc}. "
                    "Provide a JSON object with 'node_types' and/or 'edge_types'."
                )

            try:
                node_types = [
                    NodeType(
                        name=nt["name"],
                        required_properties=nt.get("required_properties", []),
                        optional_properties=nt.get("optional_properties", []),
                    )
                    for nt in schema_data.get("node_types", [])
                ]
                edge_types = [
                    EdgeType(
                        name=et["name"],
                        source_type=et.get("source_type"),
                        target_type=et.get("target_type"),
                        required_properties=et.get("required_properties", []),
                    )
                    for et in schema_data.get("edge_types", [])
                ]
                schema = GraphSchema(node_types=node_types, edge_types=edge_types)
            except (KeyError, TypeError) as exc:
                return ToolResult.create_error(
                    f"Invalid schema definition: {exc}. "
                    "Each node_type needs 'name'. Each edge_type needs 'name'."
                )

            violations = schema.validate(g)
            violation_dicts = [
                {"kind": v.kind, "element_id": v.element_id, "message": v.message}
                for v in violations
            ]
            valid = len(violations) == 0
            info = {
                "valid": valid,
                "violation_count": len(violations),
                "violations": violation_dicts,
            }
            summary = (
                f"Schema validation: {'PASSED' if valid else 'FAILED'} "
                f"({len(violations)} violation(s))."
            )
            return ToolResult.create_success(info, summary=summary)

    # ── 11. kaos-graph-load-adjacency ────────────────────────────────

    class LoadAdjacencyTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-load-adjacency",
                display_name="Load Adjacency JSON",
                description=(
                    "Load a graph from adjacency-list JSON format. "
                    'Input: {"nodes": {"a": {...}}, "edges": {"a": [["b", {...}]]}}. '
                    "Returns graph info and the graph_data JSON for use with other tools. "
                    "For standard graph JSON, use kaos-graph-create instead."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.EXTRACT,
                module_name=_MODULE,
                version=_VERSION,
                annotations=_READONLY,
                input_schema=[
                    ParameterSchema(
                        name="adjacency_json",
                        type="string",
                        description=(
                            "Adjacency-list JSON: "
                            '{"nodes": {"a": {}, "b": {}}, '
                            '"edges": {"a": [["b", {"weight": 1.0}]]}, '
                            '"directed": true}'
                        ),
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            from kaos_graph.io.adjacency import load_adjacency_json

            try:
                # A2-followup-#2: byte-cap the input before the underlying
                # json.loads + Graph construction so adjacency-form payloads
                # share the same DoS bounds as Graph.from_json.
                adjacency_data = inputs["adjacency_json"]
                _capped_json_loads(adjacency_data, context, "adjacency")
                g = load_adjacency_json(adjacency_data)
            except (ValueError, KeyError, TypeError) as exc:
                return ToolResult.create_error(
                    f"Failed to load adjacency JSON: {exc}. "
                    "Provide a JSON object with 'nodes' (id->props) "
                    "and 'edges' (source->[[target, props]])."
                )

            info = {
                "n_nodes": g.n_nodes,
                "n_edges": g.n_edges,
                "is_directed": g.is_directed,
                "graph_data": g.to_json(),
            }
            summary = (
                f"Loaded adjacency graph: "
                f"{g.n_nodes} nodes, {g.n_edges} edges "
                f"(directed={g.is_directed})."
            )
            return ToolResult.create_success(info, summary=summary)

    # ── 12. kaos-graph-load-rdf-string ───────────────────────────────

    class LoadRdfStringTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-load-rdf-string",
                display_name="Load RDF from String",
                description=(
                    "Load RDF data from an inline string (Turtle, N-Triples, or RDF/XML). "
                    "Unlike kaos-graph-load-rdf which reads from a file path, this tool "
                    "accepts RDF content directly. "
                    "Returns graph info and graph_data JSON for use with other tools."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.EXTRACT,
                module_name=_MODULE,
                version=_VERSION,
                annotations=_READONLY,
                input_schema=[
                    ParameterSchema(
                        name="rdf_data",
                        type="string",
                        description="RDF content string (Turtle, N-Triples, or RDF/XML).",
                    ),
                    ParameterSchema(
                        name="format",
                        type="string",
                        description="RDF serialization format.",
                        constraints={"enum": ["turtle", "ntriples", "rdfxml"]},
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            from kaos_graph.rdf import load_rdf
            from kaos_graph.settings import KaosGraphSettings

            rdf_data = inputs["rdf_data"]
            fmt = inputs["format"]
            settings = KaosGraphSettings.from_context(context)

            try:
                g, stats = load_rdf(rdf_data, format=fmt, settings=settings)
            except Exception as exc:
                logger.debug("Failed to parse RDF string (format=%s): %s", fmt, exc)
                return ToolResult.create_error(
                    f"Failed to parse RDF string: {exc}. "
                    "Ensure the data is valid RDF in the specified format "
                    "(turtle, ntriples, or rdfxml). "
                    "For loading from a file path, use kaos-graph-load-rdf instead."
                )

            info = {
                "n_nodes": g.n_nodes,
                "n_edges": g.n_edges,
                "is_directed": g.is_directed,
                "stats": {
                    "total_triples": stats.total_triples,
                    "nodes": stats.nodes,
                    "edges": stats.edges,
                    "literal_properties": stats.literal_properties,
                    "load_time_ms": stats.load_time_ms,
                },
                "graph_data": g.to_json(),
            }
            summary = (
                f"Loaded RDF string ({fmt}): "
                f"{stats.total_triples} triples -> "
                f"{g.n_nodes} nodes, {g.n_edges} edges."
            )
            return ToolResult.create_success(info, summary=summary)

    # ── 13. kaos-graph-sparql ────────────────────────────────────────

    class SparqlTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-sparql",
                display_name="SPARQL Query",
                description=(
                    "Execute a SPARQL SELECT query over a graph. "
                    "Requires the 'rdf' extra (pyoxigraph). "
                    "The graph is converted to an in-memory RDF store; edges become triples "
                    "using the edge's 'predicate' property as the predicate IRI. "
                    "Returns query results as {variables: [...], rows: [...]}."
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
                        name="query",
                        type="string",
                        description=(
                            "SPARQL SELECT query string. Example: "
                            "'SELECT ?s ?o WHERE { ?s <http://example.org/knows> ?o }'"
                        ),
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            from kaos_graph.graph import Graph

            try:
                g = Graph.from_json(inputs["graph_json"], settings=_settings_for(context))
            except Exception as exc:
                logger.debug("Failed to load graph in kaos-graph-sparql: %s", exc)
                return ToolResult.create_error(
                    f"Failed to load graph: {exc}. "
                    "Pass the 'graph_data' field from a kaos-graph-create or "
                    "kaos-graph-load-rdf result. "
                    "Alternatively, call kaos-graph-create with a new JSON definition."
                )

            try:
                from kaos_graph.rdf.sparql import query_sparql
            except ImportError:
                return ToolResult.create_error(
                    "SPARQL support requires pyoxigraph. "
                    "Install with: pip install kaos-graph[rdf]. "
                    "Alternative: use kaos-graph-query for simple node/neighbor lookups, "
                    "or kaos-graph-find-patterns for property-based filtering."
                )

            query = inputs["query"]
            try:
                # A2-followup-#3: thread per-request settings through to
                # SPARQL so query-byte / row-count / wall-clock-time caps
                # apply to MCP-exposed evaluation.
                result = query_sparql(g, query, settings=_settings_for(context))
            except ValueError as exc:
                return ToolResult.create_error(
                    f"SPARQL query failed: {exc}. "
                    "Check your query syntax. Only SELECT queries are supported; "
                    "use a standard SPARQL SELECT form."
                )
            except Exception as exc:
                logger.debug("SPARQL query error: %s", exc)
                return ToolResult.create_error(
                    f"SPARQL query error: {exc}. "
                    "Check the query syntax and ensure the graph has RDF-compatible "
                    "edge predicates. For simple lookups, use kaos-graph-query or "
                    "kaos-graph-find-patterns instead."
                )

            info = {
                "variables": result.variables,
                "rows": result.rows,
                "row_count": len(result.rows),
            }
            summary = (
                f"SPARQL query returned {len(result.rows)} row(s) "
                f"with variables: {', '.join(result.variables)}."
            )
            return ToolResult.create_success(info, summary=summary)

    # ── 14. kaos-graph-export-adjacency ──────────────────────────────

    class ExportAdjacencyTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-export-adjacency",
                display_name="Export Adjacency JSON",
                description=(
                    "Export a graph to adjacency-list JSON format. "
                    "Output: {nodes: {id: props}, edges: {source: [[target, props]]}}. "
                    "This is an alternative to the standard graph JSON format. "
                    "For other formats, use kaos-graph-export."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.TRANSFORM,
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
            from kaos_graph.graph import Graph
            from kaos_graph.io.adjacency import to_adjacency_json

            try:
                g = Graph.from_json(inputs["graph_json"], settings=_settings_for(context))
            except Exception as exc:
                logger.debug("Failed to load graph in kaos-graph-export-adjacency: %s", exc)
                return ToolResult.create_error(
                    f"Failed to load graph: {exc}. "
                    "Pass the 'graph_data' field from a kaos-graph-create or "
                    "kaos-graph-load-rdf result. "
                    "Alternatively, call kaos-graph-create with a new JSON definition."
                )

            try:
                adjacency = to_adjacency_json(g)
            except Exception as exc:
                logger.debug("Failed to export adjacency JSON: %s", exc)
                return ToolResult.create_error(
                    f"Failed to export adjacency JSON: {exc}. "
                    "Verify the graph data is valid by calling kaos-graph-info first. "
                    "For other export formats, try kaos-graph-export."
                )

            return ToolResult.create_success(adjacency)

    # ── 15. kaos-graph-critical-path ─────────────────────────────────

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
                g = Graph.from_json(inputs["graph_json"], settings=_settings_for(context))
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

    # ── 16. kaos-graph-find-patterns ─────────────────────────────────

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
                g = Graph.from_json(inputs["graph_json"], settings=_settings_for(context))
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

    # ── 17. kaos-graph-stats ─────────────────────────────────────────

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
                g = Graph.from_json(inputs["graph_json"], settings=_settings_for(context))
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

            # Compute degree statistics
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

    tool_classes = [
        GraphCreateTool,
        GraphQueryTool,
        GraphAlgorithmTool,
        GraphLoadRdfTool,
        GraphExportTool,
        GraphInfoTool,
        GraphVisualizeTool,
        GraphTransformTool,
        TraceToGraphTool,
        ValidateSchemaTool,
        LoadAdjacencyTool,
        LoadRdfStringTool,
        SparqlTool,
        ExportAdjacencyTool,
        CriticalPathTool,
        FindPatternsTool,
        GraphStatsTool,
    ]

    count = 0
    for cls in tool_classes:
        runtime.tools.register_tool(cls())
        count += 1
    return count
