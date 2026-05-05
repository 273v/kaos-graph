"""Tests for Mermaid, DOT, GraphML, GEXF, and Adjacency JSON graph I/O."""

from __future__ import annotations

import json

from kaos_graph.graph import Graph
from kaos_graph.io import (
    from_gexf,
    from_graphml,
    load_adjacency_json,
    to_adjacency_json,
    to_dot,
    to_gexf,
    to_graphml,
    to_mermaid,
)


def _make_simple_graph() -> Graph:
    """Create a small directed graph for testing."""
    g = Graph(directed=True)
    g.add_node("a", label="Node A")
    g.add_node("b", label="Node B")
    g.add_node("c", label="Node C")
    g.add_edge("a", "b", weight=1.0)
    g.add_edge("b", "c", weight=2.0)
    return g


# --- Mermaid tests ---


def test_mermaid_basic() -> None:
    g = _make_simple_graph()
    result = to_mermaid(g)
    assert result.startswith("flowchart TB\n")
    assert 'a["a"]' in result
    assert 'b["b"]' in result
    assert 'c["c"]' in result
    assert "a --> b" in result
    assert "b --> c" in result


def test_mermaid_custom_labels() -> None:
    g = _make_simple_graph()
    result = to_mermaid(
        g,
        node_label=lambda nid, props: props.get("label", nid),
        edge_label=lambda src, tgt, props: f"w={props.get('weight', '?')}",
    )
    assert '"Node A"' in result
    assert '"Node B"' in result
    assert '"Node C"' in result
    assert '-->|"w=1.0"|' in result
    assert '-->|"w=2.0"|' in result


def test_mermaid_truncation() -> None:
    g = Graph(directed=True)
    for i in range(100):
        g.add_node(f"n{i}")
    # Chain edges
    for i in range(99):
        g.add_edge(f"n{i}", f"n{i + 1}")

    result = to_mermaid(g, max_nodes=10)
    # Should have exactly 10 node definitions (plus header, edges, truncation lines)
    node_defs = [line for line in result.splitlines() if '["' in line and "truncated" not in line]
    assert len(node_defs) == 10

    # Truncation note
    assert "90 more nodes omitted" in result
    assert "truncated_note" in result


def test_mermaid_direction() -> None:
    g = _make_simple_graph()
    result = to_mermaid(g, direction="LR")
    assert result.startswith("flowchart LR\n")


def test_mermaid_sanitizes_ids() -> None:
    """Node IDs with special chars are sanitized for Mermaid."""
    g = Graph(directed=True)
    g.add_node("node-1")
    g.add_node("2nd")
    g.add_edge("node-1", "2nd")
    result = to_mermaid(g)
    # "node-1" -> "node_1", "2nd" -> "n_2nd"
    assert "node_1" in result
    assert "n_2nd" in result


def test_mermaid_empty_edge_label() -> None:
    """Edge label callback returning empty string uses plain arrow."""
    g = Graph(directed=True)
    g.add_node("x")
    g.add_node("y")
    g.add_edge("x", "y")
    result = to_mermaid(g, edge_label=lambda s, t, p: "")
    assert "x --> y" in result
    assert "-->|" not in result


# --- DOT tests ---


def test_dot_directed() -> None:
    g = _make_simple_graph()
    result = to_dot(g)
    assert result.startswith('digraph "G" {\n')
    assert '"a" -> "b"' in result
    assert '"b" -> "c"' in result
    assert result.strip().endswith("}")


def test_dot_undirected() -> None:
    g = Graph(directed=False)
    g.add_node("x")
    g.add_node("y")
    g.add_edge("x", "y")
    result = to_dot(g)
    assert result.startswith('graph "G" {\n')
    assert '"x" -- "y"' in result
    assert "->" not in result


def test_dot_labels() -> None:
    g = _make_simple_graph()
    result = to_dot(
        g,
        node_label=lambda nid, props: props.get("label", nid),
        edge_label=lambda src, tgt, props: f"w={props.get('weight', '')}",
        graph_name="TestGraph",
    )
    assert 'digraph "TestGraph" {' in result
    assert '[label="Node A"]' in result
    assert '[label="Node B"]' in result
    assert '[label="Node C"]' in result
    assert '[label="w=1.0"]' in result
    assert '[label="w=2.0"]' in result


def test_dot_empty_edge_label() -> None:
    """Edge label callback returning empty string omits label attribute on edge."""
    g = Graph(directed=True)
    g.add_node("a")
    g.add_node("b")
    g.add_edge("a", "b")
    result = to_dot(g, edge_label=lambda s, t, p: "")
    # Edge line should have no [label=...] attribute
    edge_lines = [line for line in result.splitlines() if "->" in line and '"a"' in line]
    assert len(edge_lines) == 1
    assert "[label=" not in edge_lines[0]


def test_dot_escaping() -> None:
    """Special characters in IDs and labels are escaped."""
    g = Graph(directed=True)
    g.add_node('node"1')
    g.add_node("node\\2")
    g.add_edge('node"1', "node\\2")
    result = to_dot(g, graph_name='My "Graph"')
    assert 'digraph "My \\"Graph\\"" {' in result
    assert '"node\\"1"' in result
    assert '"node\\\\2"' in result


# --- GraphML tests ---


def test_graphml_basic_roundtrip() -> None:
    """Create graph -> export GraphML -> parse -> verify."""
    g = _make_simple_graph()
    xml = to_graphml(g)

    # Check basic structure
    assert "graphml" in xml
    assert 'edgedefault="directed"' in xml

    # Parse back
    g2 = from_graphml(xml)
    assert g2.n_nodes == g.n_nodes
    assert g2.n_edges == g.n_edges
    assert g2.is_directed == g.is_directed
    assert g2.has_node("a")
    assert g2.has_node("b")
    assert g2.has_node("c")
    assert g2.has_edge("a", "b")
    assert g2.has_edge("b", "c")


def test_graphml_properties_roundtrip() -> None:
    """Node and edge properties survive round-trip."""
    g = _make_simple_graph()
    xml = to_graphml(g)
    g2 = from_graphml(xml)

    # Node properties
    node_a = g2.node("a")
    assert node_a is not None
    assert node_a["label"] == "Node A"

    # Edge properties (weight is a float)
    edges = g2.edges()
    ab_edges = [e for e in edges if e.source == "a" and e.target == "b"]
    assert len(ab_edges) == 1
    assert ab_edges[0].properties["weight"] == 1.0


def test_graphml_undirected() -> None:
    """Undirected graph round-trips correctly."""
    g = Graph(directed=False)
    g.add_node("x")
    g.add_node("y")
    g.add_edge("x", "y")
    xml = to_graphml(g)
    assert 'edgedefault="undirected"' in xml

    g2 = from_graphml(xml)
    assert not g2.is_directed
    assert g2.has_node("x")
    assert g2.has_node("y")


def test_graphml_empty_graph() -> None:
    """Empty graph round-trips."""
    g = Graph(directed=True)
    xml = to_graphml(g)
    g2 = from_graphml(xml)
    assert g2.n_nodes == 0
    assert g2.n_edges == 0


def test_graphml_xml_declaration() -> None:
    """Output starts with XML declaration."""
    g = Graph(directed=True)
    g.add_node("a")
    xml = to_graphml(g)
    assert xml.startswith("<?xml")


def test_graphml_invalid_xml() -> None:
    """Invalid XML raises InvalidFormatError."""
    import pytest

    from kaos_graph.errors import InvalidFormatError

    with pytest.raises(InvalidFormatError, match="Invalid XML"):
        from_graphml("not xml at all <<<")


def test_graphml_missing_graph_element() -> None:
    """XML without <graph> raises InvalidFormatError."""
    import pytest

    from kaos_graph.errors import InvalidFormatError

    with pytest.raises(InvalidFormatError, match="No <graph> element"):
        from_graphml(
            '<?xml version="1.0"?><graphml xmlns="http://graphml.graphdrawing.org/xmlns"></graphml>'
        )


# --- GEXF tests ---


def test_gexf_basic_roundtrip() -> None:
    """Create graph -> export GEXF -> parse -> verify."""
    g = _make_simple_graph()
    xml = to_gexf(g)

    # Check basic structure
    assert "gexf" in xml
    assert 'defaultedgetype="directed"' in xml

    # Parse back
    g2 = from_gexf(xml)
    assert g2.n_nodes == g.n_nodes
    assert g2.n_edges == g.n_edges
    assert g2.is_directed == g.is_directed
    assert g2.has_node("a")
    assert g2.has_node("b")
    assert g2.has_node("c")
    assert g2.has_edge("a", "b")
    assert g2.has_edge("b", "c")


def test_gexf_properties_roundtrip() -> None:
    """Node and edge properties survive round-trip."""
    g = _make_simple_graph()
    xml = to_gexf(g)
    g2 = from_gexf(xml)

    # Node properties (label is stored as GEXF attribute)
    node_a = g2.node("a")
    assert node_a is not None
    assert node_a["label"] == "Node A"

    # Edge properties (weight is a float)
    edges = g2.edges()
    ab_edges = [e for e in edges if e.source == "a" and e.target == "b"]
    assert len(ab_edges) == 1
    assert ab_edges[0].properties["weight"] == 1.0


def test_gexf_undirected() -> None:
    """Undirected graph round-trips correctly."""
    g = Graph(directed=False)
    g.add_node("x")
    g.add_node("y")
    g.add_edge("x", "y")
    xml = to_gexf(g)
    assert 'defaultedgetype="undirected"' in xml

    g2 = from_gexf(xml)
    assert not g2.is_directed


def test_gexf_empty_graph() -> None:
    """Empty graph round-trips."""
    g = Graph(directed=True)
    xml = to_gexf(g)
    g2 = from_gexf(xml)
    assert g2.n_nodes == 0
    assert g2.n_edges == 0


def test_gexf_labels() -> None:
    """GEXF node labels default to node ID when no label property."""
    g = Graph(directed=True)
    g.add_node("my_node")
    xml = to_gexf(g)
    assert 'label="my_node"' in xml


def test_gexf_xml_declaration() -> None:
    """Output starts with XML declaration."""
    g = Graph(directed=True)
    g.add_node("a")
    xml = to_gexf(g)
    assert xml.startswith("<?xml")


def test_gexf_invalid_xml() -> None:
    """Invalid XML raises InvalidFormatError."""
    import pytest

    from kaos_graph.errors import InvalidFormatError

    with pytest.raises(InvalidFormatError, match="Invalid XML"):
        from_gexf("not xml <<<")


def test_gexf_missing_graph_element() -> None:
    """XML without <graph> raises InvalidFormatError."""
    import pytest

    from kaos_graph.errors import InvalidFormatError

    with pytest.raises(InvalidFormatError, match="No <graph> element"):
        from_gexf('<?xml version="1.0"?><gexf xmlns="http://gexf.net/1.3"></gexf>')


# --- Adjacency JSON tests ---


def test_adjacency_json_roundtrip() -> None:
    """Graph round-trips through adjacency JSON."""
    g = _make_simple_graph()
    adj = to_adjacency_json(g)
    g2 = load_adjacency_json(adj)
    assert g2.n_nodes == g.n_nodes
    assert g2.n_edges == g.n_edges
    assert g2.is_directed == g.is_directed
    assert g2.has_node("a")
    assert g2.has_node("b")
    assert g2.has_node("c")
    assert g2.has_edge("a", "b")
    assert g2.has_edge("b", "c")


def test_adjacency_json_properties_roundtrip() -> None:
    """Node and edge properties survive adjacency JSON round-trip."""
    g = _make_simple_graph()
    adj = to_adjacency_json(g)
    g2 = load_adjacency_json(adj)

    # Node properties
    node_a = g2.node("a")
    assert node_a is not None
    assert node_a["label"] == "Node A"

    # Edge properties
    edges = g2.edges()
    ab_edges = [e for e in edges if e.source == "a" and e.target == "b"]
    assert len(ab_edges) == 1
    assert ab_edges[0].properties["weight"] == 1.0


def test_adjacency_json_structure() -> None:
    """Output JSON has expected structure."""
    g = _make_simple_graph()
    adj = to_adjacency_json(g)
    parsed = json.loads(adj)
    assert "directed" in parsed
    assert "nodes" in parsed
    assert "edges" in parsed
    assert parsed["directed"] is True
    assert "a" in parsed["nodes"]
    assert "a" in parsed["edges"]


def test_adjacency_json_empty_graph() -> None:
    """Empty graph round-trips correctly."""
    g = Graph(directed=True)
    adj = to_adjacency_json(g)
    g2 = load_adjacency_json(adj)
    assert g2.n_nodes == 0
    assert g2.n_edges == 0


def test_adjacency_json_undirected() -> None:
    """Undirected graph round-trips."""
    g = Graph(directed=False)
    g.add_node("x")
    g.add_node("y")
    g.add_edge("x", "y")
    adj = to_adjacency_json(g)
    g2 = load_adjacency_json(adj)
    assert not g2.is_directed


def test_adjacency_json_invalid() -> None:
    """Invalid JSON raises ValueError."""
    import pytest

    with pytest.raises(ValueError, match="Invalid JSON"):
        load_adjacency_json("not json {{{")


# --- Mixed-type property round-trip tests ---


def test_graphml_mixed_type_properties() -> None:
    """GraphML handles heterogeneous property types via string fallback."""
    g = Graph()
    g.add_node("a", meta=1)
    g.add_node("b", meta={"x": 1})
    xml = to_graphml(g)
    g2 = from_graphml(xml)
    # Integer may survive as string when type is forced to "string"
    props_a = g2.node("a")
    assert props_a is not None
    assert props_a["meta"] == 1 or props_a["meta"] == "1"
    props_b = g2.node("b")
    assert props_b is not None
    assert props_b["meta"] == {"x": 1}


def test_gexf_mixed_type_properties() -> None:
    """GEXF handles heterogeneous property types via string fallback."""
    g = Graph()
    g.add_node("a", meta=1)
    g.add_node("b", meta={"x": 1})
    xml = to_gexf(g)
    g2 = from_gexf(xml)
    # Integer may survive as string when type is forced to "string"
    props_a = g2.node("a")
    assert props_a is not None
    assert props_a["meta"] == 1 or props_a["meta"] == "1"
    props_b = g2.node("b")
    assert props_b is not None
    assert props_b["meta"] == {"x": 1}


def test_graphml_list_property_roundtrip() -> None:
    """GraphML round-trips list properties via JSON serialization."""
    g = Graph()
    g.add_node("a", tags=["x", "y"])
    xml = to_graphml(g)
    g2 = from_graphml(xml)
    props = g2.node("a")
    assert props is not None
    assert props["tags"] == ["x", "y"]


def test_gexf_list_property_roundtrip() -> None:
    """GEXF round-trips list properties via JSON serialization."""
    g = Graph()
    g.add_node("a", tags=["x", "y"])
    xml = to_gexf(g)
    g2 = from_gexf(xml)
    props = g2.node("a")
    assert props is not None
    assert props["tags"] == ["x", "y"]
