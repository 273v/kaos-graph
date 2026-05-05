"""GEXF (Graph Exchange XML Format) import/export.

GEXF is an XML format used by Gephi and other graph visualization tools.
This module uses Python's stdlib xml.etree.ElementTree. No external deps.

Reference: https://gexf.net/schema.html
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET  # used for *output* construction only
from typing import TYPE_CHECKING, Any

from defusedxml.ElementTree import fromstring as _safe_fromstring

from kaos_graph.errors import InvalidFormatError

# A2-#6: hard cap on input XML size, matching graphml.py.
_MAX_GEXF_BYTES = 32 * 1024 * 1024

if TYPE_CHECKING:
    from kaos_graph.graph import Graph

_GEXF_NS = "http://gexf.net/1.3"
_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_SCHEMA_LOC = "http://gexf.net/1.3 http://gexf.net/1.3/gexf.xsd"
_GEXF_VERSION = "1.3"


def _infer_gexf_type(value: Any) -> str:
    """Map a Python value to a GEXF attribute type string."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "long"
    if isinstance(value, float):
        return "double"
    return "string"


def _serialize_value(value: Any) -> str:
    """Serialize a property value for a GEXF attvalue element."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _deserialize_value(text: str, attr_type: str) -> Any:
    """Deserialize a GEXF attvalue text to a Python value."""
    if attr_type == "boolean":
        return text.lower() in ("true", "1")
    if attr_type in ("integer", "long"):
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


def to_gexf(graph: Graph) -> str:
    """Export a graph as a GEXF XML string.

    Node IDs, labels, and all properties are preserved. Properties are
    emitted as GEXF attribute definitions and attvalue elements.

    Args:
        graph: The graph to export.

    Returns:
        A GEXF XML string.
    """
    # Collect attribute keys across nodes and edges, tracking all value types
    node_attr_types: dict[str, set[str]] = {}  # attr_name -> set of gexf_types seen
    edge_attr_types: dict[str, set[str]] = {}
    node_has_complex: dict[str, bool] = {}  # attr_name -> True if any dict/list value
    edge_has_complex: dict[str, bool] = {}

    for nid in graph.node_ids():
        node = graph.node(nid)
        node_props = node.properties if node else {}
        for k, v in node_props.items():
            node_attr_types.setdefault(k, set()).add(_infer_gexf_type(v))
            if isinstance(v, (dict, list)):
                node_has_complex[k] = True

    for edge in graph.edges():
        for k, v in edge.properties.items():
            edge_attr_types.setdefault(k, set()).add(_infer_gexf_type(v))
            if isinstance(v, (dict, list)):
                edge_has_complex[k] = True

    # Resolve final types: use "string" when types are mixed or any value is complex
    node_attrs: dict[str, str] = {}
    for k, types in node_attr_types.items():
        if len(types) > 1 or node_has_complex.get(k, False):
            node_attrs[k] = "string"
        else:
            node_attrs[k] = next(iter(types))

    edge_attrs: dict[str, str] = {}
    for k, types in edge_attr_types.items():
        if len(types) > 1 or edge_has_complex.get(k, False):
            edge_attrs[k] = "string"
        else:
            edge_attrs[k] = next(iter(types))

    # Build XML
    root = ET.Element("gexf")
    root.set("xmlns", _GEXF_NS)
    root.set("xmlns:xsi", _XSI_NS)
    root.set("xsi:schemaLocation", _SCHEMA_LOC)
    root.set("version", _GEXF_VERSION)

    # Graph element
    edge_type = "directed" if graph.is_directed else "undirected"
    graph_el = ET.SubElement(root, "graph")
    graph_el.set("defaultedgetype", edge_type)

    # Node attribute declarations
    if node_attrs:
        node_attrs_el = ET.SubElement(graph_el, "attributes")
        node_attrs_el.set("class", "node")
        for idx, (attr_name, attr_type) in enumerate(sorted(node_attrs.items())):
            attr_el = ET.SubElement(node_attrs_el, "attribute")
            attr_el.set("id", str(idx))
            attr_el.set("title", attr_name)
            attr_el.set("type", attr_type)
    node_attr_id_map = {name: str(i) for i, (name, _) in enumerate(sorted(node_attrs.items()))}

    # Edge attribute declarations
    if edge_attrs:
        edge_attrs_el = ET.SubElement(graph_el, "attributes")
        edge_attrs_el.set("class", "edge")
        for idx, (attr_name, attr_type) in enumerate(sorted(edge_attrs.items())):
            attr_el = ET.SubElement(edge_attrs_el, "attribute")
            attr_el.set("id", f"e{idx}")
            attr_el.set("title", attr_name)
            attr_el.set("type", attr_type)
    edge_attr_id_map = {name: f"e{i}" for i, (name, _) in enumerate(sorted(edge_attrs.items()))}

    # Nodes
    nodes_el = ET.SubElement(graph_el, "nodes")
    for nid in graph.node_ids():
        node_el = ET.SubElement(nodes_el, "node")
        node_el.set("id", nid)
        node = graph.node(nid)
        node_props = node.properties if node else {}
        # Use 'label' property as GEXF label if available, else node ID
        label = node_props.get("label", nid)
        if not isinstance(label, str):
            label = str(label)
        node_el.set("label", label)

        if node_props:
            attvalues_el = ET.SubElement(node_el, "attvalues")
            for k, v in sorted(node_props.items()):
                if k in node_attr_id_map:
                    av_el = ET.SubElement(attvalues_el, "attvalue")
                    av_el.set("for", node_attr_id_map[k])
                    av_el.set("value", _serialize_value(v))

    # Edges
    edges_el = ET.SubElement(graph_el, "edges")
    for idx, edge in enumerate(graph.edges()):
        edge_el = ET.SubElement(edges_el, "edge")
        edge_el.set("id", str(idx))
        edge_el.set("source", edge.source)
        edge_el.set("target", edge.target)

        if edge.properties:
            attvalues_el = ET.SubElement(edge_el, "attvalues")
            for k, v in sorted(edge.properties.items()):
                if k in edge_attr_id_map:
                    av_el = ET.SubElement(attvalues_el, "attvalue")
                    av_el.set("for", edge_attr_id_map[k])
                    av_el.set("value", _serialize_value(v))

    # Serialize with declaration
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def from_gexf(data: str) -> Graph:
    """Parse a GEXF XML string into a Graph.

    Args:
        data: GEXF XML string.

    Returns:
        A Graph instance.

    Raises:
        InvalidFormatError: If the XML is not valid GEXF.
    """
    from kaos_graph.graph import Graph

    raw_len = len(data.encode("utf-8")) if isinstance(data, str) else len(data)
    if raw_len > _MAX_GEXF_BYTES:
        raise InvalidFormatError(
            f"GEXF input is {raw_len} bytes; refusing to parse above "
            f"{_MAX_GEXF_BYTES} bytes. Increase the cap in code only if "
            "the input is trusted."
        )

    try:
        root = _safe_fromstring(data)
    except ET.ParseError as e:
        raise InvalidFormatError(f"Invalid XML: {e}") from e

    # Handle namespace
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    # Find graph element
    graph_el = root.find(f"{ns}graph")
    if graph_el is None:
        raise InvalidFormatError("No <graph> element found in GEXF")

    edge_type = graph_el.get("defaultedgetype", "directed")
    directed = edge_type == "directed"

    g = Graph(directed=directed)

    # Parse attribute declarations
    # Maps: (class, id) -> (title, type)
    attr_defs: dict[tuple[str, str], tuple[str, str]] = {}
    for attrs_el in graph_el.findall(f"{ns}attributes"):
        attr_class = attrs_el.get("class", "")
        for attr_el in attrs_el.findall(f"{ns}attribute"):
            attr_id = attr_el.get("id", "")
            attr_title = attr_el.get("title", attr_id)
            attr_type = attr_el.get("type", "string")
            attr_defs[(attr_class, attr_id)] = (attr_title, attr_type)

    # Parse nodes
    nodes_el = graph_el.find(f"{ns}nodes")
    if nodes_el is not None:
        for node_el in nodes_el.findall(f"{ns}node"):
            nid = node_el.get("id")
            if nid is None:
                raise InvalidFormatError("Node element missing 'id' attribute")

            props: dict[str, Any] = {}
            label = node_el.get("label")
            if label is not None:
                props["label"] = label

            attvalues_el = node_el.find(f"{ns}attvalues")
            if attvalues_el is not None:
                for av_el in attvalues_el.findall(f"{ns}attvalue"):
                    attr_id = av_el.get("for", "")
                    value_text = av_el.get("value", "")
                    key = ("node", attr_id)
                    if key in attr_defs:
                        title, atype = attr_defs[key]
                        props[title] = _deserialize_value(value_text, atype)
                    else:
                        props[attr_id] = value_text

            g.add_node(nid, **props)

    # Parse edges
    edges_el = graph_el.find(f"{ns}edges")
    if edges_el is not None:
        for edge_el in edges_el.findall(f"{ns}edge"):
            src = edge_el.get("source")
            tgt = edge_el.get("target")
            if src is None or tgt is None:
                raise InvalidFormatError("Edge element missing 'source' or 'target' attribute")

            props = {}
            attvalues_el = edge_el.find(f"{ns}attvalues")
            if attvalues_el is not None:
                for av_el in attvalues_el.findall(f"{ns}attvalue"):
                    attr_id = av_el.get("for", "")
                    value_text = av_el.get("value", "")
                    key = ("edge", attr_id)
                    if key in attr_defs:
                        title, atype = attr_defs[key]
                        props[title] = _deserialize_value(value_text, atype)
                    else:
                        props[attr_id] = value_text

            g.add_edge(src, tgt, **props)

    return g


__all__ = ["from_gexf", "to_gexf"]
