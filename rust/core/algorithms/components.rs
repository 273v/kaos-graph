use petgraph::algo::tarjan_scc;
use petgraph::visit::EdgeRef;

use crate::core::graph::{Graph, GraphInner};

/// Strongly connected components via Tarjan's algorithm.
/// Returns a list of components, each component is a list of node IDs.
/// Components are in reverse topological order (sinks first).
///
/// For undirected graphs, every connected component is trivially strongly
/// connected, so this delegates to weakly_connected_components.
pub fn strongly_connected_components(graph: &Graph) -> Vec<Vec<String>> {
    match &graph.inner {
        GraphInner::Directed(g) => tarjan_scc(g)
            .into_iter()
            .map(|component| {
                component
                    .into_iter()
                    .map(|idx| graph.id_of(idx).to_string())
                    .collect()
            })
            .collect(),
        GraphInner::Undirected(_) => weakly_connected_components(graph),
    }
}

/// Number of weakly connected components.
/// Uses union-find because petgraph::algo::connected_components requires
/// NodeCompactIndexable, which StableGraph does not implement.
pub fn num_connected_components(graph: &Graph) -> usize {
    weakly_connected_components(graph).len()
}

/// Weakly connected components as lists of node IDs.
/// Uses union-find. For undirected graphs this is the same as connected components.
pub fn weakly_connected_components(graph: &Graph) -> Vec<Vec<String>> {
    use petgraph::unionfind::UnionFind;
    use petgraph::visit::{IntoEdgeReferences, NodeIndexable};

    match &graph.inner {
        GraphInner::Directed(inner) => {
            let mut uf = UnionFind::new(inner.node_bound());
            for edge in inner.edge_references() {
                let a = inner.to_index(edge.source());
                let b = inner.to_index(edge.target());
                uf.union(a, b);
            }
            let mut components: std::collections::HashMap<usize, Vec<String>> =
                std::collections::HashMap::new();
            for node in inner.node_indices() {
                let root = uf.find(inner.to_index(node));
                components
                    .entry(root)
                    .or_default()
                    .push(graph.id_of(node).to_string());
            }
            components.into_values().collect()
        }
        GraphInner::Undirected(inner) => {
            let mut uf = UnionFind::new(inner.node_bound());
            for edge in inner.edge_references() {
                let a = inner.to_index(edge.source());
                let b = inner.to_index(edge.target());
                uf.union(a, b);
            }
            let mut components: std::collections::HashMap<usize, Vec<String>> =
                std::collections::HashMap::new();
            for node in inner.node_indices() {
                let root = uf.find(inner.to_index(node));
                components
                    .entry(root)
                    .or_default()
                    .push(graph.id_of(node).to_string());
            }
            components.into_values().collect()
        }
    }
}

/// Connected-component labels over an undirected **integer edge list**,
/// without building a string-keyed property [`Graph`].
///
/// This is the array fast path for callers that already hold an edge list
/// addressed by contiguous integer node id (`0..n_nodes`) — e.g. the
/// `(m, 2)` pairs produced by `kaos_nlp_core.similarity.knn_graph` /
/// `near_duplicates` — and want component labels without paying to
/// construct and string-key a `Graph` edge by edge.
///
/// Returns a length-`n_nodes` vector where every node carries the
/// **smallest node id in its component** — a canonical, deterministic
/// label independent of edge order and of petgraph's union-find internal
/// representative (isolated nodes label to themselves).
///
/// Errors with a message naming the offending node if any edge references
/// a node `>= n_nodes`.
pub fn connected_components_from_edges(
    n_nodes: usize,
    edges: &[(u32, u32)],
) -> Result<Vec<u32>, String> {
    use petgraph::unionfind::UnionFind;

    let mut uf = UnionFind::new(n_nodes);
    for &(a, b) in edges {
        let (ai, bi) = (a as usize, b as usize);
        if ai >= n_nodes {
            return Err(format!("edge references node {a} but n_nodes is {n_nodes}"));
        }
        if bi >= n_nodes {
            return Err(format!("edge references node {b} but n_nodes is {n_nodes}"));
        }
        uf.union(ai, bi);
    }

    // Relabel each component by the smallest member id, so the labels are
    // stable across union order and petgraph versions (its `find` returns
    // an arbitrary representative, not necessarily the minimum).
    let mut root_min: Vec<u32> = (0..n_nodes as u32).collect();
    for node in 0..n_nodes {
        let root = uf.find(node);
        if (node as u32) < root_min[root] {
            root_min[root] = node as u32;
        }
    }
    Ok((0..n_nodes).map(|node| root_min[uf.find(node)]).collect())
}

/// Check if the graph is strongly connected (every node reachable from every other).
pub fn is_strongly_connected(graph: &Graph) -> bool {
    if graph.n_nodes() == 0 {
        return true;
    }
    match &graph.inner {
        GraphInner::Directed(g) => {
            let sccs = tarjan_scc(g);
            sccs.len() == 1
        }
        // For undirected, strongly connected == connected.
        GraphInner::Undirected(_) => graph.is_connected(),
    }
}

/// Check if the graph is weakly connected.
pub fn is_weakly_connected(graph: &Graph) -> bool {
    num_connected_components(graph) <= 1
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn test_scc_dag() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();

        let sccs = strongly_connected_components(&g);
        assert_eq!(sccs.len(), 3); // each node is its own SCC in a DAG
    }

    #[test]
    fn test_scc_cycle() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "a", HashMap::new()).unwrap();

        let sccs = strongly_connected_components(&g);
        assert_eq!(sccs.len(), 1);
        assert_eq!(sccs[0].len(), 3);
    }

    #[test]
    fn test_num_connected_components() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        // c is isolated
        assert_eq!(num_connected_components(&g), 2);
    }

    #[test]
    fn test_weakly_connected_components() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();

        let wccs = weakly_connected_components(&g);
        assert_eq!(wccs.len(), 2);
    }

    #[test]
    fn test_is_strongly_connected() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "a", HashMap::new()).unwrap();
        assert!(is_strongly_connected(&g));

        let mut g2 = Graph::new(true);
        g2.add_node("a", HashMap::new()).unwrap();
        g2.add_node("b", HashMap::new()).unwrap();
        g2.add_edge("a", "b", HashMap::new()).unwrap();
        assert!(!is_strongly_connected(&g2));
    }

    #[test]
    fn test_is_weakly_connected() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        assert!(is_weakly_connected(&g));
    }

    #[test]
    fn test_components_from_edges_two_groups() {
        // {0,1,2} connected; {3,4} connected; {5} isolated.
        let edges = [(0u32, 1u32), (1, 2), (3, 4)];
        let labels = connected_components_from_edges(6, &edges).unwrap();
        assert_eq!(labels, vec![0, 0, 0, 3, 3, 5]);
    }

    #[test]
    fn test_components_from_edges_all_isolated() {
        let labels = connected_components_from_edges(4, &[]).unwrap();
        assert_eq!(labels, vec![0, 1, 2, 3]);
    }

    #[test]
    fn test_components_from_edges_canonical_min_label() {
        // Union order makes a higher id the union-find root; the label must
        // still be the component minimum.
        let edges = [(2u32, 0u32), (2, 1)];
        let labels = connected_components_from_edges(3, &edges).unwrap();
        assert_eq!(labels, vec![0, 0, 0]);
    }

    #[test]
    fn test_components_from_edges_invalid_node_errors() {
        let err = connected_components_from_edges(3, &[(0, 5)]).unwrap_err();
        assert!(err.contains("node 5"), "got: {err}");
    }
}
