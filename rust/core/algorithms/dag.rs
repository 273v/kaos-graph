use std::collections::HashSet;

use petgraph::algo::toposort;
use petgraph::visit::NodeIndexable;
use petgraph::Direction;

use crate::core::graph::{Graph, GraphInner};

/// Topological sort via petgraph::algo::toposort.
/// Returns node IDs in topological order, or error if graph has cycles.
///
/// Only meaningful for directed graphs. Undirected graphs always return an error.
pub fn topological_sort(graph: &Graph) -> Result<Vec<String>, String> {
    match &graph.inner {
        GraphInner::Directed(g) => toposort(g, None)
            .map(|order| {
                order
                    .into_iter()
                    .map(|idx| graph.id_of(idx).to_string())
                    .collect()
            })
            .map_err(|cycle| {
                format!(
                    "Graph has a cycle involving node '{}'",
                    graph.id_of(cycle.node_id())
                )
            }),
        GraphInner::Undirected(_) => {
            Err("Topological sort is only defined for directed graphs".to_string())
        }
    }
}

/// All ancestors of a node (nodes that can reach it). Does NOT include the node itself.
pub fn ancestors(graph: &Graph, id: &str) -> Result<Vec<String>, String> {
    let idx = graph.resolve_index(id)?;

    match &graph.inner {
        GraphInner::Directed(inner) => {
            let mut visited = HashSet::new();
            let mut stack = vec![idx];
            while let Some(node) = stack.pop() {
                for pred in inner.neighbors_directed(node, Direction::Incoming) {
                    if visited.insert(pred) {
                        stack.push(pred);
                    }
                }
            }
            Ok(visited
                .into_iter()
                .map(|n| graph.id_of(n).to_string())
                .collect())
        }
        // For undirected, "ancestors" means all reachable nodes (since edges are bidirectional).
        GraphInner::Undirected(inner) => {
            let mut visited = HashSet::new();
            let mut stack = vec![idx];
            while let Some(node) = stack.pop() {
                for nbr in inner.neighbors(node) {
                    if visited.insert(nbr) {
                        stack.push(nbr);
                    }
                }
            }
            Ok(visited
                .into_iter()
                .map(|n| graph.id_of(n).to_string())
                .collect())
        }
    }
}

/// All descendants of a node (nodes reachable from it). Does NOT include the node itself.
pub fn descendants(graph: &Graph, id: &str) -> Result<Vec<String>, String> {
    let idx = graph.resolve_index(id)?;

    match &graph.inner {
        GraphInner::Directed(inner) => {
            let mut visited = HashSet::new();
            let mut stack = vec![idx];
            while let Some(node) = stack.pop() {
                for succ in inner.neighbors_directed(node, Direction::Outgoing) {
                    if visited.insert(succ) {
                        stack.push(succ);
                    }
                }
            }
            Ok(visited
                .into_iter()
                .map(|n| graph.id_of(n).to_string())
                .collect())
        }
        // For undirected, descendants == all reachable.
        GraphInner::Undirected(inner) => {
            let mut visited = HashSet::new();
            let mut stack = vec![idx];
            while let Some(node) = stack.pop() {
                for nbr in inner.neighbors(node) {
                    if visited.insert(nbr) {
                        stack.push(nbr);
                    }
                }
            }
            Ok(visited
                .into_iter()
                .map(|n| graph.id_of(n).to_string())
                .collect())
        }
    }
}

/// Transitive reduction of a DAG.
/// Returns a new Graph with redundant edges removed.
///
/// Only meaningful for directed acyclic graphs.
pub fn transitive_reduction(graph: &Graph) -> Result<Graph, String> {
    if !graph.is_dag() {
        return Err("Transitive reduction requires a DAG".to_string());
    }

    let inner = graph.inner_directed();
    let mut new_graph = Graph::with_name(graph.is_directed(), graph.name().to_string());

    for node in inner.node_weights() {
        new_graph
            .add_node(&node.id, node.properties.clone())
            .map_err(|e| e.to_string())?;
    }

    use petgraph::visit::{EdgeRef, IntoEdgeReferences};

    for edge in inner.edge_references() {
        let src = edge.source();
        let tgt = edge.target();

        let mut reachable_via_other = false;
        for neighbor in inner.neighbors_directed(src, Direction::Outgoing) {
            if neighbor == tgt {
                continue;
            }
            if petgraph::algo::has_path_connecting(inner, neighbor, tgt, None) {
                reachable_via_other = true;
                break;
            }
        }

        if !reachable_via_other {
            let src_id = &inner[src].id;
            let tgt_id = &inner[tgt].id;
            new_graph
                .add_edge(src_id, tgt_id, edge.weight().properties.clone())
                .map_err(|e| e.to_string())?;
        }
    }

    Ok(new_graph)
}

/// Longest path in a DAG (critical path). Returns (length, path_node_ids).
/// Uses topological sort + dynamic programming. Returns error if graph has cycles.
pub fn longest_path(graph: &Graph) -> Result<(usize, Vec<String>), String> {
    let order = topological_sort(graph)?;
    if order.is_empty() {
        return Ok((0, vec![]));
    }

    let inner = graph.inner_directed();
    let n = inner.node_bound();
    let mut dist = vec![0usize; n];
    let mut prev = vec![None::<petgraph::stable_graph::NodeIndex>; n];

    for id in &order {
        let idx = graph.resolve_index(id)?;
        for succ in inner.neighbors_directed(idx, Direction::Outgoing) {
            if dist[succ.index()] < dist[idx.index()] + 1 {
                dist[succ.index()] = dist[idx.index()] + 1;
                prev[succ.index()] = Some(idx);
            }
        }
    }

    let (best_idx, &best_dist) = dist
        .iter()
        .enumerate()
        .filter(|(i, _)| {
            inner
                .node_weight(petgraph::stable_graph::NodeIndex::new(*i))
                .is_some()
        })
        .max_by_key(|(_, d)| *d)
        .unwrap_or((0, &0));

    let mut path = vec![];
    let mut cur = petgraph::stable_graph::NodeIndex::new(best_idx);
    path.push(graph.id_of(cur).to_string());
    while let Some(p) = prev[cur.index()] {
        path.push(graph.id_of(p).to_string());
        cur = p;
    }
    path.reverse();

    Ok((best_dist, path))
}

/// Transitive closure: for every pair (u, v) where v is reachable from u,
/// add edge (u, v) if it doesn't already exist.
///
/// Works on any directed graph (not just DAGs). For undirected, operates
/// on all neighbors.
pub fn transitive_closure(graph: &Graph) -> Graph {
    let mut new_graph = Graph::with_name(graph.is_directed(), graph.name().to_string());

    // Add all nodes
    for &id in &graph.node_ids() {
        if let Some(n) = graph.node(id) {
            new_graph.add_node(id, n.properties.clone()).ok();
        }
    }

    // Add all original edges
    for (src, tgt, data) in graph.edges_vec() {
        new_graph.add_edge(src, tgt, data.properties.clone()).ok();
    }

    // For each node u, find all descendants and add transitive edges.
    match &graph.inner {
        GraphInner::Directed(inner) => {
            for u in inner.node_indices() {
                let u_id = graph.id_of(u).to_string();
                let mut visited = HashSet::new();
                let mut stack = vec![u];
                while let Some(node) = stack.pop() {
                    for succ in inner.neighbors_directed(node, Direction::Outgoing) {
                        if visited.insert(succ) {
                            stack.push(succ);
                        }
                    }
                }
                for v in visited {
                    if v == u {
                        continue;
                    }
                    let v_id = graph.id_of(v).to_string();
                    if !new_graph.has_edge(&u_id, &v_id) {
                        new_graph
                            .add_edge(&u_id, &v_id, std::collections::HashMap::new())
                            .ok();
                    }
                }
            }
        }
        GraphInner::Undirected(inner) => {
            for u in inner.node_indices() {
                let u_id = graph.id_of(u).to_string();
                let mut visited = HashSet::new();
                let mut stack = vec![u];
                while let Some(node) = stack.pop() {
                    for nbr in inner.neighbors(node) {
                        if visited.insert(nbr) {
                            stack.push(nbr);
                        }
                    }
                }
                for v in visited {
                    if v == u {
                        continue;
                    }
                    let v_id = graph.id_of(v).to_string();
                    if !new_graph.has_edge(&u_id, &v_id) {
                        new_graph
                            .add_edge(&u_id, &v_id, std::collections::HashMap::new())
                            .ok();
                    }
                }
            }
        }
    }

    new_graph
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn test_topological_sort() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();

        let order = topological_sort(&g).unwrap();
        let pos_a = order.iter().position(|x| x == "a").unwrap();
        let pos_b = order.iter().position(|x| x == "b").unwrap();
        let pos_c = order.iter().position(|x| x == "c").unwrap();
        assert!(pos_a < pos_b);
        assert!(pos_b < pos_c);
    }

    #[test]
    fn test_topological_sort_cycle() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "a", HashMap::new()).unwrap();

        assert!(topological_sort(&g).is_err());
    }

    #[test]
    fn test_ancestors() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();

        let mut anc = ancestors(&g, "c").unwrap();
        anc.sort();
        assert_eq!(anc, vec!["a", "b"]);

        let anc_a = ancestors(&g, "a").unwrap();
        assert!(anc_a.is_empty());
    }

    #[test]
    fn test_descendants() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();

        let mut desc = descendants(&g, "a").unwrap();
        desc.sort();
        assert_eq!(desc, vec!["b", "c"]);
    }

    #[test]
    fn test_longest_path() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();
        g.add_edge("a", "d", HashMap::new()).unwrap(); // shortcut

        let (len, path) = longest_path(&g).unwrap();
        assert_eq!(len, 3);
        assert_eq!(path, vec!["a", "b", "c", "d"]);
    }

    #[test]
    fn test_transitive_closure_chain() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();

        let tc = transitive_closure(&g);
        assert_eq!(tc.n_nodes(), 3);
        assert!(tc.has_edge("a", "b"));
        assert!(tc.has_edge("b", "c"));
        assert!(tc.has_edge("a", "c"));
        assert_eq!(tc.n_edges(), 3);
    }

    #[test]
    fn test_transitive_closure_already_complete() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();

        let tc = transitive_closure(&g);
        assert_eq!(tc.n_edges(), 3);
    }

    #[test]
    fn test_transitive_closure_disconnected() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();

        let tc = transitive_closure(&g);
        assert_eq!(tc.n_edges(), 0);
    }

    #[test]
    fn test_transitive_closure_longer_chain() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();

        let tc = transitive_closure(&g);
        assert_eq!(tc.n_nodes(), 4);
        assert_eq!(tc.n_edges(), 6);
        assert!(tc.has_edge("a", "c"));
        assert!(tc.has_edge("a", "d"));
        assert!(tc.has_edge("b", "d"));
    }
}
