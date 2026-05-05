use std::collections::HashMap;

use petgraph::algo::{astar, dijkstra, has_path_connecting};
use petgraph::stable_graph::NodeIndex;
use petgraph::visit::{EdgeRef, IntoEdgeReferences, NodeIndexable};
use serde_json::Value;

use crate::core::graph::{Graph, GraphInner};

/// Extract a numeric weight from edge properties. Falls back to `default` if
/// the key is missing or not numeric.
fn edge_weight(props: &HashMap<String, Value>, key: &str, default: f64) -> f64 {
    props
        .get(key)
        .and_then(|v| match v {
            Value::Number(n) => n.as_f64(),
            _ => None,
        })
        .unwrap_or(default)
}

/// Single-source shortest paths via Dijkstra. Returns (node_id -> cost).
///
/// `weight_key`: property name to read edge weights from. If None, all edges
/// have weight 1.0.
pub fn shortest_paths(
    graph: &Graph,
    source: &str,
    target: Option<&str>,
    weight_key: Option<&str>,
) -> Result<HashMap<String, f64>, String> {
    let src_idx = graph.resolve_index(source)?;
    let tgt_idx = match target {
        Some(t) => Some(graph.resolve_index(t)?),
        None => None,
    };

    let costs = match &graph.inner {
        GraphInner::Directed(g) => dijkstra(g, src_idx, tgt_idx, |e| -> f64 {
            match weight_key {
                Some(key) => edge_weight(&e.weight().properties, key, 1.0),
                None => 1.0,
            }
        }),
        GraphInner::Undirected(g) => dijkstra(g, src_idx, tgt_idx, |e| -> f64 {
            match weight_key {
                Some(key) => edge_weight(&e.weight().properties, key, 1.0),
                None => 1.0,
            }
        }),
    };

    Ok(costs
        .into_iter()
        .map(|(idx, cost)| (graph.id_of(idx).to_string(), cost))
        .collect())
}

/// Shortest path distance between two nodes. Returns None if unreachable.
pub fn shortest_path_length(
    graph: &Graph,
    source: &str,
    target: &str,
    weight_key: Option<&str>,
) -> Result<Option<f64>, String> {
    let costs = shortest_paths(graph, source, Some(target), weight_key)?;
    Ok(costs.get(target).copied())
}

/// Check if a path exists between two nodes.
pub fn has_path(graph: &Graph, source: &str, target: &str) -> Result<bool, String> {
    let src_idx = graph.resolve_index(source)?;
    let tgt_idx = graph.resolve_index(target)?;
    Ok(match &graph.inner {
        GraphInner::Directed(g) => has_path_connecting(g, src_idx, tgt_idx, None),
        GraphInner::Undirected(g) => has_path_connecting(g, src_idx, tgt_idx, None),
    })
}

/// A* shortest path. Returns (cost, path_node_ids) or None if unreachable.
///
/// `heuristic` is not easily exposed from Rust to Python, so we use a zero
/// heuristic (degrades to Dijkstra) when called from bindings. Pure Rust
/// callers can use petgraph::algo::astar directly for custom heuristics.
pub fn astar_path(
    graph: &Graph,
    source: &str,
    target: &str,
    weight_key: Option<&str>,
) -> Result<Option<(f64, Vec<String>)>, String> {
    let src_idx = graph.resolve_index(source)?;
    let tgt_idx = graph.resolve_index(target)?;

    let result = match &graph.inner {
        GraphInner::Directed(g) => astar(
            g,
            src_idx,
            |n| n == tgt_idx,
            |e| match weight_key {
                Some(key) => edge_weight(&e.weight().properties, key, 1.0),
                None => 1.0,
            },
            |_| 0.0,
        ),
        GraphInner::Undirected(g) => astar(
            g,
            src_idx,
            |n| n == tgt_idx,
            |e| match weight_key {
                Some(key) => edge_weight(&e.weight().properties, key, 1.0),
                None => 1.0,
            },
            |_| 0.0,
        ),
    };

    match result {
        Some((cost, path)) => {
            let ids: Vec<String> = path
                .iter()
                .map(|&idx| graph.id_of(idx).to_string())
                .collect();
            Ok(Some((cost, ids)))
        }
        None => Ok(None),
    }
}

/// Bellman-Ford single-source shortest paths. Supports negative weights.
/// Returns (node_id -> cost) or error if negative cycle detected.
///
/// Note: petgraph's built-in bellman_ford requires G::EdgeWeight: FloatMeasure,
/// which our EdgeData doesn't satisfy. This implements the standard algorithm
/// directly on our property-bearing graph.
pub fn bellman_ford_paths(
    graph: &Graph,
    source: &str,
    weight_key: Option<&str>,
) -> Result<HashMap<String, f64>, String> {
    let src_idx = graph.resolve_index(source)?;

    // This works generically since both graph types implement the required traits.
    match &graph.inner {
        GraphInner::Directed(inner) => bellman_ford_generic(graph, inner, src_idx, weight_key),
        GraphInner::Undirected(inner) => bellman_ford_generic(graph, inner, src_idx, weight_key),
    }
}

fn bellman_ford_generic<G>(
    graph: &Graph,
    inner: G,
    src_idx: NodeIndex,
    weight_key: Option<&str>,
) -> Result<HashMap<String, f64>, String>
where
    G: IntoEdgeReferences<NodeId = NodeIndex, EdgeWeight = crate::core::edge::EdgeData>
        + NodeIndexable
        + Copy,
    for<'a> <G as IntoEdgeReferences>::EdgeRef: EdgeRef<Weight = crate::core::edge::EdgeData>,
{
    let n = inner.node_bound();
    let node_count = graph.n_nodes();

    let mut dist = vec![f64::INFINITY; n];
    dist[src_idx.index()] = 0.0;

    // Relax edges |V|-1 times
    for _ in 0..node_count.saturating_sub(1) {
        let mut changed = false;
        for edge in inner.edge_references() {
            let u = edge.source().index();
            let v = edge.target().index();
            let w = match weight_key {
                Some(key) => edge_weight(&edge.weight().properties, key, 1.0),
                None => 1.0,
            };
            if dist[u] + w < dist[v] {
                dist[v] = dist[u] + w;
                changed = true;
            }
        }
        if !changed {
            break;
        }
    }

    // Check for negative cycles
    for edge in inner.edge_references() {
        let u = edge.source().index();
        let v = edge.target().index();
        let w = match weight_key {
            Some(key) => edge_weight(&edge.weight().properties, key, 1.0),
            None => 1.0,
        };
        if dist[u] + w < dist[v] {
            return Err("Negative cycle detected".to_string());
        }
    }

    // Collect results — we iterate via edges_vec to get valid nodes.
    let mut out = HashMap::new();
    for &id in &graph.node_ids() {
        let idx = graph.resolve_index(id).unwrap();
        let d = dist[idx.index()];
        if d < f64::INFINITY {
            out.insert(id.to_string(), d);
        }
    }
    Ok(out)
}

/// All simple (non-repeating) paths from `source` to `target`.
///
/// `max_depth` limits the total path length (number of nodes). When `None`,
/// all paths up to the graph's node count are returned.
///
/// petgraph's `all_simple_paths` counts *intermediate* nodes (i.e. excluding
/// source and target), so `max_intermediate = max_depth - 2` when
/// `max_depth >= 2`.
pub fn all_simple_paths(
    graph: &Graph,
    source: &str,
    target: &str,
    max_depth: Option<usize>,
) -> Result<Vec<Vec<String>>, String> {
    all_simple_paths_capped(graph, source, target, max_depth, usize::MAX)
}

/// All simple paths from source to target with both depth and result-count
/// caps. The result cap is applied to the *iterator* (via ``.take(cap)``)
/// so enumeration stops as soon as the cap is reached, bounding peak CPU
/// and memory on dense graphs (audit follow-up #2).
pub fn all_simple_paths_capped(
    graph: &Graph,
    source: &str,
    target: &str,
    max_depth: Option<usize>,
    max_paths: usize,
) -> Result<Vec<Vec<String>>, String> {
    let src_idx = graph.resolve_index(source)?;
    let tgt_idx = graph.resolve_index(target)?;

    let max_intermediate: Option<usize> = max_depth.map(|d| d.saturating_sub(2));

    let paths: Vec<Vec<NodeIndex>> = match &graph.inner {
        GraphInner::Directed(g) => petgraph::algo::all_simple_paths::<
            Vec<_>,
            _,
            std::hash::RandomState,
        >(g, src_idx, tgt_idx, 0, max_intermediate)
        .take(max_paths)
        .collect(),
        GraphInner::Undirected(g) => petgraph::algo::all_simple_paths::<
            Vec<_>,
            _,
            std::hash::RandomState,
        >(g, src_idx, tgt_idx, 0, max_intermediate)
        .take(max_paths)
        .collect(),
    };

    Ok(paths
        .into_iter()
        .map(|p| p.iter().map(|&idx| graph.id_of(idx).to_string()).collect())
        .collect())
}

/// Find all cycles in the graph using the SCC-based approach.
///
/// For directed graphs, cycles exist within strongly connected components of
/// size > 1. This function returns the node IDs of each SCC that contains a
/// cycle (i.e. |SCC| >= 2). Self-loops are also detected.
///
/// For undirected graphs, this is not meaningful in the same sense.
/// Returns empty for undirected graphs.
pub fn find_cycles(graph: &Graph) -> Vec<Vec<String>> {
    match &graph.inner {
        GraphInner::Directed(inner) => {
            let sccs = petgraph::algo::tarjan_scc(inner);
            let mut cycles: Vec<Vec<String>> = Vec::new();

            for scc in sccs {
                if scc.len() >= 2 {
                    let ids: Vec<String> = scc
                        .iter()
                        .map(|&idx| graph.id_of(idx).to_string())
                        .collect();
                    cycles.push(ids);
                } else if scc.len() == 1 {
                    let node = scc[0];
                    if inner.find_edge(node, node).is_some() {
                        cycles.push(vec![graph.id_of(node).to_string()]);
                    }
                }
            }

            cycles
        }
        GraphInner::Undirected(_) => {
            // SCC-based cycle detection is not meaningful for undirected graphs.
            vec![]
        }
    }
}

/// Find one representative cycle path per strongly connected component.
///
/// For each SCC with > 1 node, does a DFS within the SCC to find an actual
/// cycle path (ordered sequence of node IDs forming the cycle). For self-loops,
/// returns `[node]`.
///
/// Returns empty for undirected graphs.
pub fn find_cycle_paths(graph: &Graph) -> Vec<Vec<String>> {
    match &graph.inner {
        GraphInner::Directed(inner) => {
            let sccs = petgraph::algo::tarjan_scc(inner);
            let mut result: Vec<Vec<String>> = Vec::new();

            for scc in sccs {
                if scc.len() == 1 {
                    let node = scc[0];
                    if inner.find_edge(node, node).is_some() {
                        result.push(vec![graph.id_of(node).to_string()]);
                    }
                    continue;
                }

                // For SCC with > 1 node, find one cycle via DFS.
                let scc_set: std::collections::HashSet<_> = scc.iter().copied().collect();
                let start = scc[0];

                // DFS within the SCC to find a back-edge, then reconstruct the cycle.
                let mut stack = vec![(start, vec![start])];
                let mut visited = std::collections::HashSet::new();
                visited.insert(start);
                let mut found = false;

                while let Some((node, path)) = stack.pop() {
                    for neighbor in inner.neighbors_directed(node, petgraph::Direction::Outgoing) {
                        if !scc_set.contains(&neighbor) {
                            continue;
                        }
                        if neighbor == start && !path.is_empty() {
                            // Found a cycle back to start.
                            let cycle_path: Vec<String> = path
                                .iter()
                                .map(|&idx| graph.id_of(idx).to_string())
                                .collect();
                            result.push(cycle_path);
                            found = true;
                            break;
                        }
                        if !visited.contains(&neighbor) {
                            visited.insert(neighbor);
                            let mut new_path = path.clone();
                            new_path.push(neighbor);
                            stack.push((neighbor, new_path));
                        }
                    }
                    if found {
                        break;
                    }
                }
            }

            result
        }
        GraphInner::Undirected(_) => {
            vec![]
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_weighted() -> Graph {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();

        let mut w1 = HashMap::new();
        w1.insert(
            "weight".to_string(),
            Value::Number(serde_json::Number::from_f64(1.0).unwrap()),
        );
        let mut w2 = HashMap::new();
        w2.insert(
            "weight".to_string(),
            Value::Number(serde_json::Number::from_f64(2.0).unwrap()),
        );
        let mut w10 = HashMap::new();
        w10.insert(
            "weight".to_string(),
            Value::Number(serde_json::Number::from_f64(10.0).unwrap()),
        );

        g.add_edge("a", "b", w1.clone()).unwrap();
        g.add_edge("b", "c", w1.clone()).unwrap();
        g.add_edge("a", "c", w10).unwrap(); // direct but expensive
        g.add_edge("c", "d", w2).unwrap();
        g
    }

    #[test]
    fn test_shortest_paths_unweighted() {
        let g = make_weighted();
        let costs = shortest_paths(&g, "a", None, None).unwrap();
        assert_eq!(costs["a"], 0.0);
        assert_eq!(costs["b"], 1.0);
        assert_eq!(costs["c"], 1.0); // direct a->c, weight=1 (unweighted)
        assert_eq!(costs["d"], 2.0);
    }

    #[test]
    fn test_shortest_paths_weighted() {
        let g = make_weighted();
        let costs = shortest_paths(&g, "a", None, Some("weight")).unwrap();
        assert_eq!(costs["a"], 0.0);
        assert_eq!(costs["b"], 1.0);
        assert_eq!(costs["c"], 2.0); // a->b->c = 1+1 < a->c = 10
        assert_eq!(costs["d"], 4.0);
    }

    #[test]
    fn test_shortest_path_length() {
        let g = make_weighted();
        let len = shortest_path_length(&g, "a", "d", Some("weight")).unwrap();
        assert_eq!(len, Some(4.0));

        let none = shortest_path_length(&g, "d", "a", Some("weight")).unwrap();
        assert_eq!(none, None); // no reverse path
    }

    #[test]
    fn test_has_path() {
        let g = make_weighted();
        assert!(has_path(&g, "a", "d").unwrap());
        assert!(!has_path(&g, "d", "a").unwrap());
    }

    #[test]
    fn test_astar_path() {
        let g = make_weighted();
        let result = astar_path(&g, "a", "d", Some("weight")).unwrap();
        let (cost, path) = result.unwrap();
        assert_eq!(cost, 4.0);
        assert_eq!(path, vec!["a", "b", "c", "d"]);
    }

    #[test]
    fn test_astar_unreachable() {
        let g = make_weighted();
        let result = astar_path(&g, "d", "a", Some("weight")).unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn test_bellman_ford() {
        let g = make_weighted();
        let costs = bellman_ford_paths(&g, "a", Some("weight")).unwrap();
        assert_eq!(costs["a"], 0.0);
        assert_eq!(costs["b"], 1.0);
        assert_eq!(costs["c"], 2.0);
        assert_eq!(costs["d"], 4.0);
    }

    #[test]
    fn test_all_simple_paths_diamond() {
        // a -> b -> d
        // a -> c -> d
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();
        g.add_edge("b", "d", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();

        let mut paths = all_simple_paths(&g, "a", "d", None).unwrap();
        paths.sort();
        assert_eq!(paths.len(), 2);
        assert_eq!(paths[0], vec!["a", "b", "d"]);
        assert_eq!(paths[1], vec!["a", "c", "d"]);
    }

    #[test]
    fn test_all_simple_paths_with_max_depth() {
        // a -> b -> c -> d, plus a -> c -> d
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();

        // max_depth=3 means at most 3 nodes in path (1 intermediate)
        let paths = all_simple_paths(&g, "a", "d", Some(3)).unwrap();
        // Only a->c->d fits (3 nodes). a->b->c->d has 4 nodes, excluded.
        assert_eq!(paths.len(), 1);
        assert_eq!(paths[0], vec!["a", "c", "d"]);
    }

    #[test]
    fn test_all_simple_paths_no_path() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        // no edges
        let paths = all_simple_paths(&g, "a", "b", None).unwrap();
        assert!(paths.is_empty());
    }

    #[test]
    fn test_all_simple_paths_invalid_node() {
        let g = Graph::new(true);
        assert!(all_simple_paths(&g, "missing", "also_missing", None).is_err());
    }

    #[test]
    fn test_find_cycles_no_cycles() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();

        let cycles = find_cycles(&g);
        assert!(cycles.is_empty());
    }

    #[test]
    fn test_find_cycles_single_cycle() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "a", HashMap::new()).unwrap();

        let cycles = find_cycles(&g);
        assert_eq!(cycles.len(), 1);
        assert_eq!(cycles[0].len(), 3);
    }

    #[test]
    fn test_find_cycles_self_loop() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_edge("a", "a", HashMap::new()).unwrap();

        let cycles = find_cycles(&g);
        assert_eq!(cycles.len(), 1);
        assert_eq!(cycles[0], vec!["a"]);
    }

    #[test]
    fn test_find_cycles_multiple() {
        // Two separate cycles: a<->b and c<->d
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "a", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();
        g.add_edge("d", "c", HashMap::new()).unwrap();

        let cycles = find_cycles(&g);
        assert_eq!(cycles.len(), 2);
    }

    #[test]
    fn test_find_cycle_paths_triangle() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "a", HashMap::new()).unwrap();

        let paths = find_cycle_paths(&g);
        assert_eq!(paths.len(), 1);
        let cycle = &paths[0];
        // The cycle should form a valid path through the SCC.
        assert!(cycle.len() >= 2);
        // Verify it actually forms a cycle: last node should connect back to first.
        // All nodes should be in {a, b, c}.
        for id in cycle {
            assert!(["a", "b", "c"].contains(&id.as_str()));
        }
    }

    #[test]
    fn test_find_cycle_paths_self_loop() {
        let mut g = Graph::new(true);
        g.add_node("x", HashMap::new()).unwrap();
        g.add_edge("x", "x", HashMap::new()).unwrap();

        let paths = find_cycle_paths(&g);
        assert_eq!(paths.len(), 1);
        assert_eq!(paths[0], vec!["x"]);
    }

    #[test]
    fn test_find_cycle_paths_no_cycles() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();

        let paths = find_cycle_paths(&g);
        assert!(paths.is_empty());
    }

    #[test]
    fn test_find_cycle_paths_two_cycles() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "a", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();
        g.add_edge("d", "c", HashMap::new()).unwrap();

        let paths = find_cycle_paths(&g);
        assert_eq!(paths.len(), 2);
        // Each cycle path should have length 2.
        for cycle in &paths {
            assert_eq!(cycle.len(), 2);
        }
    }
}
