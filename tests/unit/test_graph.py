"""Tests for the Graph class."""

import pickle

from kaos_graph import Graph


class TestGraphBasic:
    def test_create_directed(self):
        g = Graph(directed=True)
        assert g.is_directed is True
        assert g.n_nodes == 0
        assert g.n_edges == 0

    def test_create_undirected(self):
        g = Graph(directed=False)
        assert g.is_directed is False

    def test_create_with_name(self):
        g = Graph(directed=True, name="test_graph")
        assert g.name == "test_graph"

    def test_add_nodes(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b", color="red", weight=1.5)
        assert g.n_nodes == 2
        assert g.has_node("a")
        assert g.has_node("b")
        assert not g.has_node("c")

    def test_node_properties(self):
        g = Graph()
        g.add_node("alice", name="Alice", age=30)
        props = g.node("alice")
        assert props is not None
        assert props["name"] == "Alice"
        assert props["age"] == 30

    def test_node_not_found(self):
        g = Graph()
        assert g.node("missing") is None

    def test_add_edges(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b", weight=1.0)
        assert g.n_edges == 1
        assert g.has_edge("a", "b")
        assert not g.has_edge("b", "a")

    def test_remove_node(self):
        g = Graph()
        g.add_node("a", x=1)
        g.add_node("b")
        g.add_edge("a", "b")
        removed = g.remove_node("a")
        assert removed.id == "a"
        assert removed["x"] == 1
        assert removed.properties["x"] == 1
        assert g.n_nodes == 1
        assert g.n_edges == 0

    def test_remove_edge(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        g.remove_edge("a", "b")
        assert g.n_edges == 0

    def test_node_ids(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        ids = sorted(g.node_ids())
        assert ids == ["a", "b", "c"]

    def test_edges_list(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b", w=5)
        edges = g.edges()
        assert len(edges) == 1
        edge = edges[0]
        assert edge.source == "a"
        assert edge.target == "b"
        assert edge.properties["w"] == 5

    def test_successors_predecessors(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("a", "c")
        assert sorted(g.successors("a")) == ["b", "c"]
        assert g.predecessors("b") == ["a"]

    def test_degree(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("c", "a")
        # a: out to b (1), in from c (1) = degree 2
        assert g.degree("a") == 2

    def test_is_dag(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        assert g.is_dag()
        g.add_edge("c", "a")
        assert not g.is_dag()


class TestGraphSerialization:
    def test_json_roundtrip(self):
        g = Graph()
        g.add_node("alice", role="person")
        g.add_node("bob")
        g.add_edge("alice", "bob", since=2020)
        data = g.to_json()
        g2 = Graph.from_json(data)
        assert g2.n_nodes == 2
        assert g2.n_edges == 1
        props = g2.node("alice")
        assert props is not None
        assert props["role"] == "person"

    def test_pickle_roundtrip(self):
        g = Graph()
        g.add_node("a", x=1)
        g.add_node("b")
        g.add_edge("a", "b")
        data = pickle.dumps(g._inner)
        inner = pickle.loads(data)
        assert inner.n_nodes == 2
        assert inner.n_edges == 1


class TestGraphDunder:
    def test_len(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        assert len(g) == 2

    def test_contains(self):
        g = Graph()
        g.add_node("a")
        assert "a" in g
        assert "b" not in g

    def test_repr(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        r = repr(g)
        assert "nodes=2" in r
        assert "edges=1" in r


class TestMultiGraph:
    def test_multi_default_false(self):
        g = Graph()
        assert g.is_multi is False

    def test_multi_allows_parallel_edges(self):
        g = Graph(multi=True)
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b", weight=1.0)
        g.add_edge("a", "b", weight=2.0)
        assert g.n_edges == 2
        assert g.is_multi is True

    def test_simple_rejects_parallel_edges(self):
        import pytest

        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        with pytest.raises(ValueError, match="already exists"):
            g.add_edge("a", "b")

    def test_multi_json_roundtrip(self):
        g = Graph(multi=True)
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b", w=1)
        g.add_edge("a", "b", w=2)
        data = g.to_json()
        g2 = Graph.from_json(data)
        assert g2.is_multi is True
        assert g2.n_edges == 2

    def test_multi_undirected(self):
        g = Graph(directed=False, multi=True)
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        g.add_edge("a", "b")
        assert g.n_edges == 2
        assert g.is_directed is False
        assert g.is_multi is True

    def test_multi_edge_filtering(self):
        """Regression: edges(**filter) must not conflate parallel edges by endpoint pair."""
        g = Graph(multi=True)
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b", color="red", weight=1)
        g.add_edge("a", "b", color="blue", weight=2)

        # Single filter
        red = g.edges(color="red")
        assert len(red) == 1
        assert red[0].properties["weight"] == 1

        blue = g.edges(color="blue")
        assert len(blue) == 1
        assert blue[0].properties["weight"] == 2

        # Multi-filter: no edge has BOTH color=red AND weight=2
        impossible = g.edges(color="red", weight=2)
        assert len(impossible) == 0

        # Multi-filter: exact match
        exact = g.edges(color="blue", weight=2)
        assert len(exact) == 1

    def test_multi_in_repr(self):
        g = Graph(multi=True)
        # Just ensure repr doesn't crash
        r = repr(g)
        assert "Graph" in r


class TestGraphTransforms:
    def test_subgraph(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_node("d")
        g.add_edge("a", "b", weight=1.0)
        g.add_edge("b", "c")
        g.add_edge("c", "d")
        g.add_edge("a", "c")

        sub = g.subgraph(["a", "b"])
        assert sub.n_nodes == 2
        assert sub.has_node("a")
        assert sub.has_node("b")
        assert not sub.has_node("c")
        assert not sub.has_node("d")
        # Only the a->b edge should survive
        assert sub.n_edges == 1
        assert sub.has_edge("a", "b")

    def test_ego_graph(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_node("d")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "d")

        ego = g.ego_graph("b", radius=1)
        ids = sorted(ego.node_ids())
        assert ids == ["a", "b", "c"]
        assert ego.n_nodes == 3

    def test_ego_graph_radius_zero(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")

        ego = g.ego_graph("a", radius=0)
        assert ego.n_nodes == 1
        assert ego.has_node("a")
        assert not ego.has_node("b")

    def test_is_connected(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        assert g.is_connected() is True

        g.add_node("isolated")
        assert g.is_connected() is False

    def test_is_tree(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        assert g.is_tree() is True

        g.add_edge("a", "c")
        assert g.is_tree() is False

    def test_reverse(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("b", "c")

        rev = g.reverse()
        assert rev.n_nodes == 3
        assert rev.n_edges == 2
        # Edges should be flipped
        assert rev.has_edge("b", "a")
        assert rev.has_edge("c", "b")
        assert not rev.has_edge("a", "b")
        assert not rev.has_edge("b", "c")

    def test_to_undirected(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")

        und = g.to_undirected()
        assert und.n_nodes == 2
        # Both directions should exist
        assert und.has_edge("a", "b")
        assert und.has_edge("b", "a")
