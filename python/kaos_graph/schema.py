"""Graph schema validation."""

from __future__ import annotations

from dataclasses import dataclass, field

from kaos_graph.graph import Graph

__all__ = ["EdgeType", "GraphSchema", "NodeType", "SchemaViolation"]


@dataclass(frozen=True, slots=True)
class NodeType:
    """Definition of a node type in a graph schema."""

    name: str
    required_properties: list[str] = field(default_factory=list)
    optional_properties: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class EdgeType:
    """Definition of an edge type in a graph schema."""

    name: str
    source_type: str | None = None  # required node type for source
    target_type: str | None = None  # required node type for target
    required_properties: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SchemaViolation:
    """A single schema violation."""

    kind: str
    # "missing_property", "invalid_source_type", "invalid_target_type",
    # "unknown_node_type", "unknown_edge_type"
    element_id: str  # node or edge identifier
    message: str


@dataclass
class GraphSchema:
    """Schema for validating graph structure."""

    node_types: list[NodeType] = field(default_factory=list)
    edge_types: list[EdgeType] = field(default_factory=list)

    def validate(self, graph: Graph) -> list[SchemaViolation]:
        """Validate a graph against this schema. Returns list of violations (empty = valid)."""
        violations: list[SchemaViolation] = []

        node_type_map = {nt.name: nt for nt in self.node_types}
        edge_type_map = {et.name: et for et in self.edge_types}

        # Validate nodes
        for node_id in graph.node_ids():
            node = graph.node(node_id)
            props = node.properties if node else {}
            node_type_name = props.get("type")

            if node_type_name and self.node_types:
                if node_type_name not in node_type_map:
                    violations.append(
                        SchemaViolation(
                            kind="unknown_node_type",
                            element_id=node_id,
                            message=(
                                f"Node '{node_id}' has type '{node_type_name}'"
                                " which is not in the schema"
                            ),
                        )
                    )
                else:
                    nt = node_type_map[node_type_name]
                    for req_prop in nt.required_properties:
                        if req_prop not in props:
                            violations.append(
                                SchemaViolation(
                                    kind="missing_property",
                                    element_id=node_id,
                                    message=(
                                        f"Node '{node_id}' of type '{node_type_name}'"
                                        f" is missing required property '{req_prop}'"
                                    ),
                                )
                            )

        # Validate edges
        for edge in graph.edges():
            edge_type_name = edge.properties.get("type")

            if edge_type_name and self.edge_types:
                if edge_type_name not in edge_type_map:
                    violations.append(
                        SchemaViolation(
                            kind="unknown_edge_type",
                            element_id=f"{edge.source}->{edge.target}",
                            message=(
                                f"Edge '{edge.source}'->'{edge.target}' has type"
                                f" '{edge_type_name}'"
                                " which is not in the schema"
                            ),
                        )
                    )
                else:
                    et = edge_type_map[edge_type_name]

                    # Check source type constraint
                    if et.source_type:
                        src_node = graph.node(edge.source)
                        src_props = src_node.properties if src_node else {}
                        src_type = src_props.get("type")
                        if src_type != et.source_type:
                            violations.append(
                                SchemaViolation(
                                    kind="invalid_source_type",
                                    element_id=f"{edge.source}->{edge.target}",
                                    message=(
                                        f"Edge type '{edge_type_name}' requires source type"
                                        f" '{et.source_type}' but '{edge.source}'"
                                        f" has type '{src_type}'"
                                    ),
                                )
                            )

                    # Check target type constraint
                    if et.target_type:
                        tgt_node = graph.node(edge.target)
                        tgt_props = tgt_node.properties if tgt_node else {}
                        tgt_type = tgt_props.get("type")
                        if tgt_type != et.target_type:
                            violations.append(
                                SchemaViolation(
                                    kind="invalid_target_type",
                                    element_id=f"{edge.source}->{edge.target}",
                                    message=(
                                        f"Edge type '{edge_type_name}' requires target type"
                                        f" '{et.target_type}' but '{edge.target}'"
                                        f" has type '{tgt_type}'"
                                    ),
                                )
                            )

                    # Check required properties
                    for req_prop in et.required_properties:
                        if req_prop not in edge.properties:
                            violations.append(
                                SchemaViolation(
                                    kind="missing_property",
                                    element_id=f"{edge.source}->{edge.target}",
                                    message=(
                                        f"Edge '{edge.source}'->'{edge.target}' of type"
                                        f" '{edge_type_name}' is missing required"
                                        f" property '{req_prop}'"
                                    ),
                                )
                            )

        return violations
