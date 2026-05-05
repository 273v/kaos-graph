"""Tests for knowledge graph operations."""

from kaos_graph.graph import Graph
from kaos_graph.knowledge import (
    GraphDiff,
    Triple,
    degree_distribution,
    densify,
    diff_graphs,
    extract_subgraph,
    extract_subgraph_by_property,
    extract_subgraph_by_types,
    find_hub_nodes,
    find_orphan_nodes,
    from_triples,
    infer_types,
    merge_graphs,
    project_triples,
)


def _make_simple_graph() -> Graph:
    """Build a small graph: a(person)->b(person), a->c(org)."""
    g = Graph(directed=True)
    g.add_node("a", type="person", name="Alice")
    g.add_node("b", type="person", name="Bob")
    g.add_node("c", type="org")
    g.add_edge("a", "b", predicate="knows")
    g.add_edge("a", "c", predicate="worksAt")
    return g


class TestMergeGraphs:
    def test_disjoint(self):
        g1 = Graph(directed=True)
        g1.add_node("a")
        g2 = Graph(directed=True)
        g2.add_node("b")
        merged = merge_graphs(g1, g2)
        assert merged.n_nodes == 2
        assert merged.has_node("a")
        assert merged.has_node("b")

    def test_overlapping_nodes_other_wins(self):
        g1 = Graph(directed=True)
        g1.add_node("x", v=1)
        g2 = Graph(directed=True)
        g2.add_node("x", v=2)
        merged = merge_graphs(g1, g2)
        assert merged.n_nodes == 1
        props = merged.node("x")
        assert props is not None
        assert props["v"] == 2

    def test_edges_preserved(self):
        g1 = Graph(directed=True)
        g1.add_node("a")
        g1.add_node("b")
        g1.add_edge("a", "b")
        g2 = Graph(directed=True)
        g2.add_node("b")
        g2.add_node("c")
        g2.add_edge("b", "c")
        merged = merge_graphs(g1, g2)
        assert merged.n_nodes == 3
        assert merged.has_edge("a", "b")
        assert merged.has_edge("b", "c")

    def test_edge_property_override(self):
        g1 = Graph(directed=True)
        g1.add_node("a")
        g1.add_node("b")
        g1.add_edge("a", "b", weight=1)
        g2 = Graph(directed=True)
        g2.add_node("a")
        g2.add_node("b")
        g2.add_edge("a", "b", weight=99)
        merged = merge_graphs(g1, g2)
        edges = merged.edges()
        ab = [e for e in edges if e.source == "a" and e.target == "b"]
        assert len(ab) == 1
        assert ab[0].properties["weight"] == 99


class TestDiffGraphs:
    def test_no_change(self):
        g = _make_simple_graph()
        diff = diff_graphs(g, g)
        assert isinstance(diff, GraphDiff)
        assert diff.added_nodes == []
        assert diff.removed_nodes == []
        assert diff.added_edges == []
        assert diff.removed_edges == []
        assert diff.changed_node_properties == []

    def test_added_and_removed_nodes(self):
        old = Graph(directed=True)
        old.add_node("a")
        old.add_node("b")
        new = Graph(directed=True)
        new.add_node("b")
        new.add_node("c")
        diff = diff_graphs(old, new)
        assert "c" in diff.added_nodes
        assert "a" in diff.removed_nodes

    def test_changed_properties(self):
        old = Graph(directed=True)
        old.add_node("x", v=1)
        new = Graph(directed=True)
        new.add_node("x", v=2)
        diff = diff_graphs(old, new)
        assert "x" in diff.changed_node_properties

    def test_edge_diff(self):
        old = Graph(directed=True)
        old.add_node("a")
        old.add_node("b")
        old.add_edge("a", "b")
        new = Graph(directed=True)
        new.add_node("a")
        new.add_node("b")
        new.add_node("c")
        new.add_edge("a", "c")
        diff = diff_graphs(old, new)
        assert ("a", "c") in diff.added_edges
        assert ("a", "b") in diff.removed_edges


class TestExtractSubgraphByProperty:
    def test_filter_by_type(self):
        g = _make_simple_graph()
        sub = extract_subgraph_by_property(g, "type", "person")
        assert sub.n_nodes == 2
        assert sub.has_node("a")
        assert sub.has_node("b")
        assert not sub.has_node("c")
        assert sub.has_edge("a", "b")

    def test_no_match(self):
        g = _make_simple_graph()
        sub = extract_subgraph_by_property(g, "type", "nonexistent")
        assert sub.n_nodes == 0


class TestProjectTriples:
    def test_basic(self):
        g = _make_simple_graph()
        triples = project_triples(g)
        assert len(triples) == 2
        assert all(isinstance(t, Triple) for t in triples)
        preds = {(t.subject, t.predicate, t.object) for t in triples}
        assert ("a", "knows", "b") in preds
        assert ("a", "worksAt", "c") in preds

    def test_default_predicate(self):
        g = Graph(directed=True)
        g.add_node("x")
        g.add_node("y")
        g.add_edge("x", "y")
        triples = project_triples(g)
        assert len(triples) == 1
        assert triples[0].predicate == "relatedTo"


class TestFromTriples:
    def test_basic(self):
        triples = [("A", "knows", "B"), ("B", "knows", "C")]
        g = from_triples(triples)
        assert g.n_nodes == 3
        assert g.n_edges == 2
        assert g.has_edge("A", "B")
        assert g.has_edge("B", "C")

    def test_undirected(self):
        triples = [("A", "knows", "B")]
        g = from_triples(triples, directed=False)
        assert not g.is_directed
        assert g.has_edge("A", "B")
        assert g.has_edge("B", "A")

    def test_roundtrip(self):
        g = _make_simple_graph()
        triples = project_triples(g)
        g2 = from_triples(triples)
        assert g2.n_nodes == g.n_nodes
        assert g2.n_edges == g.n_edges


class TestInferTypes:
    def test_transitive_subclass(self):
        g = Graph(directed=True)
        g.add_node("A")
        g.add_node("B")
        g.add_node("C")
        g.add_edge("A", "B", predicate="subClassOf")
        g.add_edge("B", "C", predicate="subClassOf")
        inferred = infer_types(g, "subClassOf")
        assert inferred.has_edge("A", "B")
        assert inferred.has_edge("B", "C")
        assert inferred.has_edge("A", "C")  # inferred

    def test_no_inference_different_predicate(self):
        g = Graph(directed=True)
        g.add_node("A")
        g.add_node("B")
        g.add_edge("A", "B", predicate="knows")
        inferred = infer_types(g, "subClassOf")
        assert inferred.n_edges == 1  # no new edges

    def test_chain(self):
        g = Graph(directed=True)
        for nid in ["A", "B", "C", "D"]:
            g.add_node(nid)
        for s, t in [("A", "B"), ("B", "C"), ("C", "D")]:
            g.add_edge(s, t, predicate="isa")
        inferred = infer_types(g, "isa")
        assert inferred.has_edge("A", "C")
        assert inferred.has_edge("A", "D")
        assert inferred.has_edge("B", "D")


class TestFindOrphanNodes:
    def test_with_orphan(self):
        g = Graph(directed=True)
        g.add_node("connected_a")
        g.add_node("connected_b")
        g.add_node("orphan")
        g.add_edge("connected_a", "connected_b")
        orphans = find_orphan_nodes(g)
        assert "orphan" in orphans
        assert "connected_a" not in orphans

    def test_empty_graph(self):
        g = Graph(directed=True)
        assert find_orphan_nodes(g) == []

    def test_all_orphans(self):
        g = Graph(directed=True)
        g.add_node("a")
        g.add_node("b")
        orphans = find_orphan_nodes(g)
        assert set(orphans) == {"a", "b"}


class TestFindHubNodes:
    def test_hub_detected(self):
        g = Graph(directed=True)
        g.add_node("hub")
        for i in range(5):
            nid = f"n{i}"
            g.add_node(nid)
            g.add_edge("hub", nid)
        hubs = find_hub_nodes(g, 3)
        assert "hub" in hubs
        assert "n0" not in hubs

    def test_no_hubs(self):
        g = Graph(directed=True)
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        assert find_hub_nodes(g, 10) == []


class TestDegreeDistribution:
    def test_basic(self):
        g = Graph(directed=True)
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_node("d")  # orphan
        g.add_edge("a", "b")
        g.add_edge("a", "c")
        dist = degree_distribution(g)
        assert dist[0] == 1  # d
        assert dist[1] == 2  # b, c
        assert dist[2] == 1  # a

    def test_empty(self):
        g = Graph(directed=True)
        assert degree_distribution(g) == {}


class TestMergeGraphsConflictStrategies:
    def test_keep_latest_default(self):
        g1 = Graph(directed=True)
        g1.add_node("x", v=1)
        g2 = Graph(directed=True)
        g2.add_node("x", v=2)
        merged = merge_graphs(g1, g2)
        props = merged.node("x")
        assert props is not None
        assert props["v"] == 2

    def test_keep_first(self):
        g1 = Graph(directed=True)
        g1.add_node("x", v=1)
        g2 = Graph(directed=True)
        g2.add_node("x", v=2)
        merged = merge_graphs(g1, g2, conflict="keep_first")
        props = merged.node("x")
        assert props is not None
        assert props["v"] == 1

    def test_merge_strategy(self):
        g1 = Graph(directed=True)
        g1.add_node("x", a=1, b=2)
        g2 = Graph(directed=True)
        g2.add_node("x", b=99, c=3)
        merged = merge_graphs(g1, g2, conflict="merge")
        props = merged.node("x")
        assert props is not None
        assert props["a"] == 1  # only in base
        assert props["b"] == 99  # overwritten by other
        assert props["c"] == 3  # only in other

    def test_keep_first_edges(self):
        g1 = Graph(directed=True)
        g1.add_node("a")
        g1.add_node("b")
        g1.add_edge("a", "b", weight=10)
        g2 = Graph(directed=True)
        g2.add_node("a")
        g2.add_node("b")
        g2.add_edge("a", "b", weight=99)
        merged = merge_graphs(g1, g2, conflict="keep_first")
        edges = merged.edges()
        ab = [e for e in edges if e.source == "a" and e.target == "b"]
        assert ab[0].properties["weight"] == 10


class TestDensify:
    def test_transitive(self):
        g = Graph(directed=True)
        g.add_node("A")
        g.add_node("B")
        g.add_node("C")
        g.add_edge("A", "B", predicate="knows")
        g.add_edge("B", "C", predicate="knows")
        dense = densify(g, "knows")
        assert dense.has_edge("A", "B")
        assert dense.has_edge("B", "C")
        assert dense.has_edge("A", "C")

    def test_no_matching_predicate(self):
        g = Graph(directed=True)
        g.add_node("A")
        g.add_node("B")
        g.add_edge("A", "B", predicate="knows")
        dense = densify(g, "likes")
        assert dense.n_edges == 1


class TestExtractSubgraphByTypes:
    def test_single_type(self):
        g = _make_simple_graph()
        sub = extract_subgraph_by_types(g, ["person"])
        assert sub.n_nodes == 2
        assert sub.has_node("a")
        assert sub.has_node("b")
        assert not sub.has_node("c")

    def test_multiple_types(self):
        g = _make_simple_graph()
        sub = extract_subgraph_by_types(g, ["person", "org"])
        assert sub.n_nodes == 3

    def test_no_match(self):
        g = _make_simple_graph()
        sub = extract_subgraph_by_types(g, ["nonexistent"])
        assert sub.n_nodes == 0


class TestExtractSubgraph:
    def test_node_types(self):
        g = _make_simple_graph()
        sub = extract_subgraph(g, node_types=["person"])
        assert sub.n_nodes == 2
        assert sub.has_node("a")
        assert sub.has_node("b")

    def test_edge_types(self):
        g = _make_simple_graph()
        sub = extract_subgraph(g, edge_types=["knows"])
        assert sub.has_edge("a", "b")
        assert not sub.has_edge("a", "c")

    def test_combined(self):
        g = _make_simple_graph()
        sub = extract_subgraph(g, node_types=["person"], edge_types=["knows"])
        assert sub.n_nodes == 2
        assert sub.has_edge("a", "b")

    def test_edge_types_does_not_mutate_original(self):
        g = Graph(directed=True)
        g.add_node("a", type="person")
        g.add_node("b", type="person")
        g.add_edge("a", "b", type="knows")
        g.add_edge("b", "a", type="hates")

        original_edges = g.n_edges
        result = extract_subgraph(g, edge_types=["knows"])
        assert g.n_edges == original_edges  # original unchanged
        assert result.n_edges == 1

    def test_edge_types_multigraph(self):
        """Regression: edge_types filtering must not conflate parallel edges."""
        g = Graph(directed=True, multi=True)
        g.add_node("a", type="person")
        g.add_node("b", type="person")
        g.add_edge("a", "b", type="knows")
        g.add_edge("a", "b", type="works_with")

        result = extract_subgraph(g, edge_types=["knows"])
        assert result.n_edges == 1
        edge_types = [edge.properties.get("type") for edge in result.edges()]
        assert edge_types == ["knows"]
