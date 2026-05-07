"""Core graph-manipulation MCP tools.

Tools registered here:

- ``kaos-graph-create``           — build a graph from JSON
- ``kaos-graph-query``            — node / neighbor lookup
- ``kaos-graph-info``             — high-level graph properties
- ``kaos-graph-transform``        — structural transforms (subgraph, ego, …)
- ``kaos-graph-validate-schema``  — typed schema check
"""

from __future__ import annotations

import json
from typing import Any

from kaos_graph.tools._common import (
    _MODULE,
    _VERSION,
    get_logger,
    graph_from_json,
    readonly_annotations,
    settings_for,
)

__all__ = ["register_core_tools"]

logger = get_logger()


def register_core_tools(runtime: Any) -> int:
    """Register the 5 core graph-manipulation tools with ``runtime``.

    All ``kaos-core`` imports happen inside this function so that
    ``import kaos_graph.tools._core`` stays cheap on the standalone path.
    """
    from kaos_core.base.context import KaosContext
    from kaos_core.base.tool import KaosTool
    from kaos_core.types.enums import ToolCapability, ToolCategory
    from kaos_core.types.metadata import ToolMetadata
    from kaos_core.types.parameters import ParameterSchema
    from kaos_core.types.results import ToolResult

    _READONLY = readonly_annotations()

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
                g = graph_from_json(graph_json, context=context)
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
                g = Graph.from_json(inputs["graph_json"], settings=settings_for(context))
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

    # ── 3. kaos-graph-info ────────────────────────────────────────────

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
                g = Graph.from_json(inputs["graph_json"], settings=settings_for(context))
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

    # ── 4. kaos-graph-transform ──────────────────────────────────────

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
                g = Graph.from_json(inputs["graph_json"], settings=settings_for(context))
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

    # ── 5. kaos-graph-validate-schema ────────────────────────────────

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
                g = Graph.from_json(inputs["graph_json"], settings=settings_for(context))
            except Exception as exc:
                logger.debug("Failed to load graph in kaos-graph-validate-schema: %s", exc)
                return ToolResult.create_error(
                    f"Failed to load graph: {exc}. "
                    "Pass the 'graph_data' field from a kaos-graph-create or "
                    "kaos-graph-load-rdf result. "
                    "Alternatively, call kaos-graph-create with a new JSON definition."
                )

            try:
                schema_data = json.loads(inputs["schema_json"])
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

    # ── Registration ──────────────────────────────────────────────────

    tool_classes: list[type[KaosTool]] = [
        GraphCreateTool,
        GraphQueryTool,
        GraphInfoTool,
        GraphTransformTool,
        ValidateSchemaTool,
    ]
    for cls in tool_classes:
        runtime.tools.register_tool(cls())
    return len(tool_classes)
