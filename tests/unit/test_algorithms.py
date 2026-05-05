"""Tests for graph algorithms (Python typed wrappers)."""

import pytest

from kaos_graph import Graph
from kaos_graph.algorithms import (
    all_simple_paths,
    ancestors,
    articulation_points,
    astar_path,
    bellman_ford_paths,
    betweenness_centrality,
    bfs,
    bfs_at_depth,
    bfs_with_depth,
    closeness_centrality,
    condensation,
    degree_centrality,
    density,
    descendants,
    dfs,
    dfs_events,
    eigenvector_centrality,
    find_cycle_paths,
    find_cycles,
    has_path,
    in_degree_centrality,
    is_bipartite,
    is_strongly_connected,
    is_weakly_connected,
    k_clique_communities,
    label_propagation,
    longest_path,
    louvain_communities,
    maximum_matching,
    num_connected_components,
    pagerank,
    shortest_path_length,
    shortest_paths,
    strongly_connected_components,
    topological_sort,
    transitive_closure,
    weakly_connected_components,
)
from kaos_graph.types import BfsNode, DfsEvent


def make_chain() -> Graph:
    g = Graph()
    g.add_node("a")
    g.add_node("b")
    g.add_node("c")
    g.add_node("d")
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    g.add_edge("c", "d")
    return g


def make_weighted() -> Graph:
    g = Graph()
    g.add_node("a")
    g.add_node("b")
    g.add_node("c")
    g.add_node("d")
    g.add_edge("a", "b", weight=1.0)
    g.add_edge("b", "c", weight=1.0)
    g.add_edge("a", "c", weight=10.0)
    g.add_edge("c", "d", weight=2.0)
    return g


class TestTraversal:
    def test_bfs(self):
        g = make_chain()
        order = bfs(g, "a")
        assert order == ["a", "b", "c", "d"]

    def test_dfs(self):
        g = make_chain()
        order = dfs(g, "a")
        assert order == ["a", "b", "c", "d"]

    def test_bfs_with_depth(self):
        g = make_chain()
        pairs = bfs_with_depth(g, "a")
        assert isinstance(pairs[0], BfsNode)
        assert pairs[0] == BfsNode(node_id="a", depth=0)
        assert pairs[1] == BfsNode(node_id="b", depth=1)
        assert pairs[2] == BfsNode(node_id="c", depth=2)
        assert pairs[3] == BfsNode(node_id="d", depth=3)

    def test_bfs_at_depth(self):
        g = Graph()
        g.add_node("root")
        g.add_node("l")
        g.add_node("r")
        g.add_edge("root", "l")
        g.add_edge("root", "r")
        at_1 = bfs_at_depth(g, "root", 1)
        assert sorted(at_1) == ["l", "r"]


class TestPaths:
    def test_shortest_paths_unweighted(self):
        g = make_chain()
        costs = shortest_paths(g, "a")
        assert costs["a"] == 0.0
        assert costs["b"] == 1.0
        assert costs["c"] == 2.0
        assert costs["d"] == 3.0

    def test_shortest_paths_weighted(self):
        g = make_weighted()
        costs = shortest_paths(g, "a", weight_key="weight")
        assert costs["a"] == 0.0
        assert costs["b"] == 1.0
        assert costs["c"] == 2.0  # a->b->c = 1+1 < a->c = 10
        assert costs["d"] == 4.0

    def test_shortest_path_length(self):
        g = make_weighted()
        length = shortest_path_length(g, "a", "d", weight_key="weight")
        assert length == 4.0

    def test_shortest_path_unreachable(self):
        g = make_chain()
        length = shortest_path_length(g, "d", "a")
        assert length is None

    def test_has_path(self):
        g = make_chain()
        assert has_path(g, "a", "d") is True
        assert has_path(g, "d", "a") is False

    def test_astar_path(self):
        g = make_weighted()
        result = astar_path(g, "a", "d", weight_key="weight")
        assert result is not None
        assert result.cost == 4.0
        assert result.path == ["a", "b", "c", "d"]

    def test_astar_unreachable(self):
        g = make_chain()
        result = astar_path(g, "d", "a")
        assert result is None

    def test_bellman_ford(self):
        g = make_weighted()
        costs = bellman_ford_paths(g, "a", weight_key="weight")
        assert costs["a"] == 0.0
        assert costs["b"] == 1.0
        assert costs["c"] == 2.0
        assert costs["d"] == 4.0


class TestComponents:
    def test_scc_dag(self):
        g = make_chain()
        sccs = strongly_connected_components(g)
        assert len(sccs) == 4

    def test_scc_cycle(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "a")
        sccs = strongly_connected_components(g)
        assert len(sccs) == 1
        assert len(sccs[0]) == 3

    def test_num_connected_components(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        assert num_connected_components(g) == 2  # {a,b} and {c}

    def test_weakly_connected_components(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_node("d")
        g.add_edge("a", "b")
        g.add_edge("c", "d")
        wccs = weakly_connected_components(g)
        assert len(wccs) == 2

    def test_is_strongly_connected(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        assert is_strongly_connected(g) is True

    def test_is_weakly_connected(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        assert is_weakly_connected(g) is True


class TestDAG:
    def test_topological_sort(self):
        g = make_chain()
        order = topological_sort(g)
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")
        assert order.index("c") < order.index("d")

    def test_topological_sort_cycle(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        with pytest.raises(ValueError):
            topological_sort(g)

    def test_ancestors(self):
        g = make_chain()
        anc = sorted(ancestors(g, "c"))
        assert anc == ["a", "b"]

    def test_descendants(self):
        g = make_chain()
        desc = sorted(descendants(g, "b"))
        assert desc == ["c", "d"]

    def test_longest_path(self):
        g = make_chain()
        result = longest_path(g)
        assert result.length == 3
        assert result.path == ["a", "b", "c", "d"]

    def test_critical_path(self):
        from kaos_graph.algorithms import critical_path

        g = Graph()
        g.add_node("start", latency_ms=0.0)
        g.add_node("fast", latency_ms=10.0)
        g.add_node("slow", latency_ms=500.0)
        g.add_node("end", latency_ms=5.0)
        g.add_edge("start", "fast")
        g.add_edge("start", "slow")
        g.add_edge("fast", "end")
        g.add_edge("slow", "end")

        result = critical_path(g, weight="latency_ms")
        assert result.cost >= 505.0  # slow + end
        assert "slow" in result.path
        assert "end" in result.path

    def test_critical_path_empty(self):
        from kaos_graph.algorithms import critical_path

        g = Graph()
        result = critical_path(g)
        assert result.cost == 0.0
        assert result.path == []


class TestCentrality:
    def test_pagerank(self):
        g = Graph()
        g.add_node("hub")
        for i in range(5):
            g.add_node(f"leaf{i}")
            g.add_edge(f"leaf{i}", "hub")
        ranks = pagerank(g)
        assert ranks[0].node_id == "hub"
        assert ranks[0].score > ranks[1].score

    def test_degree_centrality(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("a", "c")
        dc = degree_centrality(g)
        a_rank = next(r for r in dc if r.node_id == "a")
        assert a_rank.score == 1.0  # 2 / (3-1) = 1.0

    def test_in_degree_centrality(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "c")
        g.add_edge("b", "c")
        idc = in_degree_centrality(g)
        c_rank = next(r for r in idc if r.node_id == "c")
        assert c_rank.score == 1.0  # 2 / (3-1) = 1.0

    def test_betweenness_centrality_line(self):
        """Line graph a->b->c->d: b and c have high betweenness."""
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_node("d")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "d")
        bc = betweenness_centrality(g, normalized=False)
        scores = {r.node_id: r.score for r in bc}
        # Endpoints have 0 betweenness
        assert scores["a"] == 0.0
        assert scores["d"] == 0.0
        # b and c each lie on 2 shortest paths
        assert abs(scores["b"] - 2.0) < 1e-9
        assert abs(scores["c"] - 2.0) < 1e-9

    def test_betweenness_centrality_normalized(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_node("d")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "d")
        bc = betweenness_centrality(g, normalized=True)
        scores = {r.node_id: r.score for r in bc}
        # Normalized by (V-1)(V-2) = 3*2 = 6
        assert abs(scores["b"] - 2.0 / 6.0) < 1e-9

    def test_betweenness_centrality_empty(self):
        g = Graph()
        bc = betweenness_centrality(g)
        assert bc == []

    def test_closeness_centrality_line(self):
        """Line graph a->b->c: a has closeness 2/3, b has 1.0, c has 0."""
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        cc = closeness_centrality(g)
        scores = {r.node_id: r.score for r in cc}
        assert abs(scores["a"] - 2.0 / 3.0) < 1e-9
        assert abs(scores["b"] - 1.0) < 1e-9
        assert scores["c"] == 0.0

    def test_closeness_centrality_empty(self):
        g = Graph()
        cc = closeness_centrality(g)
        assert cc == []

    def test_eigenvector_centrality_cycle(self):
        """Cycle a->b->c->a: all nodes converge to equal scores."""
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "a")
        ec = eigenvector_centrality(g, iterations=1000, tolerance=1e-10)
        assert len(ec) == 3
        expected = 1.0 / (3.0**0.5)
        for r in ec:
            assert abs(r.score - expected) < 1e-6

    def test_eigenvector_centrality_convergence(self):
        """Triangle + extra source: verifies convergence and normalization."""
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_node("d")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "a")
        g.add_edge("d", "a")
        ec = eigenvector_centrality(g, iterations=1000, tolerance=1e-10)
        assert len(ec) == 4
        scores = {r.node_id: r.score for r in ec}
        # d has 0 incoming -> score ~0
        assert scores["d"] < 1e-10
        # L2 norm should be ~1.0
        norm = sum(r.score**2 for r in ec) ** 0.5
        assert abs(norm - 1.0) < 1e-6

    def test_eigenvector_centrality_empty(self):
        g = Graph()
        ec = eigenvector_centrality(g)
        assert ec == []


class TestStructure:
    def test_density(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        d = density(g)
        assert d == 0.5  # 1 / (2*1) = 0.5

    def test_condensation(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        g.add_edge("b", "c")
        dag = condensation(g)
        assert dag.n_nodes == 2
        assert dag.n_edges == 1
        assert dag.is_dag()

    def test_maximum_matching(self):
        g = Graph(directed=False)
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_node("d")
        g.add_edge("a", "b")
        g.add_edge("c", "d")
        m = maximum_matching(g)
        assert len(m) == 2

    def test_is_bipartite_even_cycle(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_node("d")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "d")
        g.add_edge("d", "a")
        assert is_bipartite(g) is True

    def test_is_bipartite_odd_cycle(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "a")
        assert is_bipartite(g) is False

    def test_is_bipartite_tree(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("a", "c")
        assert is_bipartite(g) is True

    def test_is_bipartite_empty(self):
        g = Graph()
        assert is_bipartite(g) is True

    def test_is_bipartite_self_loop(self):
        g = Graph()
        g.add_node("a")
        g.add_edge("a", "a")
        assert is_bipartite(g) is False

    def test_transitive_closure_chain(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        tc = transitive_closure(g)
        assert tc.n_nodes == 3
        assert tc.n_edges == 3  # a->b, b->c, a->c (transitive)
        assert tc.has_edge("a", "c")

    def test_transitive_closure_longer_chain(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_node("d")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "d")
        tc = transitive_closure(g)
        assert tc.n_nodes == 4
        # 3 original + 3 transitive (a->c, a->d, b->d) = 6
        assert tc.n_edges == 6
        assert tc.has_edge("a", "c")
        assert tc.has_edge("a", "d")
        assert tc.has_edge("b", "d")


class TestAllSimplePaths:
    def test_diamond(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_node("d")
        g.add_edge("a", "b")
        g.add_edge("a", "c")
        g.add_edge("b", "d")
        g.add_edge("c", "d")
        paths = all_simple_paths(g, "a", "d")
        paths.sort()
        assert len(paths) == 2
        assert paths[0] == ["a", "b", "d"]
        assert paths[1] == ["a", "c", "d"]

    def test_with_max_depth(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_node("d")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "d")
        g.add_edge("a", "c")
        # max_depth=3: at most 3 nodes in path (1 intermediate)
        paths = all_simple_paths(g, "a", "d", max_depth=3)
        # Only a->c->d (3 nodes). a->b->c->d has 4 nodes, excluded.
        assert len(paths) == 1
        assert paths[0] == ["a", "c", "d"]

    def test_no_path(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        paths = all_simple_paths(g, "a", "b")
        assert paths == []

    def test_invalid_node(self):
        g = Graph()
        with pytest.raises(KeyError):
            all_simple_paths(g, "missing", "also_missing")


class TestFindCycles:
    def test_no_cycles(self):
        g = make_chain()
        cycles = find_cycles(g)
        assert cycles == []

    def test_single_cycle(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "a")
        cycles = find_cycles(g)
        assert len(cycles) == 1
        assert len(cycles[0]) == 3

    def test_self_loop(self):
        g = Graph()
        g.add_node("a")
        g.add_edge("a", "a")
        cycles = find_cycles(g)
        assert len(cycles) == 1
        assert cycles[0] == ["a"]

    def test_multiple_cycles(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_node("d")
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        g.add_edge("c", "d")
        g.add_edge("d", "c")
        cycles = find_cycles(g)
        assert len(cycles) == 2


def _make_two_cliques() -> Graph:
    """Two 4-cliques connected by a single bridge edge."""
    g = Graph(directed=False)
    # Clique 1: a, b, c, d
    for nid in ["a", "b", "c", "d"]:
        g.add_node(nid)
    for s, t in [("a", "b"), ("a", "c"), ("a", "d"), ("b", "c"), ("b", "d"), ("c", "d")]:
        g.add_edge(s, t)
    # Clique 2: e, f, g, h
    for nid in ["e", "f", "g", "h"]:
        g.add_node(nid)
    for s, t in [("e", "f"), ("e", "g"), ("e", "h"), ("f", "g"), ("f", "h"), ("g", "h")]:
        g.add_edge(s, t)
    # Bridge
    g.add_edge("d", "e")
    return g


class TestLouvainCommunities:
    def test_two_cliques(self):
        g = _make_two_cliques()
        communities = louvain_communities(g)
        assert len(communities) == 2
        sizes = sorted(len(c) for c in communities)
        assert sizes == [4, 4]
        # Nodes in same clique should be in same community
        comm_of = {nid: i for i, c in enumerate(communities) for nid in c}
        assert comm_of["a"] == comm_of["b"] == comm_of["c"] == comm_of["d"]
        assert comm_of["e"] == comm_of["f"] == comm_of["g"] == comm_of["h"]
        assert comm_of["a"] != comm_of["e"]

    def test_single_node(self):
        g = Graph()
        g.add_node("x")
        communities = louvain_communities(g)
        assert len(communities) == 1
        assert communities[0] == ["x"]

    def test_empty_graph(self):
        g = Graph()
        communities = louvain_communities(g)
        assert communities == []

    def test_complete_graph(self):
        g = Graph(directed=False)
        for nid in ["a", "b", "c", "d"]:
            g.add_node(nid)
        for s, t in [("a", "b"), ("a", "c"), ("a", "d"), ("b", "c"), ("b", "d"), ("c", "d")]:
            g.add_edge(s, t)
        communities = louvain_communities(g)
        assert len(communities) == 1
        assert len(communities[0]) == 4

    def test_disconnected_nodes(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        communities = louvain_communities(g)
        assert len(communities) == 3


class TestLabelPropagation:
    def test_two_cliques(self):
        g = _make_two_cliques()
        communities = label_propagation(g)
        assert len(communities) == 2
        sizes = sorted(len(c) for c in communities)
        assert sizes == [4, 4]
        comm_of = {nid: i for i, c in enumerate(communities) for nid in c}
        assert comm_of["a"] == comm_of["b"] == comm_of["c"] == comm_of["d"]
        assert comm_of["e"] == comm_of["f"] == comm_of["g"] == comm_of["h"]
        assert comm_of["a"] != comm_of["e"]

    def test_single_node(self):
        g = Graph()
        g.add_node("x")
        communities = label_propagation(g)
        assert len(communities) == 1
        assert communities[0] == ["x"]

    def test_empty_graph(self):
        g = Graph()
        communities = label_propagation(g)
        assert communities == []

    def test_complete_graph(self):
        g = Graph(directed=False)
        for nid in ["a", "b", "c", "d"]:
            g.add_node(nid)
        for s, t in [("a", "b"), ("a", "c"), ("a", "d"), ("b", "c"), ("b", "d"), ("c", "d")]:
            g.add_edge(s, t)
        communities = label_propagation(g)
        assert len(communities) == 1
        assert len(communities[0]) == 4

    def test_disconnected_nodes(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        communities = label_propagation(g)
        assert len(communities) == 3


# ─── DFS Events ───────────────────────────────────────────────────────────


class TestDFSEvents:
    def test_chain(self):
        g = make_chain()
        events = dfs_events(g, "a")
        # 4 enters + 4 exits = 8 events
        assert len(events) == 8
        assert isinstance(events[0], DfsEvent)
        assert events[0] == DfsEvent(node_id="a", event="enter")
        assert events[-1] == DfsEvent(node_id="a", event="exit")

    def test_every_node_enters_and_exits(self):
        g = make_chain()
        events = dfs_events(g, "a")
        for node in ["a", "b", "c", "d"]:
            enters = [ev for ev in events if ev.node_id == node and ev.event == "enter"]
            exits = [ev for ev in events if ev.node_id == node and ev.event == "exit"]
            assert len(enters) == 1, f"{node} should enter once"
            assert len(exits) == 1, f"{node} should exit once"

    def test_enter_before_exit(self):
        g = make_chain()
        events = dfs_events(g, "a")
        for node in ["a", "b", "c", "d"]:
            enter_pos = next(
                i for i, ev in enumerate(events) if ev.node_id == node and ev.event == "enter"
            )
            exit_pos = next(
                i for i, ev in enumerate(events) if ev.node_id == node and ev.event == "exit"
            )
            assert enter_pos < exit_pos, f"Enter before exit for {node}"

    def test_missing_source(self):
        g = Graph()
        with pytest.raises(KeyError):
            dfs_events(g, "missing")


# ─── Articulation Points ──────────────────────────────────────────────────


class TestArticulationPoints:
    def test_linear(self):
        """a -- b -- c: b is articulation point."""
        g = Graph(directed=False)
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        points = articulation_points(g)
        assert points == ["b"]

    def test_triangle(self):
        """Triangle: no articulation points."""
        g = Graph(directed=False)
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "a")
        points = articulation_points(g)
        assert points == []

    def test_bridge_graph(self):
        """Two triangles connected by bridge: c and d are articulation points."""
        g = Graph(directed=False)
        for nid in ["a", "b", "c", "d", "e", "f"]:
            g.add_node(nid)
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "a")
        g.add_edge("c", "d")
        g.add_edge("d", "e")
        g.add_edge("e", "f")
        g.add_edge("f", "d")
        points = articulation_points(g)
        assert "c" in points
        assert "d" in points

    def test_empty(self):
        g = Graph(directed=False)
        points = articulation_points(g)
        assert points == []


# ─── Find Cycle Paths ─────────────────────────────────────────────────────


class TestFindCyclePaths:
    def test_triangle(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "a")
        paths = find_cycle_paths(g)
        assert len(paths) == 1
        # All nodes in the cycle should be in {a, b, c}
        assert set(paths[0]) <= {"a", "b", "c"}
        assert len(paths[0]) >= 2

    def test_self_loop(self):
        g = Graph()
        g.add_node("x")
        g.add_edge("x", "x")
        paths = find_cycle_paths(g)
        assert len(paths) == 1
        assert paths[0] == ["x"]

    def test_no_cycles(self):
        g = make_chain()
        paths = find_cycle_paths(g)
        assert paths == []

    def test_two_cycles(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_node("d")
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        g.add_edge("c", "d")
        g.add_edge("d", "c")
        paths = find_cycle_paths(g)
        assert len(paths) == 2
        for cycle in paths:
            assert len(cycle) == 2


# ─── k-Clique Communities ─────────────────────────────────────────────────


class TestKCliqueCommunities:
    def test_two_triangles_sharing_edge(self):
        """Two triangles sharing edge b-c merge into one community with k=3."""
        g = Graph(directed=False)
        for nid in ["a", "b", "c", "d"]:
            g.add_node(nid)
        g.add_edge("a", "b")
        g.add_edge("a", "c")
        g.add_edge("b", "c")
        g.add_edge("b", "d")
        g.add_edge("c", "d")
        communities = k_clique_communities(g, 3)
        assert len(communities) == 1
        assert len(communities[0]) == 4

    def test_separate_triangles(self):
        """Two separate triangles with k=3 produce two communities."""
        g = Graph(directed=False)
        for nid in ["a", "b", "c", "d", "e", "f"]:
            g.add_node(nid)
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "a")
        g.add_edge("d", "e")
        g.add_edge("e", "f")
        g.add_edge("f", "d")
        communities = k_clique_communities(g, 3)
        assert len(communities) == 2
        sizes = sorted(len(c) for c in communities)
        assert sizes == [3, 3]

    def test_no_cliques(self):
        """Linear graph: no k=3 cliques."""
        g = Graph(directed=False)
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        communities = k_clique_communities(g, 3)
        assert communities == []

    def test_empty(self):
        g = Graph(directed=False)
        communities = k_clique_communities(g, 3)
        assert communities == []


# ─── Property Filtering (Graph.nodes/edges with filter) ───────────────────


class TestPropertyFiltering:
    def test_nodes_filter(self):
        g = Graph()
        g.add_node("alice", type="person")
        g.add_node("bob", type="person")
        g.add_node("acme", type="org")
        persons = g.nodes(type="person")
        assert sorted(persons) == ["alice", "bob"]

    def test_nodes_no_filter(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        assert sorted(g.nodes()) == sorted(g.node_ids())

    def test_nodes_multiple_filters(self):
        g = Graph()
        g.add_node("alice", type="person", country="US")
        g.add_node("bob", type="person", country="UK")
        g.add_node("acme", type="org", country="US")
        result = g.nodes(type="person", country="US")
        assert result == ["alice"]

    def test_edges_filter(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("c")
        g.add_edge("a", "b", rel="friend")
        g.add_edge("b", "c", rel="colleague")
        friends = g.edges(rel="friend")
        assert len(friends) == 1
        assert friends[0].source == "a"
        assert friends[0].target == "b"

    def test_edges_no_filter(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        assert len(g.edges()) == 1

    def test_edges_filter_no_match(self):
        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b", rel="friend")
        assert g.edges(rel="enemy") == []
