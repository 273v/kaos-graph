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
}
