"""Performance benchmarks for kaos-graph, with optional NetworkX comparison.

Run: python tests/bench_performance.py
"""

from __future__ import annotations

import time
from pathlib import Path

from kaos_graph import Graph
from kaos_graph.algorithms import (
    bfs,
    degree_centrality,
    dfs,
    louvain_communities,
    pagerank,
    shortest_paths,
    strongly_connected_components,
    topological_sort,
    weakly_connected_components,
)

try:
    import networkx as nx

    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False


def make_random_dag(n_nodes: int, edges_per_node: int = 3) -> Graph:
    """Create a random DAG with n nodes."""
    import random

    random.seed(42)
    g = Graph(directed=True)
    for i in range(n_nodes):
        g.add_node(f"n{i}")
    for i in range(n_nodes):
        targets = random.sample(
            range(i + 1, min(i + 50, n_nodes)),
            min(edges_per_node, max(0, min(49, n_nodes - i - 1))),
        )
        for t in targets:
            g.add_edge(f"n{i}", f"n{t}")
    return g


def make_random_graph(n_nodes: int, edges_per_node: int = 5) -> Graph:
    """Create a random directed graph (may have cycles)."""
    import random

    random.seed(42)
    g = Graph(directed=True)
    for i in range(n_nodes):
        g.add_node(f"n{i}")
    for i in range(n_nodes):
        targets = random.sample(range(n_nodes), min(edges_per_node, n_nodes - 1))
        for t in targets:
            if t != i:
                g.add_edge(f"n{i}", f"n{t}")
    return g


def make_nx_graph(kaos_g: Graph) -> nx.DiGraph:
    """Convert a kaos-graph Graph to a NetworkX DiGraph."""
    nxg = nx.DiGraph()
    for nid in kaos_g.node_ids():
        nxg.add_node(nid)
    for edge in kaos_g.edges():
        weight = edge.properties.get("weight", 1.0) if edge.properties else 1.0
        nxg.add_edge(edge.source, edge.target, weight=weight)
    return nxg


def make_nx_dag(kaos_dag: Graph) -> nx.DiGraph:
    """Convert a kaos-graph DAG to a NetworkX DiGraph."""
    return make_nx_graph(kaos_dag)


def bench(name: str, fn, *args) -> float:
    """Time a function, return milliseconds."""
    start = time.perf_counter()
    fn(*args)
    elapsed = (time.perf_counter() - start) * 1000
    return elapsed


def run_benchmarks():
    print("=" * 70)
    print("kaos-graph Performance Benchmarks")
    print("=" * 70)
    if HAS_NETWORKX:
        print(f"  NetworkX {nx.__version__} detected -- comparison enabled")
    else:
        print("  NetworkX not installed -- comparison disabled")
        print("  Install with: uv pip install networkx")

    for n in [1_000, 10_000, 100_000]:
        g = make_random_graph(n)
        dag = make_random_dag(n)
        print(f"\n--- {n:,} nodes, {g.n_edges:,} edges ---")

        # kaos-graph benchmarks
        kaos_bfs = bench("bfs", bfs, g, "n0")
        kaos_dfs = bench("dfs", dfs, g, "n0")
        kaos_dijkstra = bench("dijkstra", shortest_paths, g, "n0")
        kaos_scc = bench("scc", strongly_connected_components, g)
        kaos_wcc = bench("wcc", weakly_connected_components, g)
        kaos_pr = bench("pr", pagerank, g, 0.85, 20)
        kaos_dc = bench("dc", degree_centrality, g)
        kaos_topo = bench("topo", topological_sort, dag)

        # NetworkX benchmarks (if available)
        nx_bfs = None
        nx_dfs = None
        nx_dijkstra = None
        nx_scc = None
        nx_wcc = None
        nx_pr = None
        nx_dc = None
        nx_topo = None

        if HAS_NETWORKX:
            nxg = make_nx_graph(g)
            nx_dag = make_nx_dag(dag)

            nx_bfs = bench("nx_bfs", lambda _g=nxg: list(nx.bfs_tree(_g, "n0")))
            nx_dfs = bench("nx_dfs", lambda _g=nxg: list(nx.dfs_preorder_nodes(_g, "n0")))
            nx_dijkstra = bench(
                "nx_dijkstra",
                lambda _g=nxg: dict(nx.single_source_dijkstra_path_length(_g, "n0")),
            )
            nx_scc = bench("nx_scc", lambda _g=nxg: list(nx.strongly_connected_components(_g)))
            nx_wcc = bench("nx_wcc", lambda _g=nxg: list(nx.weakly_connected_components(_g)))
            nx_pr = bench("nx_pr", lambda _g=nxg: nx.pagerank(_g, alpha=0.85, max_iter=20))
            nx_dc = bench("nx_dc", lambda _g=nxg: nx.degree_centrality(_g))
            nx_topo = bench("nx_topo", lambda _g=nx_dag: list(nx.topological_sort(_g)))

        # Print results table
        def fmt_row(name: str, kaos_ms: float, nx_ms: float | None) -> str:
            if nx_ms is not None:
                speedup = nx_ms / kaos_ms if kaos_ms > 0 else float("inf")
                return f"  {name:<18} {kaos_ms:>8.1f}ms   {nx_ms:>8.1f}ms   {speedup:>6.1f}x"
            return f"  {name:<18} {kaos_ms:>8.1f}ms"

        if HAS_NETWORKX:
            print(f"  {'Algorithm':<18} {'kaos-graph':>11}   {'NetworkX':>11}   {'Speedup':>7}")
            print(f"  {'-' * 18} {'-' * 11}   {'-' * 11}   {'-' * 7}")
        else:
            print(f"  {'Algorithm':<18} {'kaos-graph':>11}")
            print(f"  {'-' * 18} {'-' * 11}")

        print(fmt_row("BFS", kaos_bfs, nx_bfs))
        print(fmt_row("DFS", kaos_dfs, nx_dfs))
        print(fmt_row("Dijkstra", kaos_dijkstra, nx_dijkstra))
        print(fmt_row("SCC (Tarjan)", kaos_scc, nx_scc))
        print(fmt_row("WCC", kaos_wcc, nx_wcc))
        print(fmt_row("PageRank (20)", kaos_pr, nx_pr))
        print(fmt_row("Degree Cent.", kaos_dc, nx_dc))

        if n <= 10_000:
            kaos_louvain = bench("louvain", louvain_communities, g)
            if HAS_NETWORKX:
                nx_louvain = bench(
                    "nx_louvain",
                    lambda _g=nxg: list(nx.community.louvain_communities(_g.to_undirected())),
                )
                print(fmt_row("Louvain", kaos_louvain, nx_louvain))
            else:
                print(fmt_row("Louvain", kaos_louvain, None))

        print(fmt_row("Topo Sort", kaos_topo, nx_topo))

        # JSON round-trip
        start = time.perf_counter()
        j = g.to_json()
        ser_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        Graph.from_json(j)
        deser_ms = (time.perf_counter() - start) * 1000
        print(f"  JSON serialize:  {ser_ms:.1f}ms ({len(j):,} bytes)")
        print(f"  JSON deserial.:  {deser_ms:.1f}ms")

    # FOLIO benchmark
    folio_path = Path("/tmp/FOLIO/FOLIO.owl")
    if folio_path.exists():
        print("\n--- FOLIO OWL (18MB real ontology) ---")
        from kaos_graph.rdf import load_owl

        start = time.perf_counter()
        g, stats = load_owl(str(folio_path))
        load_ms = (time.perf_counter() - start) * 1000
        stats_summary = (
            f"{stats.total_triples:,} triples -> {stats.nodes:,} nodes, {stats.edges:,} edges"
        )
        print(f"  Parse OWL:      {load_ms:.1f}ms ({stats_summary})")
        print(f"  BFS:            {bench('bfs', bfs, g, g.node_ids()[0]):.1f}ms")
        print(f"  SCC:            {bench('scc', strongly_connected_components, g):.1f}ms")
        print(f"  WCC:            {bench('wcc', weakly_connected_components, g):.1f}ms")
        print(f"  PageRank (20):  {bench('pr', pagerank, g, 0.85, 20):.1f}ms")
        j = g.to_json()
        print(f"  JSON serialize:  {bench('ser', g.to_json):.1f}ms ({len(j):,} bytes)")
        print(f"  JSON deserial.:  {bench('deser', Graph.from_json, j):.1f}ms")


if __name__ == "__main__":
    run_benchmarks()
