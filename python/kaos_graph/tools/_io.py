"""Import / export MCP tools.

Tools registered here:

- ``kaos-graph-export``            — JSON / Mermaid / DOT / RDF / GraphML / GEXF
- ``kaos-graph-visualize``         — Mermaid flowchart diagram
- ``kaos-graph-load-adjacency``    — load adjacency-list JSON
- ``kaos-graph-export-adjacency``  — export adjacency-list JSON

Audit-01 KG-005: text/diagram/export tools return ``ToolResult.create_success``
with a structured ``output`` dict (machine-readable metadata) **and** a
``summary`` string. That gives agents both the rendered payload (in the
``output`` field) and one-line context (in ``summary``), which is more
useful than a bare ``create_success(plain_string)`` that drops the metadata.
"""

from __future__ import annotations

from typing import Any

from kaos_graph.tools._common import (
    _EXPORT_FORMATS,
    _MODULE,
    _VERSION,
    get_logger,
    readonly_annotations,
    settings_for,
)

__all__ = ["register_io_tools"]

logger = get_logger()


def register_io_tools(runtime: Any) -> int:
    """Register the 4 import/export tools with ``runtime``."""
    from kaos_core.base.context import KaosContext
    from kaos_core.base.tool import KaosTool
    from kaos_core.types.enums import ToolCapability, ToolCategory
    from kaos_core.types.metadata import ToolMetadata
    from kaos_core.types.parameters import ParameterSchema
    from kaos_core.types.results import ToolResult

    _READONLY = readonly_annotations()

    # ── kaos-graph-export ─────────────────────────────────────────────

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
                g = Graph.from_json(inputs["graph_json"], settings=settings_for(context))
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

            # KG-005: structured success carries both the rendered payload and
            # machine-readable metadata. Agents can read .text (summary) for a
            # one-liner or .structuredContent['output'] for the full export.
            return ToolResult.create_success(
                {
                    "format": fmt,
                    "output": output,
                    "n_nodes": g.n_nodes,
                    "n_edges": g.n_edges,
                    "n_bytes": len(output),
                },
                summary=f"Exported graph as {fmt} ({g.n_nodes} nodes, {g.n_edges} edges).",
            )

    # ── kaos-graph-visualize ─────────────────────────────────────────

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
                g = Graph.from_json(inputs["graph_json"], settings=settings_for(context))
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
            truncated = g.n_nodes > max_nodes

            # KG-005: see GraphExportTool for the structured-success rationale.
            return ToolResult.create_success(
                {
                    "format": "mermaid",
                    "diagram": mermaid,
                    "n_nodes": g.n_nodes,
                    "n_edges": g.n_edges,
                    "max_nodes": max_nodes,
                    "direction": direction,
                    "truncated": truncated,
                },
                summary=(
                    f"Rendered Mermaid flowchart ({direction}) for "
                    f"{g.n_nodes} nodes, {g.n_edges} edges"
                    + (f"; truncated to first {max_nodes} nodes." if truncated else ".")
                ),
            )

    # ── kaos-graph-load-adjacency ────────────────────────────────────

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

            settings = settings_for(context)
            try:
                g = load_adjacency_json(inputs["adjacency_json"], settings=settings)
            except (ValueError, KeyError, TypeError) as exc:
                return ToolResult.create_error(
                    f"Failed to load adjacency JSON: {exc}. "
                    "Provide a JSON object with 'nodes' (id->props) "
                    "and 'edges' (source->[[target, props]]). "
                    "If the graph exceeds the configured caps, raise "
                    "KAOS_GRAPH_MAX_BYTES / KAOS_GRAPH_MAX_NODES / "
                    "KAOS_GRAPH_MAX_EDGES, or use kaos-graph-load-rdf for "
                    "file-backed loading."
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

    # ── kaos-graph-export-adjacency ──────────────────────────────────

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
                g = Graph.from_json(inputs["graph_json"], settings=settings_for(context))
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

            # KG-005: structured success — see GraphExportTool for rationale.
            return ToolResult.create_success(
                {
                    "format": "adjacency",
                    "adjacency_json": adjacency,
                    "n_nodes": g.n_nodes,
                    "n_edges": g.n_edges,
                    "n_bytes": len(adjacency),
                },
                summary=(f"Exported adjacency JSON ({g.n_nodes} nodes, {g.n_edges} edges)."),
            )

    # ── Registration ──────────────────────────────────────────────────

    tool_classes: list[type[KaosTool]] = [
        GraphExportTool,
        GraphVisualizeTool,
        LoadAdjacencyTool,
        ExportAdjacencyTool,
    ]
    for cls in tool_classes:
        runtime.tools.register_tool(cls())
    return len(tool_classes)
