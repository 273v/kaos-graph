use std::collections::VecDeque;

use petgraph::stable_graph::NodeIndex;
use petgraph::visit::{EdgeRef, IntoEdgeReferences, NodeIndexable};
use petgraph::Direction;

use crate::core::graph::{Graph, GraphInner};

/// Sparse PageRank — standard O((V+E) x iterations) algorithm.
///
/// Returns (node_id, rank) pairs sorted by rank descending.
pub fn pagerank(graph: &Graph, damping_factor: f64, iterations: usize) -> Vec<(String, f64)> {
    match &graph.inner {
        GraphInner::Directed(inner) => pagerank_generic(graph, inner, damping_factor, iterations),
        GraphInner::Undirected(inner) => pagerank_generic(graph, inner, damping_factor, iterations),
    }
}

fn pagerank_generic<G>(
    graph: &Graph,
    inner: G,
    damping_factor: f64,
    iterations: usize,
) -> Vec<(String, f64)>
where
    G: IntoEdgeReferences<NodeId = NodeIndex, EdgeWeight = crate::core::edge::EdgeData>
        + NodeIndexable
        + Copy,
    for<'a> <G as IntoEdgeReferences>::EdgeRef: EdgeRef<Weight = crate::core::edge::EdgeData>,
    G: petgraph::visit::IntoNodeIdentifiers,
{
    let n = graph.n_nodes();
    if n == 0 {
        return vec![];
    }

    let bound = inner.node_bound();
    let init = 1.0 / n as f64;

    // Build out-degree array and adjacency list (target -> sources)
    let mut out_degree = vec![0usize; bound];
    let mut in_edges: Vec<Vec<usize>> = vec![vec![]; bound];

    for edge in inner.edge_references() {
        let src = inner.to_index(edge.source());
        let tgt = inner.to_index(edge.target());
        out_degree[src] += 1;
        in_edges[tgt].push(src);
    }

    // Identify valid node indices
    let valid: Vec<usize> = inner
        .node_identifiers()
        .map(|idx| inner.to_index(idx))
        .collect();

    let mut ranks = vec![0.0f64; bound];
    for &i in &valid {
        ranks[i] = init;
    }

    let teleport = (1.0 - damping_factor) / n as f64;

    for _ in 0..iterations {
        let dangling_sum: f64 = valid
            .iter()
            .filter(|&&i| out_degree[i] == 0)
            .map(|&i| ranks[i])
            .sum();
        let dangling_contrib = damping_factor * dangling_sum / n as f64;

        let mut new_ranks = vec![0.0f64; bound];
        for &v in &valid {
            let mut sum = 0.0;
            for &src in &in_edges[v] {
                sum += ranks[src] / out_degree[src] as f64;
            }
            new_ranks[v] = teleport + dangling_contrib + damping_factor * sum;
        }

        // Normalize
        let total: f64 = valid.iter().map(|&i| new_ranks[i]).sum();
        if total > 0.0 {
            for &i in &valid {
                new_ranks[i] /= total;
            }
        }

        ranks = new_ranks;
    }

    let mut result: Vec<(String, f64)> = graph
        .node_ids()
        .into_iter()
        .map(|id| {
            let idx = graph.resolve_index(id).unwrap();
            let i = idx.index();
            (id.to_string(), ranks[i])
        })
        .collect();

    result.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    result
}

/// Degree centrality: degree(v) / (n - 1).
pub fn degree_centrality(graph: &Graph) -> Vec<(String, f64)> {
    let n = graph.n_nodes();
    if n <= 1 {
        return graph
            .node_ids()
            .into_iter()
            .map(|id| (id.to_string(), 0.0))
            .collect();
    }

    let denom = (n - 1) as f64;
    let mut result: Vec<(String, f64)> = graph
        .node_ids()
        .into_iter()
        .map(|id| {
            let deg = graph.degree(id).unwrap_or(0) as f64;
            (id.to_string(), deg / denom)
        })
        .collect();

    result.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    result
}

/// In-degree centrality (for directed graphs): in_degree(v) / (n - 1).
/// For undirected graphs, equivalent to degree centrality.
pub fn in_degree_centrality(graph: &Graph) -> Vec<(String, f64)> {
    let n = graph.n_nodes();
    if n <= 1 {
        return graph
            .node_ids()
            .into_iter()
            .map(|id| (id.to_string(), 0.0))
            .collect();
    }

    let denom = (n - 1) as f64;

    match &graph.inner {
        GraphInner::Directed(inner) => {
            let mut result: Vec<(String, f64)> = inner
                .node_indices()
                .map(|idx| {
                    let in_deg = inner.neighbors_directed(idx, Direction::Incoming).count() as f64;
                    (graph.id_of(idx).to_string(), in_deg / denom)
                })
                .collect();
            result.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
            result
        }
        GraphInner::Undirected(_) => degree_centrality(graph),
    }
}

/// Out-degree centrality (for directed graphs): out_degree(v) / (n - 1).
/// For undirected graphs, equivalent to degree centrality.
pub fn out_degree_centrality(graph: &Graph) -> Vec<(String, f64)> {
    let n = graph.n_nodes();
    if n <= 1 {
        return graph
            .node_ids()
            .into_iter()
            .map(|id| (id.to_string(), 0.0))
            .collect();
    }

    let denom = (n - 1) as f64;

    match &graph.inner {
        GraphInner::Directed(inner) => {
            let mut result: Vec<(String, f64)> = inner
                .node_indices()
                .map(|idx| {
                    let out_deg = inner.neighbors_directed(idx, Direction::Outgoing).count() as f64;
                    (graph.id_of(idx).to_string(), out_deg / denom)
                })
                .collect();
            result.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
            result
        }
        GraphInner::Undirected(_) => degree_centrality(graph),
    }
}

/// Betweenness centrality — Brandes algorithm, O(VE) for unweighted graphs.
///
/// For directed graphs: BFS follows outgoing edges.
/// For undirected graphs: BFS follows all adjacent edges.
///
/// If `normalized` is true, divides by (V-1)(V-2) for directed, (V-1)(V-2)/2 for undirected.
pub fn betweenness_centrality(graph: &Graph, normalized: bool) -> Vec<(String, f64)> {
    match &graph.inner {
        GraphInner::Directed(inner) => betweenness_directed(graph, inner, normalized),
        GraphInner::Undirected(inner) => betweenness_undirected(graph, inner, normalized),
    }
}

fn betweenness_directed(
    graph: &Graph,
    inner: &petgraph::stable_graph::StableDiGraph<
        crate::core::node::NodeData,
        crate::core::edge::EdgeData,
    >,
    normalized: bool,
) -> Vec<(String, f64)> {
    let n = inner.node_count();
    if n <= 2 {
        return inner
            .node_indices()
            .map(|idx| (graph.id_of(idx).to_string(), 0.0))
            .collect();
    }

    let bound = inner.node_bound();
    let valid: Vec<usize> = inner
        .node_indices()
        .map(|idx| inner.to_index(idx))
        .collect();

    let mut cb = vec![0.0f64; bound];

    for &s in &valid {
        let mut stack: Vec<usize> = Vec::new();
        let mut pred: Vec<Vec<usize>> = vec![vec![]; bound];
        let mut sigma = vec![0.0f64; bound];
        let mut dist: Vec<i64> = vec![-1; bound];
        let mut delta = vec![0.0f64; bound];

        sigma[s] = 1.0;
        dist[s] = 0;
        let mut queue = VecDeque::new();
        queue.push_back(s);

        while let Some(v) = queue.pop_front() {
            stack.push(v);
            let v_idx = inner.from_index(v);
            for w_idx in inner.neighbors_directed(v_idx, Direction::Outgoing) {
                let w = inner.to_index(w_idx);
                if dist[w] < 0 {
                    dist[w] = dist[v] + 1;
                    queue.push_back(w);
                }
                if dist[w] == dist[v] + 1 {
                    sigma[w] += sigma[v];
                    pred[w].push(v);
                }
            }
        }

        while let Some(w) = stack.pop() {
            for &v in &pred[w] {
                delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w]);
            }
            if w != s {
                cb[w] += delta[w];
            }
        }

        for &v in &valid {
            delta[v] = 0.0;
        }
    }

    if normalized {
        let factor = ((n - 1) * (n - 2)) as f64;
        if factor > 0.0 {
            for &v in &valid {
                cb[v] /= factor;
            }
        }
    }

    let mut result: Vec<(String, f64)> = inner
        .node_indices()
        .map(|idx| {
            let i = inner.to_index(idx);
            (graph.id_of(idx).to_string(), cb[i])
        })
        .collect();

    result.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    result
}

fn betweenness_undirected(
    graph: &Graph,
    inner: &petgraph::stable_graph::StableUnGraph<
        crate::core::node::NodeData,
        crate::core::edge::EdgeData,
    >,
    normalized: bool,
) -> Vec<(String, f64)> {
    let n = inner.node_count();
    if n <= 2 {
        return inner
            .node_indices()
            .map(|idx| (graph.id_of(idx).to_string(), 0.0))
            .collect();
    }

    let bound = inner.node_bound();
    let valid: Vec<usize> = inner
        .node_indices()
        .map(|idx| inner.to_index(idx))
        .collect();

    let mut cb = vec![0.0f64; bound];

    for &s in &valid {
        let mut stack: Vec<usize> = Vec::new();
        let mut pred: Vec<Vec<usize>> = vec![vec![]; bound];
        let mut sigma = vec![0.0f64; bound];
        let mut dist: Vec<i64> = vec![-1; bound];
        let mut delta = vec![0.0f64; bound];

        sigma[s] = 1.0;
        dist[s] = 0;
        let mut queue = VecDeque::new();
        queue.push_back(s);

        while let Some(v) = queue.pop_front() {
            stack.push(v);
            let v_idx = inner.from_index(v);
            for w_idx in petgraph::visit::IntoNeighbors::neighbors(inner, v_idx) {
                let w = inner.to_index(w_idx);
                if dist[w] < 0 {
                    dist[w] = dist[v] + 1;
                    queue.push_back(w);
                }
                if dist[w] == dist[v] + 1 {
                    sigma[w] += sigma[v];
                    pred[w].push(v);
                }
            }
        }

        while let Some(w) = stack.pop() {
            for &v in &pred[w] {
                delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w]);
            }
            if w != s {
                cb[w] += delta[w];
            }
        }

        for &v in &valid {
            delta[v] = 0.0;
        }
    }

    // For undirected, each pair (s,t) is counted twice; divide by 2.
    // Then normalize by (V-1)(V-2)/2 if requested.
    for &v in &valid {
        cb[v] /= 2.0;
    }

    if normalized {
        let factor = ((n - 1) * (n - 2)) as f64 / 2.0;
        if factor > 0.0 {
            for &v in &valid {
                cb[v] /= factor;
            }
        }
    }

    let mut result: Vec<(String, f64)> = inner
        .node_indices()
        .map(|idx| {
            let i = inner.to_index(idx);
            (graph.id_of(idx).to_string(), cb[i])
        })
        .collect();

    result.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    result
}

/// Closeness centrality — Wasserman-Faust normalization.
///
/// For directed: BFS follows outgoing edges.
/// For undirected: BFS follows all adjacent edges.
pub fn closeness_centrality(graph: &Graph) -> Vec<(String, f64)> {
    match &graph.inner {
        GraphInner::Directed(inner) => closeness_directed(graph, inner),
        GraphInner::Undirected(inner) => closeness_undirected(graph, inner),
    }
}

fn closeness_directed(
    graph: &Graph,
    inner: &petgraph::stable_graph::StableDiGraph<
        crate::core::node::NodeData,
        crate::core::edge::EdgeData,
    >,
) -> Vec<(String, f64)> {
    let n = inner.node_count();
    if n == 0 {
        return vec![];
    }

    let bound = inner.node_bound();
    let mut result: Vec<(String, f64)> = Vec::with_capacity(n);

    for source in inner.node_indices() {
        let s = inner.to_index(source);
        let mut dist: Vec<i64> = vec![-1; bound];
        dist[s] = 0;
        let mut queue = VecDeque::new();
        queue.push_back(s);

        let mut total_dist: f64 = 0.0;
        let mut reachable: usize = 0;

        while let Some(v) = queue.pop_front() {
            let v_idx = inner.from_index(v);
            for w_idx in inner.neighbors_directed(v_idx, Direction::Outgoing) {
                let w = inner.to_index(w_idx);
                if dist[w] < 0 {
                    dist[w] = dist[v] + 1;
                    total_dist += dist[w] as f64;
                    reachable += 1;
                    queue.push_back(w);
                }
            }
        }

        let closeness = if reachable > 0 && total_dist > 0.0 {
            reachable as f64 / total_dist
        } else {
            0.0
        };

        result.push((graph.id_of(source).to_string(), closeness));
    }

    result.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    result
}

fn closeness_undirected(
    graph: &Graph,
    inner: &petgraph::stable_graph::StableUnGraph<
        crate::core::node::NodeData,
        crate::core::edge::EdgeData,
    >,
) -> Vec<(String, f64)> {
    let n = inner.node_count();
    if n == 0 {
        return vec![];
    }

    let bound = inner.node_bound();
    let mut result: Vec<(String, f64)> = Vec::with_capacity(n);

    for source in inner.node_indices() {
        let s = inner.to_index(source);
        let mut dist: Vec<i64> = vec![-1; bound];
        dist[s] = 0;
        let mut queue = VecDeque::new();
        queue.push_back(s);

        let mut total_dist: f64 = 0.0;
        let mut reachable: usize = 0;

        while let Some(v) = queue.pop_front() {
            let v_idx = inner.from_index(v);
            for w_idx in petgraph::visit::IntoNeighbors::neighbors(inner, v_idx) {
                let w = inner.to_index(w_idx);
                if dist[w] < 0 {
                    dist[w] = dist[v] + 1;
                    total_dist += dist[w] as f64;
                    reachable += 1;
                    queue.push_back(w);
                }
            }
        }

        let closeness = if reachable > 0 && total_dist > 0.0 {
            reachable as f64 / total_dist
        } else {
            0.0
        };

        result.push((graph.id_of(source).to_string(), closeness));
    }

    result.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    result
}

/// Eigenvector centrality — power iteration on the adjacency matrix.
///
/// For directed: incoming neighbors contribute.
/// For undirected: all neighbors contribute.
pub fn eigenvector_centrality(
    graph: &Graph,
    iterations: usize,
    tolerance: f64,
) -> Vec<(String, f64)> {
    match &graph.inner {
        GraphInner::Directed(inner) => eigenvector_directed(graph, inner, iterations, tolerance),
        GraphInner::Undirected(inner) => {
            eigenvector_undirected(graph, inner, iterations, tolerance)
        }
    }
}

fn eigenvector_directed(
    graph: &Graph,
    inner: &petgraph::stable_graph::StableDiGraph<
        crate::core::node::NodeData,
        crate::core::edge::EdgeData,
    >,
    iterations: usize,
    tolerance: f64,
) -> Vec<(String, f64)> {
    let n = inner.node_count();
    if n == 0 {
        return vec![];
    }

    let bound = inner.node_bound();
    let valid: Vec<usize> = inner
        .node_indices()
        .map(|idx| inner.to_index(idx))
        .collect();

    let init = 1.0 / (n as f64).sqrt();
    let mut scores = vec![0.0f64; bound];
    for &i in &valid {
        scores[i] = init;
    }

    for _ in 0..iterations {
        let mut new_scores = vec![0.0f64; bound];

        for &v in &valid {
            let v_idx = inner.from_index(v);
            let mut sum = 0.0;
            for u_idx in inner.neighbors_directed(v_idx, Direction::Incoming) {
                let u = inner.to_index(u_idx);
                sum += scores[u];
            }
            new_scores[v] = sum;
        }

        let norm: f64 = valid
            .iter()
            .map(|&i| new_scores[i] * new_scores[i])
            .sum::<f64>()
            .sqrt();
        if norm > 0.0 {
            for &i in &valid {
                new_scores[i] /= norm;
            }
        }

        let diff: f64 = valid
            .iter()
            .map(|&i| (new_scores[i] - scores[i]).powi(2))
            .sum::<f64>()
            .sqrt();

        scores = new_scores;

        if diff < tolerance {
            break;
        }
    }

    let mut result: Vec<(String, f64)> = inner
        .node_indices()
        .map(|idx| {
            let i = inner.to_index(idx);
            (graph.id_of(idx).to_string(), scores[i])
        })
        .collect();

    result.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    result
}

fn eigenvector_undirected(
    graph: &Graph,
    inner: &petgraph::stable_graph::StableUnGraph<
        crate::core::node::NodeData,
        crate::core::edge::EdgeData,
    >,
    iterations: usize,
    tolerance: f64,
) -> Vec<(String, f64)> {
    let n = inner.node_count();
    if n == 0 {
        return vec![];
    }

    let bound = inner.node_bound();
    let valid: Vec<usize> = inner
        .node_indices()
        .map(|idx| inner.to_index(idx))
        .collect();

    let init = 1.0 / (n as f64).sqrt();
    let mut scores = vec![0.0f64; bound];
    for &i in &valid {
        scores[i] = init;
    }

    for _ in 0..iterations {
        let mut new_scores = vec![0.0f64; bound];

        for &v in &valid {
            let v_idx = inner.from_index(v);
            let mut sum = 0.0;
            for u_idx in petgraph::visit::IntoNeighbors::neighbors(inner, v_idx) {
                let u = inner.to_index(u_idx);
                sum += scores[u];
            }
            new_scores[v] = sum;
        }

        let norm: f64 = valid
            .iter()
            .map(|&i| new_scores[i] * new_scores[i])
            .sum::<f64>()
            .sqrt();
        if norm > 0.0 {
            for &i in &valid {
                new_scores[i] /= norm;
            }
        }

        let diff: f64 = valid
            .iter()
            .map(|&i| (new_scores[i] - scores[i]).powi(2))
            .sum::<f64>()
            .sqrt();

        scores = new_scores;

        if diff < tolerance {
            break;
        }
    }

    let mut result: Vec<(String, f64)> = inner
        .node_indices()
        .map(|idx| {
            let i = inner.to_index(idx);
            (graph.id_of(idx).to_string(), scores[i])
        })
        .collect();

    result.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn test_pagerank_simple() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "a", HashMap::new()).unwrap();

        let ranks = pagerank(&g, 0.85, 100);
        assert_eq!(ranks.len(), 3);
        let total: f64 = ranks.iter().map(|(_, r)| r).sum();
        assert!((total - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_pagerank_star() {
        let mut g = Graph::new(true);
        g.add_node("hub", HashMap::new()).unwrap();
        for i in 0..5 {
            let id = format!("leaf{}", i);
            g.add_node(&id, HashMap::new()).unwrap();
            g.add_edge(&id, "hub", HashMap::new()).unwrap();
        }

        let ranks = pagerank(&g, 0.85, 100);
        assert_eq!(ranks[0].0, "hub");
    }

    #[test]
    fn test_degree_centrality() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();

        let dc = degree_centrality(&g);
        let a_rank = dc.iter().find(|(id, _)| id == "a").unwrap().1;
        assert_eq!(a_rank, 1.0);
    }

    #[test]
    fn test_in_degree_centrality() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();

        let idc = in_degree_centrality(&g);
        let c_rank = idc.iter().find(|(id, _)| id == "c").unwrap().1;
        assert_eq!(c_rank, 1.0);
    }

    #[test]
    fn test_betweenness_centrality_line() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();

        let bc = betweenness_centrality(&g, false);
        let scores: HashMap<&str, f64> = bc.iter().map(|(id, s)| (id.as_str(), *s)).collect();

        assert!(scores["b"] > 0.0);
        assert!(scores["c"] > 0.0);
        assert_eq!(scores["a"], 0.0);
        assert_eq!(scores["d"], 0.0);
        assert!((scores["b"] - 2.0).abs() < 1e-9);
        assert!((scores["c"] - 2.0).abs() < 1e-9);
    }

    #[test]
    fn test_betweenness_centrality_normalized() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();

        let bc = betweenness_centrality(&g, true);
        let scores: HashMap<&str, f64> = bc.iter().map(|(id, s)| (id.as_str(), *s)).collect();

        assert!((scores["b"] - 2.0 / 6.0).abs() < 1e-9);
    }

    #[test]
    fn test_betweenness_centrality_empty() {
        let g = Graph::new(true);
        let bc = betweenness_centrality(&g, false);
        assert!(bc.is_empty());
    }

    #[test]
    fn test_closeness_centrality_line() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();

        let cc = closeness_centrality(&g);
        let scores: HashMap<&str, f64> = cc.iter().map(|(id, s)| (id.as_str(), *s)).collect();

        assert!((scores["a"] - 2.0 / 3.0).abs() < 1e-9);
        assert!((scores["b"] - 1.0).abs() < 1e-9);
        assert_eq!(scores["c"], 0.0);
    }

    #[test]
    fn test_closeness_centrality_empty() {
        let g = Graph::new(true);
        let cc = closeness_centrality(&g);
        assert!(cc.is_empty());
    }

    #[test]
    fn test_eigenvector_centrality_cycle() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "a", HashMap::new()).unwrap();

        let ec = eigenvector_centrality(&g, 1000, 1e-10);
        assert_eq!(ec.len(), 3);
        let scores: Vec<f64> = ec.iter().map(|(_, s)| *s).collect();
        let expected = 1.0 / (3.0f64).sqrt();
        for s in &scores {
            assert!((s - expected).abs() < 1e-6);
        }
    }

    #[test]
    fn test_eigenvector_centrality_chain() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "a", HashMap::new()).unwrap();
        g.add_edge("d", "a", HashMap::new()).unwrap();

        let ec = eigenvector_centrality(&g, 1000, 1e-10);
        assert_eq!(ec.len(), 4);
        for (_, s) in &ec {
            assert!(*s >= 0.0);
        }
        let norm: f64 = ec.iter().map(|(_, s)| s * s).sum::<f64>().sqrt();
        assert!((norm - 1.0).abs() < 1e-6);
        let scores: HashMap<&str, f64> = ec.iter().map(|(id, s)| (id.as_str(), *s)).collect();
        assert!(scores["d"] < 1e-10);
    }

    #[test]
    fn test_eigenvector_centrality_empty() {
        let g = Graph::new(true);
        let ec = eigenvector_centrality(&g, 100, 1e-6);
        assert!(ec.is_empty());
    }
}
