use petgraph::visit::{Bfs, Dfs, IntoNeighbors, NodeIndexable};

use crate::core::graph::{Graph, GraphInner};

/// DFS with enter/exit events. Returns (node_id, event) pairs.
/// event: true = enter (preorder), false = exit (postorder).
///
/// Uses an explicit stack to track both enter and exit events.
pub fn dfs_events(graph: &Graph, source: &str) -> Result<Vec<(String, bool)>, String> {
    let start = graph.resolve_index(source)?;

    // Stack entries: (node_index, is_enter)
    // We push enter first, process children, then exit.
    enum Action {
        Enter(petgraph::stable_graph::NodeIndex),
        Exit(petgraph::stable_graph::NodeIndex),
    }

    match &graph.inner {
        GraphInner::Directed(g) => {
            let mut visited = std::collections::HashSet::new();
            let mut stack = vec![Action::Enter(start)];
            let mut result = Vec::new();

            while let Some(action) = stack.pop() {
                match action {
                    Action::Enter(node) => {
                        if !visited.insert(node) {
                            continue;
                        }
                        result.push((graph.id_of(node).to_string(), true));
                        stack.push(Action::Exit(node));
                        // Push children in reverse order so first child is processed first.
                        let neighbors: Vec<_> = g
                            .neighbors_directed(node, petgraph::Direction::Outgoing)
                            .collect();
                        for &child in neighbors.iter().rev() {
                            if !visited.contains(&child) {
                                stack.push(Action::Enter(child));
                            }
                        }
                    }
                    Action::Exit(node) => {
                        result.push((graph.id_of(node).to_string(), false));
                    }
                }
            }
            Ok(result)
        }
        GraphInner::Undirected(g) => {
            let mut visited = std::collections::HashSet::new();
            let mut stack = vec![Action::Enter(start)];
            let mut result = Vec::new();

            while let Some(action) = stack.pop() {
                match action {
                    Action::Enter(node) => {
                        if !visited.insert(node) {
                            continue;
                        }
                        result.push((graph.id_of(node).to_string(), true));
                        stack.push(Action::Exit(node));
                        let neighbors: Vec<_> = IntoNeighbors::neighbors(g, node).collect();
                        for &child in neighbors.iter().rev() {
                            if !visited.contains(&child) {
                                stack.push(Action::Enter(child));
                            }
                        }
                    }
                    Action::Exit(node) => {
                        result.push((graph.id_of(node).to_string(), false));
                    }
                }
            }
            Ok(result)
        }
    }
}

/// BFS traversal from a source node. Returns node IDs in BFS order.
pub fn bfs(graph: &Graph, source: &str) -> Result<Vec<String>, String> {
    let idx = graph.resolve_index(source)?;
    match &graph.inner {
        GraphInner::Directed(g) => {
            let mut bfs = Bfs::new(g, idx);
            let mut result = Vec::new();
            while let Some(node) = bfs.next(g) {
                result.push(graph.id_of(node).to_string());
            }
            Ok(result)
        }
        GraphInner::Undirected(g) => {
            let mut bfs = Bfs::new(g, idx);
            let mut result = Vec::new();
            while let Some(node) = bfs.next(g) {
                result.push(graph.id_of(node).to_string());
            }
            Ok(result)
        }
    }
}

/// DFS traversal from a source node. Returns node IDs in DFS (preorder).
pub fn dfs(graph: &Graph, source: &str) -> Result<Vec<String>, String> {
    let idx = graph.resolve_index(source)?;
    match &graph.inner {
        GraphInner::Directed(g) => {
            let mut dfs = Dfs::new(g, idx);
            let mut result = Vec::new();
            while let Some(node) = dfs.next(g) {
                result.push(graph.id_of(node).to_string());
            }
            Ok(result)
        }
        GraphInner::Undirected(g) => {
            let mut dfs = Dfs::new(g, idx);
            let mut result = Vec::new();
            while let Some(node) = dfs.next(g) {
                result.push(graph.id_of(node).to_string());
            }
            Ok(result)
        }
    }
}

/// BFS returning (node_id, depth) pairs.
pub fn bfs_with_depth(graph: &Graph, source: &str) -> Result<Vec<(String, usize)>, String> {
    let start = graph.resolve_index(source)?;

    match &graph.inner {
        GraphInner::Directed(inner) => bfs_with_depth_generic(graph, inner, start),
        GraphInner::Undirected(inner) => bfs_with_depth_generic(graph, inner, start),
    }
}

fn bfs_with_depth_generic<G>(
    graph: &Graph,
    inner: G,
    start: petgraph::stable_graph::NodeIndex,
) -> Result<Vec<(String, usize)>, String>
where
    G: IntoNeighbors<NodeId = petgraph::stable_graph::NodeIndex> + NodeIndexable + Copy,
{
    let mut visited = vec![false; inner.node_bound()];
    let mut queue = std::collections::VecDeque::new();
    let mut result = Vec::new();

    visited[start.index()] = true;
    queue.push_back((start, 0usize));

    while let Some((node, depth)) = queue.pop_front() {
        result.push((graph.id_of(node).to_string(), depth));
        for neighbor in inner.neighbors(node) {
            if !visited[neighbor.index()] {
                visited[neighbor.index()] = true;
                queue.push_back((neighbor, depth + 1));
            }
        }
    }
    Ok(result)
}

/// BFS returning only nodes at a specific depth from source.
pub fn bfs_at_depth(
    graph: &Graph,
    source: &str,
    target_depth: usize,
) -> Result<Vec<String>, String> {
    let pairs = bfs_with_depth(graph, source)?;
    Ok(pairs
        .into_iter()
        .filter(|(_, d)| *d == target_depth)
        .map(|(id, _)| id)
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn make_chain() -> Graph {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();
        g
    }

    #[test]
    fn test_bfs_chain() {
        let g = make_chain();
        let order = bfs(&g, "a").unwrap();
        assert_eq!(order, vec!["a", "b", "c", "d"]);
    }

    #[test]
    fn test_dfs_chain() {
        let g = make_chain();
        let order = dfs(&g, "a").unwrap();
        assert_eq!(order, vec!["a", "b", "c", "d"]);
    }

    #[test]
    fn test_bfs_branching() {
        let mut g = Graph::new(true);
        g.add_node("root", HashMap::new()).unwrap();
        g.add_node("l", HashMap::new()).unwrap();
        g.add_node("r", HashMap::new()).unwrap();
        g.add_node("ll", HashMap::new()).unwrap();
        g.add_edge("root", "l", HashMap::new()).unwrap();
        g.add_edge("root", "r", HashMap::new()).unwrap();
        g.add_edge("l", "ll", HashMap::new()).unwrap();

        let order = bfs(&g, "root").unwrap();
        assert_eq!(order[0], "root");
        // l and r at depth 1 (order may vary)
        assert!(order[1..3].contains(&"l".to_string()));
        assert!(order[1..3].contains(&"r".to_string()));
        assert_eq!(order[3], "ll");
    }

    #[test]
    fn test_bfs_with_depth() {
        let g = make_chain();
        let pairs = bfs_with_depth(&g, "a").unwrap();
        assert_eq!(pairs[0], ("a".to_string(), 0));
        assert_eq!(pairs[1], ("b".to_string(), 1));
        assert_eq!(pairs[2], ("c".to_string(), 2));
        assert_eq!(pairs[3], ("d".to_string(), 3));
    }

    #[test]
    fn test_bfs_at_depth() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();

        let at_1 = bfs_at_depth(&g, "a", 1).unwrap();
        assert_eq!(at_1.len(), 2);
        assert!(at_1.contains(&"b".to_string()));
        assert!(at_1.contains(&"c".to_string()));
    }

    #[test]
    fn test_missing_source() {
        let g = Graph::new(true);
        assert!(bfs(&g, "missing").is_err());
        assert!(dfs(&g, "missing").is_err());
    }

    #[test]
    fn test_dfs_events_chain() {
        let g = make_chain();
        let events = dfs_events(&g, "a").unwrap();
        // Should have 8 events (4 enters + 4 exits).
        assert_eq!(events.len(), 8);
        // First event: enter a
        assert_eq!(events[0], ("a".to_string(), true));
        // Last event: exit a
        assert_eq!(events[events.len() - 1], ("a".to_string(), false));

        // Every node should appear exactly twice: once enter, once exit.
        for node in &["a", "b", "c", "d"] {
            let enters: Vec<_> = events
                .iter()
                .filter(|(id, ev)| id == *node && *ev)
                .collect();
            let exits: Vec<_> = events
                .iter()
                .filter(|(id, ev)| id == *node && !*ev)
                .collect();
            assert_eq!(enters.len(), 1, "Node {node} should enter once");
            assert_eq!(exits.len(), 1, "Node {node} should exit once");
        }

        // Each node's enter should come before its exit.
        for node in &["a", "b", "c", "d"] {
            let enter_pos = events
                .iter()
                .position(|(id, ev)| id == *node && *ev)
                .unwrap();
            let exit_pos = events
                .iter()
                .position(|(id, ev)| id == *node && !*ev)
                .unwrap();
            assert!(enter_pos < exit_pos, "Enter before exit for {node}");
        }
    }

    #[test]
    fn test_dfs_events_branching() {
        let mut g = Graph::new(true);
        g.add_node("root", HashMap::new()).unwrap();
        g.add_node("l", HashMap::new()).unwrap();
        g.add_node("r", HashMap::new()).unwrap();
        g.add_edge("root", "l", HashMap::new()).unwrap();
        g.add_edge("root", "r", HashMap::new()).unwrap();

        let events = dfs_events(&g, "root").unwrap();
        assert_eq!(events.len(), 6); // 3 enters + 3 exits
        assert_eq!(events[0], ("root".to_string(), true));
        assert_eq!(events[events.len() - 1], ("root".to_string(), false));
    }

    #[test]
    fn test_dfs_events_missing_source() {
        let g = Graph::new(true);
        assert!(dfs_events(&g, "missing").is_err());
    }
}
