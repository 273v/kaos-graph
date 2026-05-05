use petgraph::algo::{greedy_matching, maximum_matching};
use petgraph::visit::{EdgeRef, IntoEdgeReferences, NodeIndexable};

use crate::core::graph::{Graph, GraphInner};

/// Find all bridge edges via petgraph::algo::bridges.
/// Returns (source_id, target_id) pairs.
pub fn bridges(graph: &Graph) -> Vec<(String, String)> {
    match &graph.inner {
        GraphInner::Directed(g) => petgraph::algo::bridges(g)
            .map(|e| {
                let src = &g[e.source()].id;
                let tgt = &g[e.target()].id;
                (src.clone(), tgt.clone())
            })
            .collect(),
        GraphInner::Undirected(g) => petgraph::algo::bridges(g)
            .map(|e| {
                let src = &g[e.source()].id;
                let tgt = &g[e.target()].id;
                (src.clone(), tgt.clone())
            })
            .collect(),
    }
}

/// Find articulation points (cut vertices) in the graph.
///
/// An articulation point is a node whose removal increases the number of
/// connected components.
///
/// Implements Tarjan's algorithm manually to work with StableGraph
/// (petgraph's built-in version doesn't support StableGraph correctly).
pub fn articulation_points(graph: &Graph) -> Vec<String> {
    use petgraph::stable_graph::NodeIndex;
    use std::collections::{HashMap, HashSet};

    // Collect all node indices.
    let node_indices: Vec<NodeIndex> = match &graph.inner {
        GraphInner::Directed(g) => g.node_indices().collect(),
        GraphInner::Undirected(g) => g.node_indices().collect(),
    };

    if node_indices.is_empty() {
        return vec![];
    }

    // Map node index -> contiguous id for arrays.
    let mut idx_to_pos: HashMap<NodeIndex, usize> = HashMap::new();
    for (i, &ni) in node_indices.iter().enumerate() {
        idx_to_pos.insert(ni, i);
    }
    let n = node_indices.len();

    let mut disc = vec![0usize; n];
    let mut low = vec![0usize; n];
    let mut parent = vec![usize::MAX; n];
    let mut visited = vec![false; n];
    let mut ap_set: HashSet<usize> = HashSet::new();
    let mut timer = 0usize;

    // Get symmetric neighbors for a node.
    let get_neighbors = |node: NodeIndex| -> Vec<NodeIndex> {
        match &graph.inner {
            GraphInner::Directed(g) => {
                let mut nbrs: Vec<NodeIndex> = g
                    .neighbors_directed(node, petgraph::Direction::Outgoing)
                    .collect();
                for n in g.neighbors_directed(node, petgraph::Direction::Incoming) {
                    if !nbrs.contains(&n) {
                        nbrs.push(n);
                    }
                }
                nbrs
            }
            GraphInner::Undirected(g) => {
                petgraph::visit::IntoNeighbors::neighbors(g, node).collect()
            }
        }
    };

    // Iterative DFS for articulation points (Tarjan's algorithm).
    for start_i in 0..n {
        if visited[start_i] {
            continue;
        }

        // Stack entries: (node_pos, neighbor_iterator_index, children_count)
        let mut stack: Vec<(usize, usize, usize)> = vec![(start_i, 0, 0)];
        visited[start_i] = true;
        disc[start_i] = timer;
        low[start_i] = timer;
        timer += 1;

        // Pre-compute neighbor lists.
        let mut neighbors_cache: Vec<Vec<usize>> = vec![vec![]; n];
        // Lazily fill as we visit.

        while let Some(&mut (u, ref mut ni, ref mut children)) = stack.last_mut() {
            let u_node = node_indices[u];

            // Lazily compute neighbors.
            if neighbors_cache[u].is_empty() && *ni == 0 {
                let nbrs = get_neighbors(u_node);
                neighbors_cache[u] = nbrs
                    .into_iter()
                    .filter_map(|n| idx_to_pos.get(&n).copied())
                    .collect();
            }

            if *ni < neighbors_cache[u].len() {
                let v = neighbors_cache[u][*ni];
                *ni += 1;

                if !visited[v] {
                    visited[v] = true;
                    parent[v] = u;
                    disc[v] = timer;
                    low[v] = timer;
                    timer += 1;
                    *children += 1;
                    stack.push((v, 0, 0));
                } else if v != parent[u] {
                    low[u] = low[u].min(disc[v]);
                }
            } else {
                // Done with all neighbors of u. Pop and update parent.
                let (u_final, _, children_final) = stack.pop().unwrap();
                if let Some(&mut (pu, _, _)) = stack.last_mut() {
                    low[pu] = low[pu].min(low[u_final]);

                    // Non-root: if low[u] >= disc[parent], parent is AP.
                    if parent[pu] != usize::MAX && low[u_final] >= disc[pu] {
                        ap_set.insert(pu);
                    }
                } else {
                    // Root node: AP if it has 2+ children in DFS tree.
                    if children_final > 1 {
                        ap_set.insert(u_final);
                    }
                }
            }
        }
    }

    let mut result: Vec<String> = ap_set
        .into_iter()
        .map(|pos| graph.id_of(node_indices[pos]).to_string())
        .collect();
    result.sort();
    result
}

/// Greedy matching. Returns matched (source_id, target_id) pairs.
/// O(|V| + |E|) time.
pub fn greedy_match(graph: &Graph) -> Vec<(String, String)> {
    match &graph.inner {
        GraphInner::Directed(g) => {
            let matching = greedy_matching(g);
            matching
                .edges()
                .map(|(a, b)| (graph.id_of(a).to_string(), graph.id_of(b).to_string()))
                .collect()
        }
        GraphInner::Undirected(g) => {
            let matching = greedy_matching(g);
            matching
                .edges()
                .map(|(a, b)| (graph.id_of(a).to_string(), graph.id_of(b).to_string()))
                .collect()
        }
    }
}

/// Maximum matching via Gabow's algorithm. Returns matched (source_id, target_id) pairs.
/// O(|V|^3) time.
pub fn max_matching(graph: &Graph) -> Vec<(String, String)> {
    match &graph.inner {
        GraphInner::Directed(g) => {
            let matching = maximum_matching(g);
            matching
                .edges()
                .map(|(a, b)| (graph.id_of(a).to_string(), graph.id_of(b).to_string()))
                .collect()
        }
        GraphInner::Undirected(g) => {
            let matching = maximum_matching(g);
            matching
                .edges()
                .map(|(a, b)| (graph.id_of(a).to_string(), graph.id_of(b).to_string()))
                .collect()
        }
    }
}

/// Maximal cliques via Bron-Kerbosch with pivoting.
/// Returns list of cliques, each clique is a list of node IDs.
///
/// Bron-Kerbosch's worst-case is 3^(N/3) cliques on Turán graphs, so on
/// dense input this is exponential in node count. The PyO3 binding wraps
/// this with :func:`maximal_cliques_capped` (audit follow-up #2) which
/// applies an upfront node-count gate so peak CPU/memory is bounded
/// at the *entry* point, not just the result list.
pub fn maximal_cliques(graph: &Graph) -> Vec<Vec<String>> {
    match &graph.inner {
        GraphInner::Directed(g) => petgraph::algo::maximal_cliques(g)
            .into_iter()
            .map(|clique| {
                clique
                    .into_iter()
                    .map(|idx| graph.id_of(idx).to_string())
                    .collect()
            })
            .collect(),
        GraphInner::Undirected(g) => petgraph::algo::maximal_cliques(g)
            .into_iter()
            .map(|clique| {
                clique
                    .into_iter()
                    .map(|idx| graph.id_of(idx).to_string())
                    .collect()
            })
            .collect(),
    }
}

/// Maximal cliques with an upfront node-count gate (audit follow-up #2).
///
/// Refuses inputs larger than ``max_input_nodes`` because Bron-Kerbosch's
/// worst case is 3^(N/3) cliques. After the gate, falls through to
/// :func:`maximal_cliques`; result list is truncated at ``max_cliques``
/// as a second guard.
pub fn maximal_cliques_capped(
    graph: &Graph,
    max_input_nodes: usize,
    max_cliques: usize,
) -> Result<Vec<Vec<String>>, String> {
    if graph.n_nodes() > max_input_nodes {
        return Err(format!(
            "maximal_cliques refuses inputs larger than max_input_nodes={} \
             (graph has {} nodes); Bron-Kerbosch's worst case is 3^(N/3) \
             cliques. Raise KaosGraphSettings.max_nodes if your input \
             genuinely warrants it.",
            max_input_nodes,
            graph.n_nodes()
        ));
    }
    let mut all = maximal_cliques(graph);
    if all.len() > max_cliques {
        all.truncate(max_cliques);
    }
    Ok(all)
}

/// Graph density: |E| / (|V| * (|V| - 1)) for directed,
/// 2*|E| / (|V| * (|V| - 1)) for undirected.
pub fn density(graph: &Graph) -> f64 {
    let n = graph.n_nodes() as f64;
    let e = graph.n_edges() as f64;
    if n <= 1.0 {
        return 0.0;
    }
    let max_edges = n * (n - 1.0);
    if graph.is_directed() {
        e / max_edges
    } else {
        // Undirected: max possible edges = n*(n-1)/2. Density = e / (n*(n-1)/2) = 2e / (n*(n-1)).
        2.0 * e / max_edges
    }
}

/// Check if a graph is bipartite via BFS 2-coloring.
///
/// Handles disconnected graphs by running BFS from each unvisited node.
pub fn is_bipartite(graph: &Graph) -> bool {
    match &graph.inner {
        GraphInner::Directed(inner) => {
            let bound = inner.node_bound();
            let mut color = vec![0u8; bound];

            for start in inner.node_indices() {
                let si = start.index();
                if color[si] != 0 {
                    continue;
                }
                color[si] = 1;
                let mut queue = std::collections::VecDeque::new();
                queue.push_back(start);

                while let Some(node) = queue.pop_front() {
                    let node_color = color[node.index()];
                    let neighbor_color = if node_color == 1 { 2 } else { 1 };

                    for neighbor in inner.neighbors_directed(node, petgraph::Direction::Outgoing) {
                        let ni = neighbor.index();
                        if color[ni] == 0 {
                            color[ni] = neighbor_color;
                            queue.push_back(neighbor);
                        } else if color[ni] == node_color {
                            return false;
                        }
                    }
                    for neighbor in inner.neighbors_directed(node, petgraph::Direction::Incoming) {
                        let ni = neighbor.index();
                        if color[ni] == 0 {
                            color[ni] = neighbor_color;
                            queue.push_back(neighbor);
                        } else if color[ni] == node_color {
                            return false;
                        }
                    }
                }
            }

            true
        }
        GraphInner::Undirected(inner) => {
            let bound = inner.node_bound();
            let mut color = vec![0u8; bound];

            for start in inner.node_indices() {
                let si = start.index();
                if color[si] != 0 {
                    continue;
                }
                color[si] = 1;
                let mut queue = std::collections::VecDeque::new();
                queue.push_back(start);

                while let Some(node) = queue.pop_front() {
                    let node_color = color[node.index()];
                    let neighbor_color = if node_color == 1 { 2 } else { 1 };

                    for neighbor in petgraph::visit::IntoNeighbors::neighbors(inner, node) {
                        let ni = neighbor.index();
                        if color[ni] == 0 {
                            color[ni] = neighbor_color;
                            queue.push_back(neighbor);
                        } else if color[ni] == node_color {
                            return false;
                        }
                    }
                }
            }

            true
        }
    }
}

/// Condensation: contract each SCC into a single node.
/// Returns a new DAG where each node ID is the comma-joined IDs of the original SCC.
///
/// Only meaningful for directed graphs.
pub fn condensation(graph: &Graph) -> Graph {
    match &graph.inner {
        GraphInner::Directed(inner) => {
            let sccs = petgraph::algo::tarjan_scc(inner);

            let mut dag = Graph::new(true);
            let mut node_to_scc = std::collections::HashMap::new();
            let mut scc_ids = Vec::new();

            for (i, scc) in sccs.iter().enumerate() {
                let scc_id: String = {
                    let mut ids: Vec<&str> = scc.iter().map(|&idx| graph.id_of(idx)).collect();
                    ids.sort();
                    ids.join(",")
                };
                scc_ids.push(scc_id.clone());
                dag.add_node(&scc_id, std::collections::HashMap::new()).ok();
                for &idx in scc {
                    node_to_scc.insert(idx, i);
                }
            }

            let mut added_edges = std::collections::HashSet::new();
            for edge in inner.edge_references() {
                let src_scc = node_to_scc[&edge.source()];
                let tgt_scc = node_to_scc[&edge.target()];
                if src_scc != tgt_scc {
                    let pair = (src_scc, tgt_scc);
                    if added_edges.insert(pair) {
                        dag.add_edge(
                            &scc_ids[src_scc],
                            &scc_ids[tgt_scc],
                            std::collections::HashMap::new(),
                        )
                        .ok();
                    }
                }
            }

            dag
        }
        // For undirected, condensation is not meaningful (all connected = one SCC).
        GraphInner::Undirected(_) => {
            // Return a graph with one node per connected component.
            let wccs = super::components::weakly_connected_components(graph);
            let mut dag = Graph::new(true);
            for wcc in &wccs {
                let mut ids = wcc.clone();
                ids.sort();
                let id = ids.join(",");
                dag.add_node(&id, std::collections::HashMap::new()).ok();
            }
            dag
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn test_bridges() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "a", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "b", HashMap::new()).unwrap();

        let br = bridges(&g);
        assert!(!br.is_empty());
    }

    #[test]
    fn test_greedy_matching() {
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();

        let m = greedy_match(&g);
        assert!(!m.is_empty());
    }

    #[test]
    fn test_max_matching() {
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();

        let m = max_matching(&g);
        assert_eq!(m.len(), 2);
    }

    #[test]
    fn test_density() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();

        let d = density(&g);
        assert_eq!(d, 0.5); // 1 edge out of 2 possible (directed)
    }

    #[test]
    fn test_density_undirected() {
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();

        let d = density(&g);
        assert_eq!(d, 1.0); // 1 edge out of 1 possible (undirected: n*(n-1)/2 = 1)
    }

    #[test]
    fn test_condensation() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "a", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();

        let dag = condensation(&g);
        assert_eq!(dag.n_nodes(), 2);
        assert_eq!(dag.n_edges(), 1);
        assert!(dag.is_dag());
    }

    #[test]
    fn test_is_bipartite_even_cycle() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();
        g.add_edge("d", "a", HashMap::new()).unwrap();

        assert!(is_bipartite(&g));
    }

    #[test]
    fn test_is_bipartite_odd_cycle() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "a", HashMap::new()).unwrap();

        assert!(!is_bipartite(&g));
    }

    #[test]
    fn test_is_bipartite_tree() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();

        assert!(is_bipartite(&g));
    }

    #[test]
    fn test_is_bipartite_disconnected() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();

        assert!(is_bipartite(&g));
    }

    #[test]
    fn test_is_bipartite_self_loop() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_edge("a", "a", HashMap::new()).unwrap();

        assert!(!is_bipartite(&g));
    }

    #[test]
    fn test_is_bipartite_empty() {
        let g = Graph::new(true);
        assert!(is_bipartite(&g));
    }

    #[test]
    fn test_is_bipartite_single_node() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        assert!(is_bipartite(&g));
    }

    #[test]
    fn test_articulation_points_linear() {
        // a -- b -- c (undirected): b is articulation point
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();

        let points = articulation_points(&g);
        assert_eq!(points, vec!["b"]);
    }

    #[test]
    fn test_articulation_points_triangle() {
        // a -- b -- c -- a: no articulation points (cycle)
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "a", HashMap::new()).unwrap();

        let points = articulation_points(&g);
        assert!(points.is_empty());
    }

    #[test]
    fn test_articulation_points_bridge_graph() {
        // Two triangles connected by a single bridge: d is the articulation point.
        // a--b--c--a, c--d--e--f--d
        let mut g = Graph::new(false);
        for id in &["a", "b", "c", "d", "e", "f"] {
            g.add_node(id, HashMap::new()).unwrap();
        }
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "a", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();
        g.add_edge("d", "e", HashMap::new()).unwrap();
        g.add_edge("e", "f", HashMap::new()).unwrap();
        g.add_edge("f", "d", HashMap::new()).unwrap();

        let points = articulation_points(&g);
        assert!(points.contains(&"c".to_string()));
        assert!(points.contains(&"d".to_string()));
    }

    #[test]
    fn test_articulation_points_empty() {
        let g = Graph::new(false);
        let points = articulation_points(&g);
        assert!(points.is_empty());
    }
}
