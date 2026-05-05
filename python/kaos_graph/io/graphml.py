"""GraphML import/export using Python's stdlib xml.etree.ElementTree.

GraphML is an XML-based file format for graphs. This module supports:
- Directed and undirected graphs
- Node and edge properties as GraphML ``<data>`` elements
- Round-trip fidelity for string, numeric, and boolean properties

Reference: http://graphml.graphdrawing.org/
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET  # used for *output* construction only
from typing import TYPE_CHECKING, Any

from defusedxml.ElementTree import fromstring as _safe_fromstring

from kaos_graph.errors import InvalidFormatError

# A2-#6: hard cap on input XML size to bound peak memory before defusedxml
# even sees the document. 32 MiB is generous for legitimate GraphML and small
# enough to refuse pathological inputs from MCP/HTTP callers.
_MAX_GRAPHML_BYTES = 32 * 1024 * 1024

if TYPE_CHECKING:
    from kaos_graph.graph import Graph

_GRAPHML_NS = "http://graphml.graphdrawing.org/xmlns"
_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_SCHEMA_LOC = (
    "http://graphml.graphdrawing.org/xmlns http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd"
)


def _infer_graphml_type(value: Any) -> str:
    """Map a Python value to a GraphML attr.type string."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "long"
    if isinstance(value, float):
        return "double"
    return "string"


def _serialize_value(value: Any) -> str:
    """Serialize a property value for GraphML data element text."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    # Complex values (lists, dicts) -> JSON
    return json.dumps(value)


def _deserialize_value(text: str, attr_type: str) -> Any:
    """Deserialize a GraphML data element text to a Python value."""
    if attr_type == "boolean":
        return text.lower() in ("true", "1")
    if attr_type in ("int", "long"):
        return int(text)
    if attr_type in ("float", "double"):
        return float(text)
    # For string-typed attributes, try JSON parse to recover structured data
    # (dicts, lists, and numeric values serialized as strings in mixed-type keys)
    if attr_type == "string":
        try:
            parsed = json.loads(text)
            # Only recover dicts and lists; leave plain strings as-is
            if isinstance(parsed, (dict, list)):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return text


def to_graphml(graph: Graph) -> str:
    """Export a graph as a GraphML XML string.

    Node IDs and all properties are preserved. Properties are emitted
    as ``<data>`` elements with auto-detected types.

    Args:
        graph: The graph to export.

    Returns:
        A GraphML XML string.
    """
    # Collect all property keys across nodes and edges, tracking all value types
    node_key_types: dict[str, set[str]] = {}  # key_name -> set of graphml_types seen
    edge_key_types: dict[str, set[str]] = {}
    node_has_complex: dict[str, bool] = {}  # key_name -> True if any dict/list value
    edge_has_complex: dict[str, bool] = {}

    for nid in graph.node_ids():
        node = graph.node(nid)
        node_props = node.properties if node else {}
        for k, v in node_props.items():
            node_key_types.setdefault(k, set()).add(_infer_graphml_type(v))
            if isinstance(v, (dict, list)):
                node_has_complex[k] = True

    for edge in graph.edges():
        for k, v in edge.properties.items():
            edge_key_types.setdefault(k, set()).add(_infer_graphml_type(v))
            if isinstance(v, (dict, list)):
                edge_has_complex[k] = True

    # Resolve final types: use "string" when types are mixed or any value is complex
    node_keys: dict[str, str] = {}
    for k, types in node_key_types.items():
        if len(types) > 1 or node_has_complex.get(k, False):
            node_keys[k] = "string"
        else:
            node_keys[k] = next(iter(types))

    edge_keys: dict[str, str] = {}
    for k, types in edge_key_types.items():
        if len(types) > 1 or edge_has_complex.get(k, False):
            edge_keys[k] = "string"
        else:
            edge_keys[k] = next(iter(types))

    # Build XML
    root = ET.Element("graphml")
    root.set("xmlns", _GRAPHML_NS)
    root.set("xmlns:xsi", _XSI_NS)
    root.set("xsi:schemaLocation", _SCHEMA_LOC)

    # Declare node keys
    for key_name, key_type in sorted(node_keys.items()):
        key_el = ET.SubElement(root, "key")
        key_el.set("id", f"n_{key_name}")
        key_el.set("for", "node")
        key_el.set("attr.name", key_name)
        key_el.set("attr.type", key_type)

    # Declare edge keys
    for key_name, key_type in sorted(edge_keys.items()):
        key_el = ET.SubElement(root, "key")
        key_el.set("id", f"e_{key_name}")
        key_el.set("for", "edge")
        key_el.set("attr.name", key_name)
        key_el.set("attr.type", key_type)

    # Graph element
    edge_default = "directed" if graph.is_directed else "undirected"
    graph_el = ET.SubElement(root, "graph")
    graph_el.set("id", graph.name or "G")
    graph_el.set("edgedefault", edge_default)

    # Nodes
    for nid in graph.node_ids():
        node_el = ET.SubElement(graph_el, "node")
        node_el.set("id", nid)
        node = graph.node(nid)
        node_props = node.properties if node else {}
        for k, v in sorted(node_props.items()):
            data_el = ET.SubElement(node_el, "data")
            data_el.set("key", f"n_{k}")
            data_el.text = _serialize_value(v)

    # Edges
    for idx, edge in enumerate(graph.edges()):
        edge_el = ET.SubElement(graph_el, "edge")
        edge_el.set("id", f"e{idx}")
        edge_el.set("source", edge.source)
        edge_el.set("target", edge.target)
        for k, v in sorted(edge.properties.items()):
            data_el = ET.SubElement(edge_el, "data")
            data_el.set("key", f"e_{k}")
            data_el.text = _serialize_value(v)

    # Serialize with declaration
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def from_graphml(data: str) -> Graph:
    """Parse a GraphML XML string into a Graph.

    Args:
        data: GraphML XML string.

    Returns:
        A Graph instance.

    Raises:
        InvalidFormatError: If the XML is not valid GraphML.
    """
    from kaos_graph.graph import Graph

    # Refuse before parsing if the byte length is unreasonable. defusedxml
    # disables XXE / external-entity / DTD-bomb classes, but reading the
    # whole document into ET still allocates per-element nodes.
    raw_len = len(data.encode("utf-8")) if isinstance(data, str) else len(data)
    if raw_len > _MAX_GRAPHML_BYTES:
        raise InvalidFormatError(
            f"GraphML input is {raw_len} bytes; refusing to parse above "
            f"{_MAX_GRAPHML_BYTES} bytes. Increase the cap in code only if "
            "the input is trusted."
        )

    try:
        root = _safe_fromstring(data)
    except ET.ParseError as e:
        raise InvalidFormatError(f"Invalid XML: {e}") from e

    # Handle namespace: GraphML elements may be namespaced or not
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    # Parse key declarations
    key_map: dict[str, tuple[str, str, str]] = {}  # id -> (for, attr.name, attr.type)
    for key_el in root.iter(f"{ns}key"):
        key_id = key_el.get("id", "")
        key_for = key_el.get("for", "")
        attr_name = key_el.get("attr.name", key_id)
        attr_type = key_el.get("attr.type", "string")
        key_map[key_id] = (key_for, attr_name, attr_type)

    # Find graph element
    graph_el = root.find(f"{ns}graph")
    if graph_el is None:
        raise InvalidFormatError("No <graph> element found in GraphML")

    edge_default = graph_el.get("edgedefault", "directed")
    directed = edge_default == "directed"
    graph_name = graph_el.get("id", "")

    g = Graph(directed=directed, name=graph_name or None)

    # Parse nodes
    for node_el in graph_el.iter(f"{ns}node"):
        nid = node_el.get("id")
        if nid is None:
            raise InvalidFormatError("Node element missing 'id' attribute")

        props: dict[str, Any] = {}
        for data_el in node_el.findall(f"{ns}data"):
            key_id = data_el.get("key", "")
            text = data_el.text or ""
            if key_id in key_map:
                _, attr_name, attr_type = key_map[key_id]
                props[attr_name] = _deserialize_value(text, attr_type)
            else:
                props[key_id] = text

        g.add_node(nid, **props)

    # Parse edges
    for edge_el in graph_el.iter(f"{ns}edge"):
        src = edge_el.get("source")
        tgt = edge_el.get("target")
        if src is None or tgt is None:
            raise InvalidFormatError("Edge element missing 'source' or 'target' attribute")

        props = {}
        for data_el in edge_el.findall(f"{ns}data"):
            key_id = data_el.get("key", "")
            text = data_el.text or ""
            if key_id in key_map:
                _, attr_name, attr_type = key_map[key_id]
                props[attr_name] = _deserialize_value(text, attr_type)
            else:
                props[key_id] = text

        g.add_edge(src, tgt, **props)

    return g


__all__ = ["from_graphml", "to_graphml"]
