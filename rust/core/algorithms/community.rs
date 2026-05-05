use std::collections::HashMap;

use petgraph::visit::{EdgeRef, IntoEdgeReferences, NodeIndexable};

use crate::core::graph::{Graph, GraphInner};

/// Extract numeric edge weight from EdgeData properties.
/// Looks for a "weight" key; defaults to 1.0 if absent.
fn edge_weight(edge: &crate::core::edge::EdgeData) -> f64 {
    edge.properties
        .get("weight")
        .and_then(|v| v.as_f64())
        .unwrap_or(1.0)
}

/// Build a symmetric adjacency representation from a Graph.
///
/// Returns `(adj, m)` where:
/// - `adj[i]` maps neighbor index -> total edge weight to that neighbor (symmetric)
/// - `m` is the total edge weight (each undirected edge counted once)
///
/// `idx_map` maps petgraph internal node indices to contiguous 0..n indices.
fn build_adjacency(
    graph: &Graph,
    idx_map: &HashMap<usize, usize>,
    n: usize,
) -> (Vec<HashMap<usize, f64>>, f64) {
    let mut adj: Vec<HashMap<usize, f64>> = vec![HashMap::new(); n];
    let mut total_m = 0.0;

    match &graph.inner {
        GraphInner::Directed(inner) => {
            for edge in inner.edge_references() {
                let si = idx_map[&inner.to_index(edge.source())];
                let ti = idx_map[&inner.to_index(edge.target())];
                let w = edge_weight(edge.weight());

                // Directed: symmetrize. Each directed edge contributes w to both directions.
                *adj[si].entry(ti).or_insert(0.0) += w;
                *adj[ti].entry(si).or_insert(0.0) += w;
                total_m += w;
            }
        }
        GraphInner::Undirected(inner) => {
            // Each edge appears once in petgraph's edge_references.
            for edge in inner.edge_references() {
                let si = idx_map[&inner.to_index(edge.source())];
                let ti = idx_map[&inner.to_index(edge.target())];
                let w = edge_weight(edge.weight());

                *adj[si].entry(ti).or_insert(0.0) += w;
                *adj[ti].entry(si).or_insert(0.0) += w;
                total_m += w;
            }
        }
    }

    (adj, total_m)
}

/// Get node indices from the graph for building contiguous maps.
fn get_node_indices(graph: &Graph) -> Vec<petgraph::stable_graph::NodeIndex> {
    match &graph.inner {
        GraphInner::Directed(inner) => inner.node_indices().collect(),
        GraphInner::Undirected(inner) => inner.node_indices().collect(),
    }
}

fn build_idx_map(
    graph: &Graph,
    node_indices: &[petgraph::stable_graph::NodeIndex],
) -> HashMap<usize, usize> {
    let mut idx_map: HashMap<usize, usize> = HashMap::new();
    match &graph.inner {
        GraphInner::Directed(inner) => {
            for (i, &ni) in node_indices.iter().enumerate() {
                idx_map.insert(inner.to_index(ni), i);
            }
        }
        GraphInner::Undirected(inner) => {
            for (i, &ni) in node_indices.iter().enumerate() {
                idx_map.insert(inner.to_index(ni), i);
            }
        }
    }
    idx_map
}

/// Louvain community detection algorithm.
///
/// Two-phase iterative algorithm for modularity optimization.
///
/// Treats the graph as undirected for modularity computation.
///
/// Returns communities as lists of original node IDs.
pub fn louvain_communities(graph: &Graph) -> Vec<Vec<String>> {
    let n = graph.n_nodes();
    if n == 0 {
        return vec![];
    }

    let node_indices = get_node_indices(graph);
    let idx_map = build_idx_map(graph, &node_indices);

    let (mut adj, m) = build_adjacency(graph, &idx_map, n);

    if m == 0.0 {
        return node_indices
            .iter()
            .map(|&ni| vec![graph.id_of(ni).to_string()])
            .collect();
    }

    let mut k: Vec<f64> = adj.iter().map(|nbrs| nbrs.values().sum()).collect();
    let mut community: Vec<usize> = (0..n).collect();
    let mut node_members: Vec<Vec<usize>> = (0..n).map(|i| vec![i]).collect();

    loop {
        let improved = louvain_phase1(&adj, &k, m, &mut community);
        if !improved {
            break;
        }

        let (new_adj, new_k, new_community, new_members) =
            louvain_phase2(&adj, &k, &community, &node_members);

        if new_adj.len() == adj.len() {
            break;
        }

        adj = new_adj;
        k = new_k;
        community = new_community;
        node_members = new_members;
    }

    let mut groups: HashMap<usize, Vec<usize>> = HashMap::new();
    for (i, &c) in community.iter().enumerate() {
        groups.entry(c).or_default().extend(&node_members[i]);
    }

    let mut result: Vec<Vec<String>> = groups
        .into_values()
        .map(|members| {
            let mut ids: Vec<String> = members
                .into_iter()
                .map(|orig| graph.id_of(node_indices[orig]).to_string())
                .collect();
            ids.sort();
            ids
        })
        .collect();

    result.sort_by(|a, b| a[0].cmp(&b[0]));
    result
}

/// Phase 1: iteratively move nodes to the best neighboring community.
fn louvain_phase1(adj: &[HashMap<usize, f64>], k: &[f64], m: f64, community: &mut [usize]) -> bool {
    let n = adj.len();
    let mut any_improved = false;

    let mut sigma_tot: HashMap<usize, f64> = HashMap::new();
    for (i, &c) in community.iter().enumerate() {
        *sigma_tot.entry(c).or_insert(0.0) += k[i];
    }

    let mut changed = true;
    while changed {
        changed = false;
        for i in 0..n {
            let old_c = community[i];
            let ki = k[i];

            let mut ki_in: HashMap<usize, f64> = HashMap::new();
            for (&j, &w) in &adj[i] {
                *ki_in.entry(community[j]).or_insert(0.0) += w;
            }

            *sigma_tot.get_mut(&old_c).unwrap() -= ki;

            let ki_in_old = ki_in.get(&old_c).copied().unwrap_or(0.0);
            let remove_cost = ki_in_old / m - sigma_tot[&old_c] * ki / (2.0 * m * m);

            let mut best_c = old_c;
            let mut best_gain = 0.0_f64;

            for (&c, &ki_in_c) in &ki_in {
                let st = sigma_tot.get(&c).copied().unwrap_or(0.0);
                let add_gain = ki_in_c / m - st * ki / (2.0 * m * m);
                let delta = add_gain - remove_cost;
                if delta > best_gain {
                    best_gain = delta;
                    best_c = c;
                }
            }

            *sigma_tot.entry(old_c).or_insert(0.0) += ki;

            if best_c != old_c {
                community[i] = best_c;
                *sigma_tot.get_mut(&old_c).unwrap() -= ki;
                *sigma_tot.entry(best_c).or_insert(0.0) += ki;
                changed = true;
                any_improved = true;
            }
        }
    }

    any_improved
}

/// Phase 2: contract communities into super-nodes.
#[allow(clippy::type_complexity)]
fn louvain_phase2(
    adj: &[HashMap<usize, f64>],
    k: &[f64],
    community: &[usize],
    node_members: &[Vec<usize>],
) -> (
    Vec<HashMap<usize, f64>>,
    Vec<f64>,
    Vec<usize>,
    Vec<Vec<usize>>,
) {
    let mut comm_set: Vec<usize> = community.to_vec();
    comm_set.sort();
    comm_set.dedup();
    let comm_to_new: HashMap<usize, usize> = comm_set
        .iter()
        .enumerate()
        .map(|(new_idx, &old_c)| (old_c, new_idx))
        .collect();
    let new_n = comm_set.len();

    let mut new_members: Vec<Vec<usize>> = vec![vec![]; new_n];
    for (i, &c) in community.iter().enumerate() {
        let ni = comm_to_new[&c];
        new_members[ni].extend(&node_members[i]);
    }

    let mut new_adj: Vec<HashMap<usize, f64>> = vec![HashMap::new(); new_n];
    for (i, nbrs) in adj.iter().enumerate() {
        let ci = comm_to_new[&community[i]];
        for (&j, &w) in nbrs {
            let cj = comm_to_new[&community[j]];
            if ci != cj {
                *new_adj[ci].entry(cj).or_insert(0.0) += w;
            }
        }
    }

    let mut new_k: Vec<f64> = vec![0.0; new_n];
    for (i, &c) in community.iter().enumerate() {
        let ni = comm_to_new[&c];
        new_k[ni] += k[i];
    }
    let new_community: Vec<usize> = (0..new_n).collect();

    (new_adj, new_k, new_community, new_members)
}

/// Label propagation community detection.
///
/// Each node starts with its own unique label. In each iteration, each node adopts
/// the most common label among its neighbors. Ties broken by smallest label.
///
/// Returns communities as lists of node IDs grouped by final label.
pub fn label_propagation(graph: &Graph) -> Vec<Vec<String>> {
    let n = graph.n_nodes();
    if n == 0 {
        return vec![];
    }

    let node_indices = get_node_indices(graph);
    let idx_map = build_idx_map(graph, &node_indices);

    // Build symmetric neighbor lists.
    let mut neighbors: Vec<Vec<usize>> = vec![vec![]; n];
    match &graph.inner {
        GraphInner::Directed(inner) => {
            for edge in inner.edge_references() {
                let si = idx_map[&inner.to_index(edge.source())];
                let ti = idx_map[&inner.to_index(edge.target())];
                neighbors[si].push(ti);
                neighbors[ti].push(si); // symmetrize for directed
            }
        }
        GraphInner::Undirected(inner) => {
            for edge in inner.edge_references() {
                let si = idx_map[&inner.to_index(edge.source())];
                let ti = idx_map[&inner.to_index(edge.target())];
                neighbors[si].push(ti);
                neighbors[ti].push(si);
            }
        }
    }
    for nb in &mut neighbors {
        nb.sort();
        nb.dedup();
    }

    let mut labels: Vec<usize> = (0..n).collect();

    // A2-followup-#1: hard iteration cap. Synchronous label propagation
    // can oscillate forever on some graph shapes (e.g. a 2-node graph with
    // both nodes flipping labels each round). 100 iterations matches the
    // upstream-petgraph default and is well above the typical convergence
    // count (~10-20) for real graphs.
    const MAX_ITERATIONS: usize = 100;

    for _ in 0..MAX_ITERATIONS {
        let mut new_labels = labels.clone();
        let mut changed = false;
        for i in 0..n {
            if neighbors[i].is_empty() {
                continue;
            }
            let mut label_counts: HashMap<usize, usize> = HashMap::new();
            for &j in &neighbors[i] {
                *label_counts.entry(labels[j]).or_insert(0) += 1;
            }
            let max_count = *label_counts.values().max().unwrap_or(&0);
            let current_count = label_counts.get(&labels[i]).copied().unwrap_or(0);
            if current_count == max_count {
                continue;
            }
            let mut best_label = labels[i];
            for (&label, &count) in &label_counts {
                if count == max_count && (best_label == labels[i] || label < best_label) {
                    best_label = label;
                }
            }
            if best_label != labels[i] {
                new_labels[i] = best_label;
                changed = true;
            }
        }
        labels = new_labels;
        if !changed {
            break;
        }
    }

    let mut groups: HashMap<usize, Vec<String>> = HashMap::new();
    for (i, &label) in labels.iter().enumerate() {
        groups
            .entry(label)
            .or_default()
            .push(graph.id_of(node_indices[i]).to_string());
    }

    let mut result: Vec<Vec<String>> = groups.into_values().collect();
    for c in &mut result {
        c.sort();
    }
    result.sort_by(|a, b| a[0].cmp(&b[0]));
    result
}

/// k-clique communities.
///
/// Algorithm:
/// 1. Find all maximal cliques (Bron-Kerbosch).
/// 2. Filter to cliques of size >= k.
/// 3. Build a clique overlap graph: two cliques share an edge if they
///    overlap in k-1 or more nodes.
/// 4. Connected components of the overlap graph = communities.
/// 5. Each community is the union of its constituent cliques' nodes.
///
/// Returns communities as sorted lists of node IDs.
pub fn k_clique_communities(graph: &Graph, k: usize) -> Vec<Vec<String>> {
    if k < 2 {
        // k=1 or k=0 is degenerate; every node is its own community.
        // Return each connected component.
        return super::components::weakly_connected_components(graph);
    }

    // Step 1: Get all maximal cliques.
    let all_cliques = super::structure::maximal_cliques(graph);

    // Step 2: Filter to cliques of size >= k. Convert to sets of node IDs.
    let big_cliques: Vec<std::collections::HashSet<String>> = all_cliques
        .into_iter()
        .filter(|c| c.len() >= k)
        .map(|c| c.into_iter().collect())
        .collect();

    if big_cliques.is_empty() {
        return vec![];
    }

    let n = big_cliques.len();

    // Step 3: Build overlap graph using union-find.
    use petgraph::unionfind::UnionFind;
    let mut uf = UnionFind::new(n);

    for i in 0..n {
        for j in (i + 1)..n {
            let overlap = big_cliques[i].intersection(&big_cliques[j]).count();
            if overlap >= k - 1 {
                uf.union(i, j);
            }
        }
    }

    // Step 4: Group cliques by connected component.
    let mut component_map: std::collections::HashMap<usize, Vec<usize>> =
        std::collections::HashMap::new();
    for i in 0..n {
        let root = uf.find(i);
        component_map.entry(root).or_default().push(i);
    }

    // Step 5: Union all nodes in each component.
    let mut result: Vec<Vec<String>> = component_map
        .into_values()
        .map(|clique_indices| {
            let mut all_nodes: std::collections::HashSet<String> = std::collections::HashSet::new();
            for &ci in &clique_indices {
                all_nodes.extend(big_cliques[ci].iter().cloned());
            }
            let mut ids: Vec<String> = all_nodes.into_iter().collect();
            ids.sort();
            ids
        })
        .collect();

    result.sort_by(|a, b| a[0].cmp(&b[0]));
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Build two 4-cliques connected by a single bridge edge.
    fn two_cliques_graph() -> Graph {
        let mut g = Graph::new(false);
        for id in &["a", "b", "c", "d"] {
            g.add_node(id, HashMap::new()).unwrap();
        }
        for &(s, t) in &[
            ("a", "b"),
            ("a", "c"),
            ("a", "d"),
            ("b", "c"),
            ("b", "d"),
            ("c", "d"),
        ] {
            g.add_edge(s, t, HashMap::new()).unwrap();
        }
        for id in &["e", "f", "g", "h"] {
            g.add_node(id, HashMap::new()).unwrap();
        }
        for &(s, t) in &[
            ("e", "f"),
            ("e", "g"),
            ("e", "h"),
            ("f", "g"),
            ("f", "h"),
            ("g", "h"),
        ] {
            g.add_edge(s, t, HashMap::new()).unwrap();
        }
        // Bridge
        g.add_edge("d", "e", HashMap::new()).unwrap();
        g
    }

    #[test]
    fn test_louvain_two_cliques() {
        let g = two_cliques_graph();
        let communities = louvain_communities(&g);
        assert_eq!(communities.len(), 2);
        let mut sizes: Vec<usize> = communities.iter().map(|c| c.len()).collect();
        sizes.sort();
        assert_eq!(sizes, vec![4, 4]);

        let comm_of = |id: &str| -> usize {
            communities
                .iter()
                .position(|c| c.contains(&id.to_string()))
                .unwrap()
        };
        assert_eq!(comm_of("a"), comm_of("b"));
        assert_eq!(comm_of("a"), comm_of("c"));
        assert_eq!(comm_of("a"), comm_of("d"));
        assert_eq!(comm_of("e"), comm_of("f"));
        assert_eq!(comm_of("e"), comm_of("g"));
        assert_eq!(comm_of("e"), comm_of("h"));
        assert_ne!(comm_of("a"), comm_of("e"));
    }

    #[test]
    fn test_label_propagation_two_cliques() {
        let g = two_cliques_graph();
        let communities = label_propagation(&g);
        assert_eq!(communities.len(), 2);
        let mut sizes: Vec<usize> = communities.iter().map(|c| c.len()).collect();
        sizes.sort();
        assert_eq!(sizes, vec![4, 4]);

        let comm_of = |id: &str| -> usize {
            communities
                .iter()
                .position(|c| c.contains(&id.to_string()))
                .unwrap()
        };
        assert_eq!(comm_of("a"), comm_of("b"));
        assert_eq!(comm_of("e"), comm_of("f"));
        assert_ne!(comm_of("a"), comm_of("e"));
    }

    #[test]
    fn test_louvain_single_node() {
        let mut g = Graph::new(true);
        g.add_node("x", HashMap::new()).unwrap();
        let communities = louvain_communities(&g);
        assert_eq!(communities.len(), 1);
        assert_eq!(communities[0], vec!["x"]);
    }

    #[test]
    fn test_label_propagation_single_node() {
        let mut g = Graph::new(true);
        g.add_node("x", HashMap::new()).unwrap();
        let communities = label_propagation(&g);
        assert_eq!(communities.len(), 1);
        assert_eq!(communities[0], vec!["x"]);
    }

    #[test]
    fn test_louvain_empty_graph() {
        let g = Graph::new(true);
        let communities = louvain_communities(&g);
        assert!(communities.is_empty());
    }

    #[test]
    fn test_label_propagation_empty_graph() {
        let g = Graph::new(true);
        let communities = label_propagation(&g);
        assert!(communities.is_empty());
    }

    #[test]
    fn test_louvain_complete_graph() {
        let mut g = Graph::new(false);
        for id in &["a", "b", "c", "d"] {
            g.add_node(id, HashMap::new()).unwrap();
        }
        for &(s, t) in &[
            ("a", "b"),
            ("a", "c"),
            ("a", "d"),
            ("b", "c"),
            ("b", "d"),
            ("c", "d"),
        ] {
            g.add_edge(s, t, HashMap::new()).unwrap();
        }
        let communities = louvain_communities(&g);
        assert_eq!(communities.len(), 1);
        assert_eq!(communities[0].len(), 4);
    }

    #[test]
    fn test_label_propagation_complete_graph() {
        let mut g = Graph::new(false);
        for id in &["a", "b", "c", "d"] {
            g.add_node(id, HashMap::new()).unwrap();
        }
        for &(s, t) in &[
            ("a", "b"),
            ("a", "c"),
            ("a", "d"),
            ("b", "c"),
            ("b", "d"),
            ("c", "d"),
        ] {
            g.add_edge(s, t, HashMap::new()).unwrap();
        }
        let communities = label_propagation(&g);
        assert_eq!(communities.len(), 1);
        assert_eq!(communities[0].len(), 4);
    }

    #[test]
    fn test_louvain_disconnected_nodes() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        let communities = louvain_communities(&g);
        assert_eq!(communities.len(), 3);
    }

    #[test]
    fn test_label_propagation_disconnected_nodes() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        let communities = label_propagation(&g);
        assert_eq!(communities.len(), 3);
    }

    // =========================================================================
    // k-clique communities tests
    // =========================================================================

    #[test]
    fn test_k_clique_communities_two_triangles() {
        // Two triangles sharing edge b-c:
        // a-b, a-c, b-c  and  b-c, b-d, c-d
        // With k=3: each triangle is a 3-clique, they share 2 nodes (b,c)
        // which is >= k-1=2, so they merge into one community.
        let mut g = Graph::new(false);
        for id in &["a", "b", "c", "d"] {
            g.add_node(id, HashMap::new()).unwrap();
        }
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("b", "d", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();

        let communities = k_clique_communities(&g, 3);
        assert_eq!(communities.len(), 1);
        assert_eq!(communities[0].len(), 4);
    }

    #[test]
    fn test_k_clique_communities_separate_triangles() {
        // Two separate triangles with no shared edge.
        let mut g = Graph::new(false);
        for id in &["a", "b", "c", "d", "e", "f"] {
            g.add_node(id, HashMap::new()).unwrap();
        }
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "a", HashMap::new()).unwrap();
        g.add_edge("d", "e", HashMap::new()).unwrap();
        g.add_edge("e", "f", HashMap::new()).unwrap();
        g.add_edge("f", "d", HashMap::new()).unwrap();

        let communities = k_clique_communities(&g, 3);
        assert_eq!(communities.len(), 2);
        let sizes: Vec<usize> = communities.iter().map(|c| c.len()).collect();
        assert_eq!(sizes, vec![3, 3]);
    }

    #[test]
    fn test_k_clique_communities_no_cliques() {
        // Linear graph: no cliques of size >= 3.
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();

        let communities = k_clique_communities(&g, 3);
        assert!(communities.is_empty());
    }

    #[test]
    fn test_k_clique_communities_empty() {
        let g = Graph::new(false);
        let communities = k_clique_communities(&g, 3);
        assert!(communities.is_empty());
    }

    #[test]
    fn test_k_clique_communities_k2() {
        // k=2: every edge is a 2-clique. Two edges sharing a node overlap by 1 >= k-1=1.
        // So connected components of the edge graph = connected components of the graph.
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();

        let communities = k_clique_communities(&g, 2);
        assert_eq!(communities.len(), 1);
        assert_eq!(communities[0].len(), 3);
    }
}
