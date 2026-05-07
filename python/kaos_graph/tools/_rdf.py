"""RDF / SPARQL MCP tools.

Tools registered here:

- ``kaos-graph-load-rdf``        — load an RDF/OWL file from disk
- ``kaos-graph-load-rdf-string`` — parse an inline RDF string
- ``kaos-graph-sparql``          — SPARQL SELECT over a kaos-graph Graph
"""

from __future__ import annotations

from typing import Any

from kaos_graph.tools._common import (
    _MODULE,
    _VERSION,
    get_logger,
    readonly_annotations,
    settings_for,
)

__all__ = ["register_rdf_tools"]

logger = get_logger()


def register_rdf_tools(runtime: Any) -> int:
    """Register the 3 RDF/SPARQL tools with ``runtime``."""
    from kaos_core.base.context import KaosContext
    from kaos_core.base.tool import KaosTool
    from kaos_core.types.enums import ToolCapability, ToolCategory
    from kaos_core.types.metadata import ToolMetadata
    from kaos_core.types.parameters import ParameterSchema
    from kaos_core.types.results import ToolResult

    _READONLY = readonly_annotations()

    # ── kaos-graph-load-rdf ───────────────────────────────────────────

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

            from pathlib import Path as _Path

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
            summary = (
                f"Loaded RDF from '{_Path(path).name}': "
                f"{stats.total_triples} triples -> "
                f"{g.n_nodes} nodes, {g.n_edges} edges "
                f"(in {stats.load_time_ms}ms)."
            )
            return ToolResult.create_success(info, summary=summary)

    # ── kaos-graph-load-rdf-string ───────────────────────────────────

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

    # ── kaos-graph-sparql ────────────────────────────────────────────

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
                g = Graph.from_json(inputs["graph_json"], settings=settings_for(context))
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
                result = query_sparql(g, query)
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

    # ── Registration ──────────────────────────────────────────────────

    tool_classes: list[type[KaosTool]] = [
        GraphLoadRdfTool,
        LoadRdfStringTool,
        SparqlTool,
    ]
    for cls in tool_classes:
        runtime.tools.register_tool(cls())
    return len(tool_classes)
