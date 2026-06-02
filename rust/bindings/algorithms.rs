//! PyO3 bindings for graph algorithms.

use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::graph::PyGraph;
use crate::core::algorithms::{
    centrality, community, components, dag, paths, structure, traversal,
};

// --- Traversal ---

/// BFS traversal from a source node. Returns node IDs in BFS order.
#[pyfunction]
fn bfs(graph: &PyGraph, source: &str) -> PyResult<Vec<String>> {
    traversal::bfs(&graph.inner, source).map_err(pyo3::exceptions::PyKeyError::new_err)
}

/// DFS traversal from a source node. Returns node IDs in DFS (preorder).
#[pyfunction]
fn dfs(graph: &PyGraph, source: &str) -> PyResult<Vec<String>> {
    traversal::dfs(&graph.inner, source).map_err(pyo3::exceptions::PyKeyError::new_err)
}

/// BFS returning (node_id, depth) pairs.
#[pyfunction]
fn bfs_with_depth(graph: &PyGraph, source: &str) -> PyResult<Vec<(String, usize)>> {
    traversal::bfs_with_depth(&graph.inner, source).map_err(pyo3::exceptions::PyKeyError::new_err)
}

/// BFS returning only nodes at a specific depth.
#[pyfunction]
fn bfs_at_depth(graph: &PyGraph, source: &str, depth: usize) -> PyResult<Vec<String>> {
    traversal::bfs_at_depth(&graph.inner, source, depth)
        .map_err(pyo3::exceptions::PyKeyError::new_err)
}

/// DFS with enter/exit events. Returns (node_id, event_str) pairs.
/// event_str is "enter" or "exit".
#[pyfunction]
fn dfs_events(graph: &PyGraph, source: &str) -> PyResult<Vec<(String, String)>> {
    traversal::dfs_events(&graph.inner, source)
        .map(|events| {
            events
                .into_iter()
                .map(|(id, is_enter)| (id, if is_enter { "enter" } else { "exit" }.to_string()))
                .collect()
        })
        .map_err(pyo3::exceptions::PyKeyError::new_err)
}

// --- Paths ---

/// Single-source shortest paths via Dijkstra. Returns dict of {node_id: cost}.
#[pyfunction]
#[pyo3(signature = (graph, source, target=None, weight_key=None))]
fn shortest_paths(
    py: Python<'_>,
    graph: &PyGraph,
    source: &str,
    target: Option<&str>,
    weight_key: Option<&str>,
) -> PyResult<Py<PyDict>> {
    let costs = paths::shortest_paths(&graph.inner, source, target, weight_key)
        .map_err(pyo3::exceptions::PyKeyError::new_err)?;
    let dict = PyDict::new(py);
    for (id, cost) in &costs {
        dict.set_item(id, cost)?;
    }
    Ok(dict.into())
}

/// Shortest path distance between two nodes. Returns float or None.
#[pyfunction]
#[pyo3(signature = (graph, source, target, weight_key=None))]
fn shortest_path_length(
    graph: &PyGraph,
    source: &str,
    target: &str,
    weight_key: Option<&str>,
) -> PyResult<Option<f64>> {
    paths::shortest_path_length(&graph.inner, source, target, weight_key)
        .map_err(pyo3::exceptions::PyKeyError::new_err)
}

/// Check if a path exists between two nodes.
#[pyfunction]
fn has_path(graph: &PyGraph, source: &str, target: &str) -> PyResult<bool> {
    paths::has_path(&graph.inner, source, target).map_err(pyo3::exceptions::PyKeyError::new_err)
}

/// A* shortest path. Returns dict with "cost" and "path" keys, or None.
#[pyfunction]
#[pyo3(signature = (graph, source, target, weight_key=None))]
fn astar_path(
    py: Python<'_>,
    graph: &PyGraph,
    source: &str,
    target: &str,
    weight_key: Option<&str>,
) -> PyResult<Option<Py<PyDict>>> {
    let result = paths::astar_path(&graph.inner, source, target, weight_key)
        .map_err(pyo3::exceptions::PyKeyError::new_err)?;
    match result {
        Some((cost, path)) => {
            let dict = PyDict::new(py);
            dict.set_item("cost", cost)?;
            dict.set_item("path", path)?;
            Ok(Some(dict.into()))
        }
        None => Ok(None),
    }
}

/// Bellman-Ford shortest paths. Returns dict of {node_id: cost}.
/// Supports negative weights. Raises ValueError on negative cycle.
#[pyfunction]
#[pyo3(signature = (graph, source, weight_key=None))]
fn bellman_ford_paths(
    py: Python<'_>,
    graph: &PyGraph,
    source: &str,
    weight_key: Option<&str>,
) -> PyResult<Py<PyDict>> {
    let costs = paths::bellman_ford_paths(&graph.inner, source, weight_key)
        .map_err(pyo3::exceptions::PyValueError::new_err)?;
    let dict = PyDict::new(py);
    for (id, cost) in &costs {
        dict.set_item(id, cost)?;
    }
    Ok(dict.into())
}

/// All simple (non-repeating) paths from source to target.
///
/// ``max_depth`` limits total path length (number of nodes); the default
/// (``32``) prevents the algorithm from running unbounded on large graphs
/// (audit A2-#3). ``max_paths`` is applied to the *iterator* via
/// ``.take(max_paths)`` so enumeration stops at the cap (audit follow-up
/// #2: bounds peak CPU/memory, not just the returned list).
#[pyfunction]
#[pyo3(signature = (graph, source, target, max_depth=32, max_paths=10000))]
fn all_simple_paths(
    graph: &PyGraph,
    source: &str,
    target: &str,
    max_depth: usize,
    max_paths: usize,
) -> PyResult<Vec<Vec<String>>> {
    paths::all_simple_paths_capped(&graph.inner, source, target, Some(max_depth), max_paths)
        .map_err(pyo3::exceptions::PyKeyError::new_err)
}

/// Find all cycles in the graph (SCC-based). Returns list of node-ID lists.
#[pyfunction]
fn find_cycles(graph: &PyGraph) -> Vec<Vec<String>> {
    paths::find_cycles(&graph.inner)
}

/// Find one representative cycle path per SCC. Returns list of ordered cycle paths.
#[pyfunction]
fn find_cycle_paths(graph: &PyGraph) -> Vec<Vec<String>> {
    paths::find_cycle_paths(&graph.inner)
}

// --- Components ---

/// Strongly connected components via Tarjan's algorithm.
/// Returns list of components (each is a list of node IDs).
#[pyfunction]
fn strongly_connected_components(graph: &PyGraph) -> Vec<Vec<String>> {
    components::strongly_connected_components(&graph.inner)
}

/// Number of weakly connected components.
#[pyfunction]
fn num_connected_components(graph: &PyGraph) -> usize {
    components::num_connected_components(&graph.inner)
}

/// Weakly connected components as lists of node IDs.
#[pyfunction]
fn weakly_connected_components(graph: &PyGraph) -> Vec<Vec<String>> {
    components::weakly_connected_components(&graph.inner)
}

/// Connected-component labels over an integer edge list (no Graph build).
/// Returns a label per node (smallest node id in its component). Raises
/// ValueError if an edge references a node >= n_nodes.
#[pyfunction]
fn connected_components_from_edges(n_nodes: usize, edges: Vec<(u32, u32)>) -> PyResult<Vec<u32>> {
    components::connected_components_from_edges(n_nodes, &edges)
        .map_err(pyo3::exceptions::PyValueError::new_err)
}

/// Check if the graph is strongly connected.
#[pyfunction]
fn is_strongly_connected(graph: &PyGraph) -> bool {
    components::is_strongly_connected(&graph.inner)
}

/// Check if the graph is weakly connected.
#[pyfunction]
fn is_weakly_connected(graph: &PyGraph) -> bool {
    components::is_weakly_connected(&graph.inner)
}

// --- DAG ---

/// Topological sort. Returns node IDs in topological order.
/// Raises ValueError if graph has cycles.
#[pyfunction]
fn topological_sort(graph: &PyGraph) -> PyResult<Vec<String>> {
    dag::topological_sort(&graph.inner).map_err(pyo3::exceptions::PyValueError::new_err)
}

/// All ancestors of a node (nodes that can reach it).
#[pyfunction]
fn ancestors(graph: &PyGraph, id: &str) -> PyResult<Vec<String>> {
    dag::ancestors(&graph.inner, id).map_err(pyo3::exceptions::PyKeyError::new_err)
}

/// All descendants of a node (nodes reachable from it).
#[pyfunction]
fn descendants(graph: &PyGraph, id: &str) -> PyResult<Vec<String>> {
    dag::descendants(&graph.inner, id).map_err(pyo3::exceptions::PyKeyError::new_err)
}

/// Longest path in a DAG. Returns dict with "length" and "path" keys.
#[pyfunction]
fn longest_path(py: Python<'_>, graph: &PyGraph) -> PyResult<Py<PyDict>> {
    let (length, path) =
        dag::longest_path(&graph.inner).map_err(pyo3::exceptions::PyValueError::new_err)?;
    let dict = PyDict::new(py);
    dict.set_item("length", length)?;
    dict.set_item("path", path)?;
    Ok(dict.into())
}

// --- Centrality ---

/// PageRank centrality. Returns list of (node_id, rank) tuples sorted by rank descending.
#[pyfunction]
#[pyo3(signature = (graph, damping_factor=0.85, iterations=100))]
fn pagerank(graph: &PyGraph, damping_factor: f64, iterations: usize) -> Vec<(String, f64)> {
    centrality::pagerank(&graph.inner, damping_factor, iterations)
}

/// Degree centrality. Returns list of (node_id, centrality) sorted descending.
#[pyfunction]
fn degree_centrality(graph: &PyGraph) -> Vec<(String, f64)> {
    centrality::degree_centrality(&graph.inner)
}

/// In-degree centrality. Returns list of (node_id, centrality) sorted descending.
#[pyfunction]
fn in_degree_centrality(graph: &PyGraph) -> Vec<(String, f64)> {
    centrality::in_degree_centrality(&graph.inner)
}

/// Out-degree centrality. Returns list of (node_id, centrality) sorted descending.
#[pyfunction]
fn out_degree_centrality(graph: &PyGraph) -> Vec<(String, f64)> {
    centrality::out_degree_centrality(&graph.inner)
}

/// Betweenness centrality (Brandes algorithm). Returns list of (node_id, centrality) sorted descending.
#[pyfunction]
#[pyo3(signature = (graph, normalized=true))]
fn betweenness_centrality(graph: &PyGraph, normalized: bool) -> Vec<(String, f64)> {
    centrality::betweenness_centrality(&graph.inner, normalized)
}

/// Closeness centrality (Wasserman-Faust). Returns list of (node_id, centrality) sorted descending.
#[pyfunction]
fn closeness_centrality(graph: &PyGraph) -> Vec<(String, f64)> {
    centrality::closeness_centrality(&graph.inner)
}

/// Eigenvector centrality (power iteration). Returns list of (node_id, centrality) sorted descending.
#[pyfunction]
#[pyo3(signature = (graph, iterations=100, tolerance=1e-6))]
fn eigenvector_centrality(
    graph: &PyGraph,
    iterations: usize,
    tolerance: f64,
) -> Vec<(String, f64)> {
    centrality::eigenvector_centrality(&graph.inner, iterations, tolerance)
}

// --- Community ---

/// Louvain community detection. Returns list of communities (each is a list of node IDs).
#[pyfunction]
fn louvain_communities(graph: &PyGraph) -> Vec<Vec<String>> {
    community::louvain_communities(&graph.inner)
}

/// Label propagation community detection. Returns list of communities (each is a list of node IDs).
#[pyfunction]
fn label_propagation(graph: &PyGraph) -> Vec<Vec<String>> {
    community::label_propagation(&graph.inner)
}

// --- Structure ---

/// Find bridge edges. Returns list of (source, target) tuples.
#[pyfunction]
fn bridges(graph: &PyGraph) -> Vec<(String, String)> {
    structure::bridges(&graph.inner)
}

/// Greedy matching. Returns list of (node_a, node_b) pairs.
#[pyfunction]
fn greedy_matching(graph: &PyGraph) -> Vec<(String, String)> {
    structure::greedy_match(&graph.inner)
}

/// Maximum matching (Gabow). Returns list of (node_a, node_b) pairs.
#[pyfunction]
fn maximum_matching(graph: &PyGraph) -> Vec<(String, String)> {
    structure::max_matching(&graph.inner)
}

/// Maximal cliques (Bron-Kerbosch). Returns list of cliques (each is a list
/// of node IDs).
///
/// Bron-Kerbosch's worst case is 3^(N/3) cliques on Turán graphs, so the
/// algorithm is exponential in node count. Audit follow-up #2: an upfront
/// ``max_input_nodes`` gate refuses oversized inputs at entry rather than
/// truncating after the fact; ``max_cliques`` is the second guard on the
/// returned list.
#[pyfunction]
#[pyo3(signature = (graph, max_input_nodes=1000, max_cliques=10000))]
fn maximal_cliques(
    graph: &PyGraph,
    max_input_nodes: usize,
    max_cliques: usize,
) -> PyResult<Vec<Vec<String>>> {
    structure::maximal_cliques_capped(&graph.inner, max_input_nodes, max_cliques)
        .map_err(pyo3::exceptions::PyValueError::new_err)
}

/// Graph density.
#[pyfunction]
fn density(graph: &PyGraph) -> f64 {
    structure::density(&graph.inner)
}

/// Check if the graph is bipartite (2-colorable).
#[pyfunction]
fn is_bipartite(graph: &PyGraph) -> bool {
    structure::is_bipartite(&graph.inner)
}

/// Transitive closure: add edge (u,v) for every pair where v is reachable from u.
/// Returns a new graph with all transitive edges added.
#[pyfunction]
fn transitive_closure(graph: &PyGraph) -> PyGraph {
    PyGraph {
        inner: dag::transitive_closure(&graph.inner),
    }
}

/// Condensation: contract SCCs into single nodes. Returns a new DAG.
#[pyfunction]
fn condensation(graph: &PyGraph) -> PyGraph {
    PyGraph {
        inner: structure::condensation(&graph.inner),
    }
}

/// Articulation points (cut vertices). Returns list of node IDs.
#[pyfunction]
fn articulation_points(graph: &PyGraph) -> Vec<String> {
    structure::articulation_points(&graph.inner)
}

/// k-clique communities. Returns list of communities (each is a list of node IDs).
#[pyfunction]
fn k_clique_communities(graph: &PyGraph, k: usize) -> Vec<Vec<String>> {
    community::k_clique_communities(&graph.inner, k)
}

/// Register the algorithms submodule.
pub(crate) fn register_module(parent: &Bound<'_, PyModule>) -> PyResult<()> {
    let m = PyModule::new(parent.py(), "algorithms")?;

    // Traversal
    m.add_function(wrap_pyfunction!(bfs, &m)?)?;
    m.add_function(wrap_pyfunction!(dfs, &m)?)?;
    m.add_function(wrap_pyfunction!(dfs_events, &m)?)?;
    m.add_function(wrap_pyfunction!(bfs_with_depth, &m)?)?;
    m.add_function(wrap_pyfunction!(bfs_at_depth, &m)?)?;

    // Paths
    m.add_function(wrap_pyfunction!(shortest_paths, &m)?)?;
    m.add_function(wrap_pyfunction!(shortest_path_length, &m)?)?;
    m.add_function(wrap_pyfunction!(has_path, &m)?)?;
    m.add_function(wrap_pyfunction!(astar_path, &m)?)?;
    m.add_function(wrap_pyfunction!(bellman_ford_paths, &m)?)?;
    m.add_function(wrap_pyfunction!(all_simple_paths, &m)?)?;
    m.add_function(wrap_pyfunction!(find_cycles, &m)?)?;
    m.add_function(wrap_pyfunction!(find_cycle_paths, &m)?)?;

    // Components
    m.add_function(wrap_pyfunction!(strongly_connected_components, &m)?)?;
    m.add_function(wrap_pyfunction!(num_connected_components, &m)?)?;
    m.add_function(wrap_pyfunction!(weakly_connected_components, &m)?)?;
    m.add_function(wrap_pyfunction!(connected_components_from_edges, &m)?)?;
    m.add_function(wrap_pyfunction!(is_strongly_connected, &m)?)?;
    m.add_function(wrap_pyfunction!(is_weakly_connected, &m)?)?;

    // DAG
    m.add_function(wrap_pyfunction!(topological_sort, &m)?)?;
    m.add_function(wrap_pyfunction!(ancestors, &m)?)?;
    m.add_function(wrap_pyfunction!(descendants, &m)?)?;
    m.add_function(wrap_pyfunction!(longest_path, &m)?)?;

    // Centrality
    m.add_function(wrap_pyfunction!(pagerank, &m)?)?;
    m.add_function(wrap_pyfunction!(degree_centrality, &m)?)?;
    m.add_function(wrap_pyfunction!(in_degree_centrality, &m)?)?;
    m.add_function(wrap_pyfunction!(out_degree_centrality, &m)?)?;
    m.add_function(wrap_pyfunction!(betweenness_centrality, &m)?)?;
    m.add_function(wrap_pyfunction!(closeness_centrality, &m)?)?;
    m.add_function(wrap_pyfunction!(eigenvector_centrality, &m)?)?;

    // Community
    m.add_function(wrap_pyfunction!(louvain_communities, &m)?)?;
    m.add_function(wrap_pyfunction!(label_propagation, &m)?)?;

    // Structure
    m.add_function(wrap_pyfunction!(bridges, &m)?)?;
    m.add_function(wrap_pyfunction!(greedy_matching, &m)?)?;
    m.add_function(wrap_pyfunction!(maximum_matching, &m)?)?;
    m.add_function(wrap_pyfunction!(maximal_cliques, &m)?)?;
    m.add_function(wrap_pyfunction!(density, &m)?)?;
    m.add_function(wrap_pyfunction!(is_bipartite, &m)?)?;
    m.add_function(wrap_pyfunction!(transitive_closure, &m)?)?;
    m.add_function(wrap_pyfunction!(condensation, &m)?)?;
    m.add_function(wrap_pyfunction!(articulation_points, &m)?)?;

    // Community
    m.add_function(wrap_pyfunction!(k_clique_communities, &m)?)?;

    parent.add_submodule(&m)?;
    parent
        .py()
        .import("sys")?
        .getattr("modules")?
        .set_item("kaos_graph._rust.algorithms", &m)?;

    Ok(())
}
