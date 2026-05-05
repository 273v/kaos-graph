//! Knowledge graph operations: merge, diff, subgraph extraction, triple
//! projection, type inference, and structural analysis.

use std::collections::{HashMap, HashSet};

use serde_json::Value;

use super::graph::Graph;

/// Diff between two graphs — added/removed nodes and edges, changed properties.
#[derive(Debug, Clone)]
pub struct GraphDiff {
    pub added_nodes: Vec<String>,
    pub removed_nodes: Vec<String>,
    pub added_edges: Vec<(String, String)>,
    pub removed_edges: Vec<(String, String)>,
    pub changed_node_properties: Vec<String>,
}

/// Merge two graphs with a configurable conflict strategy.
///
/// Strategies:
/// - `"keep_first"` — if a node/edge exists in both, keep *base*'s properties.
/// - `"keep_latest"` — if a node/edge exists in both, keep *other*'s properties (default).
/// - `"merge"` — merge property maps: *other*'s keys overwrite individual keys in *base*,
///   but keys only in *base* are preserved.
pub fn merge_graphs(base: &Graph, other: &Graph, conflict: &str) -> Graph {
    let mut merged = Graph::new(base.is_directed());

    // Collect all node IDs from both graphs.
    let base_ids: HashSet<&str> = base.node_ids().into_iter().collect();
    let other_ids: HashSet<&str> = other.node_ids().into_iter().collect();

    // Add nodes — strategy determines which properties win on overlap.
    for &id in &base_ids {
        let base_data = base.node(id).unwrap();
        if other_ids.contains(id) {
            let other_data = other.node(id).unwrap();
            let props = resolve_conflict(&base_data.properties, &other_data.properties, conflict);
            merged.add_node(id, props).ok();
        } else {
            merged.add_node(id, base_data.properties.clone()).ok();
        }
    }
    for &id in &other_ids {
        if !base_ids.contains(id) {
            let data = other.node(id).unwrap();
            merged.add_node(id, data.properties.clone()).ok();
        }
    }

    // Edges: index other's edges for quick lookup.
    let other_edge_set: HashMap<(&str, &str), &HashMap<String, Value>> = other
        .edges_vec()
        .into_iter()
        .map(|(s, t, d)| ((s, t), &d.properties))
        .collect();

    // Add base edges — conflict strategy applied when present in both.
    for (src, tgt, data) in base.edges_vec() {
        if merged.has_node(src) && merged.has_node(tgt) {
            let props = match other_edge_set.get(&(src, tgt)) {
                Some(other_props) => resolve_conflict(&data.properties, other_props, conflict),
                None => data.properties.clone(),
            };
            merged.add_edge(src, tgt, props).ok();
        }
    }

    // Add edges that exist only in other.
    for (src, tgt, data) in other.edges_vec() {
        if !merged.has_edge(src, tgt) && merged.has_node(src) && merged.has_node(tgt) {
            merged.add_edge(src, tgt, data.properties.clone()).ok();
        }
    }

    merged
}

/// Resolve a property conflict between base and other maps.
fn resolve_conflict(
    base_props: &HashMap<String, Value>,
    other_props: &HashMap<String, Value>,
    strategy: &str,
) -> HashMap<String, Value> {
    match strategy {
        "keep_first" => base_props.clone(),
        "merge" => {
            let mut merged = base_props.clone();
            for (k, v) in other_props {
                merged.insert(k.clone(), v.clone());
            }
            merged
        }
        // "keep_latest" and any unrecognised string default to other-wins
        _ => other_props.clone(),
    }
}

/// Diff two graphs.  Returns added/removed nodes, edges, and nodes whose
/// properties changed.
pub fn diff_graphs(old: &Graph, new: &Graph) -> GraphDiff {
    let old_ids: HashSet<&str> = old.node_ids().into_iter().collect();
    let new_ids: HashSet<&str> = new.node_ids().into_iter().collect();

    let added_nodes: Vec<String> = new_ids
        .difference(&old_ids)
        .map(|s| s.to_string())
        .collect();
    let removed_nodes: Vec<String> = old_ids
        .difference(&new_ids)
        .map(|s| s.to_string())
        .collect();

    // Changed properties: nodes in both with differing properties.
    let mut changed_node_properties = Vec::new();
    for &id in old_ids.intersection(&new_ids) {
        let old_props = &old.node(id).unwrap().properties;
        let new_props = &new.node(id).unwrap().properties;
        if old_props != new_props {
            changed_node_properties.push(id.to_string());
        }
    }

    // Edges.
    let old_edges: HashSet<(String, String)> = old
        .edges_vec()
        .iter()
        .map(|(s, t, _)| (s.to_string(), t.to_string()))
        .collect();
    let new_edges: HashSet<(String, String)> = new
        .edges_vec()
        .iter()
        .map(|(s, t, _)| (s.to_string(), t.to_string()))
        .collect();

    let added_edges: Vec<(String, String)> = new_edges.difference(&old_edges).cloned().collect();
    let removed_edges: Vec<(String, String)> = old_edges.difference(&new_edges).cloned().collect();

    GraphDiff {
        added_nodes,
        removed_nodes,
        added_edges,
        removed_edges,
        changed_node_properties,
    }
}

/// Add transitive closure edges for a specific relationship type.
///
/// If A->B and B->C both have the given predicate, add A->C with that
/// predicate.  Returns a new graph with original edges plus all inferred
/// transitive edges.  This is functionally identical to [`infer_types`] —
/// provided as a semantic alias for non-type-hierarchy use cases.
pub fn densify(graph: &Graph, predicate: &str) -> Graph {
    infer_types(graph, predicate)
}

/// Extract subgraph containing nodes whose "type" property matches any
/// value in the provided list.
///
/// All edges between matching nodes are preserved.
pub fn extract_subgraph_by_types(graph: &Graph, types: &[String]) -> Graph {
    let type_set: HashSet<&str> = types.iter().map(|s| s.as_str()).collect();

    let matching: Vec<&str> = graph
        .node_ids()
        .into_iter()
        .filter(|&id| {
            graph
                .node(id)
                .and_then(|n| n.properties.get("type"))
                .and_then(|v| v.as_str())
                .is_some_and(|t| type_set.contains(t))
        })
        .collect();

    graph
        .subgraph(&matching)
        .unwrap_or_else(|_| Graph::new(graph.is_directed()))
}

/// Extract subgraph by filtering nodes on a property value.
///
/// For example, `extract_subgraph_by_property(g, "type", &Value::String("person".into()))`
/// returns a subgraph of all nodes whose `type` property equals `"person"`.
pub fn extract_subgraph_by_property(graph: &Graph, key: &str, value: &Value) -> Graph {
    let matching: Vec<&str> = graph
        .node_ids()
        .into_iter()
        .filter(|&id| {
            graph
                .node(id)
                .map(|n| n.properties.get(key) == Some(value))
                .unwrap_or(false)
        })
        .collect();

    // Reuse the existing subgraph method (which copies edges between matching nodes).
    graph.subgraph(&matching).unwrap_or_else(|_| {
        // Empty graph on error (should not happen).
        Graph::new(graph.is_directed())
    })
}

/// Project graph edges as (subject, predicate, object) triples.
///
/// Uses the edge `predicate` property if present, then `"type"`, otherwise `"relatedTo"`.
pub fn project_triples(graph: &Graph) -> Vec<(String, String, String)> {
    graph
        .edges_vec()
        .iter()
        .map(|(src, tgt, data)| {
            let predicate = data
                .properties
                .get("predicate")
                .and_then(|v| v.as_str())
                .or_else(|| data.properties.get("type").and_then(|v| v.as_str()))
                .unwrap_or("relatedTo")
                .to_string();
            (src.to_string(), predicate, tgt.to_string())
        })
        .collect()
}

/// Build a graph from (subject, predicate, object) triples.
///
/// Each unique subject/object becomes a node. Each triple becomes an edge with
/// both `predicate` and `type` properties, so both RDF export and schema
/// validation work on the resulting graph.
pub fn from_triples(triples: &[(String, String, String)], directed: bool) -> Graph {
    let mut g = Graph::new(directed);

    for (subj, pred, obj) in triples {
        if !g.has_node(subj) {
            g.add_node(subj, HashMap::new()).ok();
        }
        if !g.has_node(obj) {
            g.add_node(obj, HashMap::new()).ok();
        }
        let mut props = HashMap::new();
        props.insert("predicate".to_string(), Value::String(pred.clone()));
        props.insert("type".to_string(), Value::String(pred.clone()));
        g.add_edge(subj, obj, props).ok();
    }

    g
}

/// Infer transitive types via a specific predicate (e.g., `"subClassOf"`).
///
/// If A->B via `predicate_iri` and B->C via `predicate_iri`, add A->C via
/// `predicate_iri`.  Returns a new graph with the original edges plus all
/// inferred transitive edges.
pub fn infer_types(graph: &Graph, predicate_iri: &str) -> Graph {
    // Clone the full graph.
    let json = graph.to_json().unwrap_or_default();
    let mut result = Graph::from_json(&json).unwrap_or_else(|_| Graph::new(graph.is_directed()));

    // Build an adjacency set of nodes connected by the target predicate.
    // Check both "predicate" and "type" properties for the target predicate.
    let mut pred_adj: HashMap<String, HashSet<String>> = HashMap::new();
    for (src, tgt, data) in graph.edges_vec() {
        let pred = data
            .properties
            .get("predicate")
            .and_then(|v| v.as_str())
            .or_else(|| data.properties.get("type").and_then(|v| v.as_str()))
            .unwrap_or("");
        if pred == predicate_iri {
            pred_adj
                .entry(src.to_string())
                .or_default()
                .insert(tgt.to_string());
        }
    }

    // Compute transitive closure on the predicate-specific edges (Warshall-ish).
    let nodes: Vec<String> = pred_adj.keys().cloned().collect();
    let mut changed = true;
    while changed {
        changed = false;
        for node in &nodes {
            let targets: Vec<String> = pred_adj
                .get(node)
                .map(|s| s.iter().cloned().collect())
                .unwrap_or_default();
            for target in targets {
                let transitive: Vec<String> = pred_adj
                    .get(&target)
                    .map(|s| s.iter().cloned().collect())
                    .unwrap_or_default();
                for t in transitive {
                    if pred_adj.entry(node.clone()).or_default().insert(t.clone()) {
                        changed = true;
                    }
                }
            }
        }
    }

    // Add inferred edges that don't already exist.
    for (src, targets) in &pred_adj {
        for tgt in targets {
            if !result.has_edge(src, tgt) {
                if !result.has_node(src) {
                    result.add_node(src, HashMap::new()).ok();
                }
                if !result.has_node(tgt) {
                    result.add_node(tgt, HashMap::new()).ok();
                }
                let mut props = HashMap::new();
                props.insert(
                    "predicate".to_string(),
                    Value::String(predicate_iri.to_string()),
                );
                props.insert("type".to_string(), Value::String(predicate_iri.to_string()));
                result.add_edge(src, tgt, props).ok();
            }
        }
    }

    result
}

/// Find orphan nodes (degree 0 — no incident edges).
pub fn find_orphan_nodes(graph: &Graph) -> Vec<String> {
    graph
        .node_ids()
        .into_iter()
        .filter(|&id| graph.degree(id).unwrap_or(0) == 0)
        .map(|s| s.to_string())
        .collect()
}

/// Find hub nodes (degree > `threshold`).
pub fn find_hub_nodes(graph: &Graph, threshold: usize) -> Vec<String> {
    graph
        .node_ids()
        .into_iter()
        .filter(|&id| graph.degree(id).unwrap_or(0) > threshold)
        .map(|s| s.to_string())
        .collect()
}

/// Degree distribution: returns (degree -> count) map.
pub fn degree_distribution(graph: &Graph) -> HashMap<usize, usize> {
    let mut dist: HashMap<usize, usize> = HashMap::new();
    for &id in &graph.node_ids() {
        let deg = graph.degree(id).unwrap_or(0);
        *dist.entry(deg).or_insert(0) += 1;
    }
    dist
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn make_simple_graph() -> Graph {
        let mut g = Graph::new(true);
        let mut props_a = HashMap::new();
        props_a.insert("type".to_string(), Value::String("person".to_string()));
        props_a.insert("name".to_string(), Value::String("Alice".to_string()));
        g.add_node("a", props_a).unwrap();

        let mut props_b = HashMap::new();
        props_b.insert("type".to_string(), Value::String("person".to_string()));
        props_b.insert("name".to_string(), Value::String("Bob".to_string()));
        g.add_node("b", props_b).unwrap();

        let mut props_c = HashMap::new();
        props_c.insert("type".to_string(), Value::String("org".to_string()));
        g.add_node("c", props_c).unwrap();

        let mut edge_props = HashMap::new();
        edge_props.insert("predicate".to_string(), Value::String("knows".to_string()));
        g.add_edge("a", "b", edge_props).unwrap();

        let mut edge_props2 = HashMap::new();
        edge_props2.insert(
            "predicate".to_string(),
            Value::String("worksAt".to_string()),
        );
        g.add_edge("a", "c", edge_props2).unwrap();

        g
    }

    #[test]
    fn test_merge_graphs_disjoint() {
        let mut g1 = Graph::new(true);
        g1.add_node("a", HashMap::new()).unwrap();

        let mut g2 = Graph::new(true);
        g2.add_node("b", HashMap::new()).unwrap();

        let merged = merge_graphs(&g1, &g2, "keep_latest");
        assert_eq!(merged.n_nodes(), 2);
        assert!(merged.has_node("a"));
        assert!(merged.has_node("b"));
    }

    #[test]
    fn test_merge_graphs_overlapping_nodes() {
        let mut g1 = Graph::new(true);
        let mut p1 = HashMap::new();
        p1.insert("v".to_string(), Value::Number(1.into()));
        g1.add_node("x", p1).unwrap();

        let mut g2 = Graph::new(true);
        let mut p2 = HashMap::new();
        p2.insert("v".to_string(), Value::Number(2.into()));
        g2.add_node("x", p2).unwrap();

        let merged = merge_graphs(&g1, &g2, "keep_latest");
        assert_eq!(merged.n_nodes(), 1);
        // other wins
        assert_eq!(
            merged.node("x").unwrap().properties["v"],
            Value::Number(2.into())
        );
    }

    #[test]
    fn test_merge_graphs_keep_first() {
        let mut g1 = Graph::new(true);
        let mut p1 = HashMap::new();
        p1.insert("v".to_string(), Value::Number(1.into()));
        g1.add_node("x", p1).unwrap();

        let mut g2 = Graph::new(true);
        let mut p2 = HashMap::new();
        p2.insert("v".to_string(), Value::Number(2.into()));
        g2.add_node("x", p2).unwrap();

        let merged = merge_graphs(&g1, &g2, "keep_first");
        assert_eq!(merged.n_nodes(), 1);
        // base wins
        assert_eq!(
            merged.node("x").unwrap().properties["v"],
            Value::Number(1.into())
        );
    }

    #[test]
    fn test_merge_graphs_merge_strategy() {
        let mut g1 = Graph::new(true);
        let mut p1 = HashMap::new();
        p1.insert("a".to_string(), Value::Number(1.into()));
        p1.insert("b".to_string(), Value::Number(2.into()));
        g1.add_node("x", p1).unwrap();

        let mut g2 = Graph::new(true);
        let mut p2 = HashMap::new();
        p2.insert("b".to_string(), Value::Number(99.into()));
        p2.insert("c".to_string(), Value::Number(3.into()));
        g2.add_node("x", p2).unwrap();

        let merged = merge_graphs(&g1, &g2, "merge");
        assert_eq!(merged.n_nodes(), 1);
        let props = &merged.node("x").unwrap().properties;
        // "a" only in base — preserved
        assert_eq!(props["a"], Value::Number(1.into()));
        // "b" in both — other overwrites
        assert_eq!(props["b"], Value::Number(99.into()));
        // "c" only in other — added
        assert_eq!(props["c"], Value::Number(3.into()));
    }

    #[test]
    fn test_merge_graphs_edges() {
        let mut g1 = Graph::new(true);
        g1.add_node("a", HashMap::new()).unwrap();
        g1.add_node("b", HashMap::new()).unwrap();
        g1.add_edge("a", "b", HashMap::new()).unwrap();

        let mut g2 = Graph::new(true);
        g2.add_node("b", HashMap::new()).unwrap();
        g2.add_node("c", HashMap::new()).unwrap();
        g2.add_edge("b", "c", HashMap::new()).unwrap();

        let merged = merge_graphs(&g1, &g2, "keep_latest");
        assert_eq!(merged.n_nodes(), 3);
        assert!(merged.has_edge("a", "b"));
        assert!(merged.has_edge("b", "c"));
    }

    #[test]
    fn test_merge_graphs_edge_property_override() {
        let mut g1 = Graph::new(true);
        g1.add_node("a", HashMap::new()).unwrap();
        g1.add_node("b", HashMap::new()).unwrap();
        let mut ep1 = HashMap::new();
        ep1.insert("weight".to_string(), Value::Number(1.into()));
        g1.add_edge("a", "b", ep1).unwrap();

        let mut g2 = Graph::new(true);
        g2.add_node("a", HashMap::new()).unwrap();
        g2.add_node("b", HashMap::new()).unwrap();
        let mut ep2 = HashMap::new();
        ep2.insert("weight".to_string(), Value::Number(99.into()));
        g2.add_edge("a", "b", ep2).unwrap();

        let merged = merge_graphs(&g1, &g2, "keep_latest");
        // other edge properties win
        let edges = merged.edges_vec();
        let ab = edges.iter().find(|(s, t, _)| *s == "a" && *t == "b");
        assert!(ab.is_some());
        assert_eq!(ab.unwrap().2.properties["weight"], Value::Number(99.into()));
    }

    #[test]
    fn test_merge_graphs_edge_keep_first() {
        let mut g1 = Graph::new(true);
        g1.add_node("a", HashMap::new()).unwrap();
        g1.add_node("b", HashMap::new()).unwrap();
        let mut ep1 = HashMap::new();
        ep1.insert("weight".to_string(), Value::Number(1.into()));
        g1.add_edge("a", "b", ep1).unwrap();

        let mut g2 = Graph::new(true);
        g2.add_node("a", HashMap::new()).unwrap();
        g2.add_node("b", HashMap::new()).unwrap();
        let mut ep2 = HashMap::new();
        ep2.insert("weight".to_string(), Value::Number(99.into()));
        g2.add_edge("a", "b", ep2).unwrap();

        let merged = merge_graphs(&g1, &g2, "keep_first");
        let edges = merged.edges_vec();
        let ab = edges.iter().find(|(s, t, _)| *s == "a" && *t == "b");
        assert!(ab.is_some());
        // base wins
        assert_eq!(ab.unwrap().2.properties["weight"], Value::Number(1.into()));
    }

    #[test]
    fn test_densify() {
        // A->B->C via "knows" — densify should add A->C.
        let mut g = Graph::new(true);
        g.add_node("A", HashMap::new()).unwrap();
        g.add_node("B", HashMap::new()).unwrap();
        g.add_node("C", HashMap::new()).unwrap();

        let mut p1 = HashMap::new();
        p1.insert("predicate".to_string(), Value::String("knows".to_string()));
        g.add_edge("A", "B", p1).unwrap();

        let mut p2 = HashMap::new();
        p2.insert("predicate".to_string(), Value::String("knows".to_string()));
        g.add_edge("B", "C", p2).unwrap();

        let dense = densify(&g, "knows");
        assert!(dense.has_edge("A", "B"));
        assert!(dense.has_edge("B", "C"));
        assert!(dense.has_edge("A", "C")); // transitive
    }

    #[test]
    fn test_extract_subgraph_by_types() {
        let g = make_simple_graph();
        // a,b are "person"; c is "org"
        let sub = extract_subgraph_by_types(&g, &["person".to_string()]);
        assert_eq!(sub.n_nodes(), 2);
        assert!(sub.has_node("a"));
        assert!(sub.has_node("b"));
        assert!(!sub.has_node("c"));
        assert!(sub.has_edge("a", "b"));
    }

    #[test]
    fn test_extract_subgraph_by_types_multiple() {
        let g = make_simple_graph();
        let sub = extract_subgraph_by_types(&g, &["person".to_string(), "org".to_string()]);
        assert_eq!(sub.n_nodes(), 3);
        assert!(sub.has_edge("a", "b"));
        assert!(sub.has_edge("a", "c"));
    }

    #[test]
    fn test_extract_subgraph_by_types_empty() {
        let g = make_simple_graph();
        let sub = extract_subgraph_by_types(&g, &["nonexistent".to_string()]);
        assert_eq!(sub.n_nodes(), 0);
    }

    #[test]
    fn test_diff_graphs_no_change() {
        let g = make_simple_graph();
        let diff = diff_graphs(&g, &g);
        assert!(diff.added_nodes.is_empty());
        assert!(diff.removed_nodes.is_empty());
        assert!(diff.added_edges.is_empty());
        assert!(diff.removed_edges.is_empty());
        assert!(diff.changed_node_properties.is_empty());
    }

    #[test]
    fn test_diff_graphs_added_removed() {
        let mut old = Graph::new(true);
        old.add_node("a", HashMap::new()).unwrap();
        old.add_node("b", HashMap::new()).unwrap();

        let mut new = Graph::new(true);
        new.add_node("b", HashMap::new()).unwrap();
        new.add_node("c", HashMap::new()).unwrap();

        let diff = diff_graphs(&old, &new);
        assert!(diff.added_nodes.contains(&"c".to_string()));
        assert!(diff.removed_nodes.contains(&"a".to_string()));
    }

    #[test]
    fn test_diff_graphs_changed_properties() {
        let mut old = Graph::new(true);
        let mut p1 = HashMap::new();
        p1.insert("v".to_string(), Value::Number(1.into()));
        old.add_node("x", p1).unwrap();

        let mut new = Graph::new(true);
        let mut p2 = HashMap::new();
        p2.insert("v".to_string(), Value::Number(2.into()));
        new.add_node("x", p2).unwrap();

        let diff = diff_graphs(&old, &new);
        assert!(diff.changed_node_properties.contains(&"x".to_string()));
    }

    #[test]
    fn test_diff_graphs_edges() {
        let mut old = Graph::new(true);
        old.add_node("a", HashMap::new()).unwrap();
        old.add_node("b", HashMap::new()).unwrap();
        old.add_edge("a", "b", HashMap::new()).unwrap();

        let mut new = Graph::new(true);
        new.add_node("a", HashMap::new()).unwrap();
        new.add_node("b", HashMap::new()).unwrap();
        new.add_node("c", HashMap::new()).unwrap();
        new.add_edge("a", "c", HashMap::new()).unwrap();

        let diff = diff_graphs(&old, &new);
        assert!(diff
            .added_edges
            .contains(&("a".to_string(), "c".to_string())));
        assert!(diff
            .removed_edges
            .contains(&("a".to_string(), "b".to_string())));
    }

    #[test]
    fn test_extract_subgraph_by_property() {
        let g = make_simple_graph();
        let sub = extract_subgraph_by_property(&g, "type", &Value::String("person".to_string()));
        assert_eq!(sub.n_nodes(), 2);
        assert!(sub.has_node("a"));
        assert!(sub.has_node("b"));
        assert!(!sub.has_node("c"));
        // Edge a->b should be present (both endpoints are persons).
        assert!(sub.has_edge("a", "b"));
        // Edge a->c should not (c is not a person).
        assert!(!sub.has_edge("a", "c"));
    }

    #[test]
    fn test_extract_subgraph_by_property_no_match() {
        let g = make_simple_graph();
        let sub =
            extract_subgraph_by_property(&g, "type", &Value::String("nonexistent".to_string()));
        assert_eq!(sub.n_nodes(), 0);
    }

    #[test]
    fn test_project_triples() {
        let g = make_simple_graph();
        let triples = project_triples(&g);
        assert_eq!(triples.len(), 2);

        let knows = triples
            .iter()
            .find(|(s, p, o)| s == "a" && o == "b" && p == "knows");
        assert!(knows.is_some());

        let works = triples
            .iter()
            .find(|(s, p, o)| s == "a" && o == "c" && p == "worksAt");
        assert!(works.is_some());
    }

    #[test]
    fn test_project_triples_default_predicate() {
        let mut g = Graph::new(true);
        g.add_node("x", HashMap::new()).unwrap();
        g.add_node("y", HashMap::new()).unwrap();
        g.add_edge("x", "y", HashMap::new()).unwrap();

        let triples = project_triples(&g);
        assert_eq!(triples.len(), 1);
        assert_eq!(triples[0].1, "relatedTo");
    }

    #[test]
    fn test_from_triples() {
        let triples = vec![
            ("A".to_string(), "knows".to_string(), "B".to_string()),
            ("B".to_string(), "knows".to_string(), "C".to_string()),
        ];
        let g = from_triples(&triples, true);
        assert_eq!(g.n_nodes(), 3);
        assert_eq!(g.n_edges(), 2);
        assert!(g.has_edge("A", "B"));
        assert!(g.has_edge("B", "C"));
    }

    #[test]
    fn test_from_triples_roundtrip() {
        let g = make_simple_graph();
        let triples = project_triples(&g);
        let triple_tuples: Vec<(String, String, String)> = triples;
        let g2 = from_triples(&triple_tuples, true);
        assert_eq!(g2.n_nodes(), g.n_nodes());
        assert_eq!(g2.n_edges(), g.n_edges());
    }

    #[test]
    fn test_infer_types() {
        // A subClassOf B, B subClassOf C → should infer A subClassOf C.
        let mut g = Graph::new(true);
        g.add_node("A", HashMap::new()).unwrap();
        g.add_node("B", HashMap::new()).unwrap();
        g.add_node("C", HashMap::new()).unwrap();

        let mut p1 = HashMap::new();
        p1.insert(
            "predicate".to_string(),
            Value::String("subClassOf".to_string()),
        );
        g.add_edge("A", "B", p1).unwrap();

        let mut p2 = HashMap::new();
        p2.insert(
            "predicate".to_string(),
            Value::String("subClassOf".to_string()),
        );
        g.add_edge("B", "C", p2).unwrap();

        let inferred = infer_types(&g, "subClassOf");
        // Should have the original 2 edges plus the inferred A->C.
        assert!(inferred.has_edge("A", "B"));
        assert!(inferred.has_edge("B", "C"));
        assert!(inferred.has_edge("A", "C")); // inferred!
    }

    #[test]
    fn test_infer_types_no_new_edges() {
        let mut g = Graph::new(true);
        g.add_node("A", HashMap::new()).unwrap();
        g.add_node("B", HashMap::new()).unwrap();

        let mut p = HashMap::new();
        p.insert("predicate".to_string(), Value::String("knows".to_string()));
        g.add_edge("A", "B", p).unwrap();

        // Different predicate — no inference.
        let inferred = infer_types(&g, "subClassOf");
        assert_eq!(inferred.n_edges(), 1);
    }

    #[test]
    fn test_infer_types_chain() {
        // A→B→C→D via "isa" → should infer A→C, A→D, B→D.
        let mut g = Graph::new(true);
        for id in &["A", "B", "C", "D"] {
            g.add_node(id, HashMap::new()).unwrap();
        }
        for (s, t) in &[("A", "B"), ("B", "C"), ("C", "D")] {
            let mut p = HashMap::new();
            p.insert("predicate".to_string(), Value::String("isa".to_string()));
            g.add_edge(s, t, p).unwrap();
        }

        let inferred = infer_types(&g, "isa");
        assert!(inferred.has_edge("A", "C"));
        assert!(inferred.has_edge("A", "D"));
        assert!(inferred.has_edge("B", "D"));
    }

    #[test]
    fn test_find_orphan_nodes() {
        let mut g = Graph::new(true);
        g.add_node("connected_a", HashMap::new()).unwrap();
        g.add_node("connected_b", HashMap::new()).unwrap();
        g.add_node("orphan", HashMap::new()).unwrap();
        g.add_edge("connected_a", "connected_b", HashMap::new())
            .unwrap();

        let orphans = find_orphan_nodes(&g);
        assert_eq!(orphans, vec!["orphan"]);
    }

    #[test]
    fn test_find_orphan_nodes_empty() {
        let g = Graph::new(true);
        let orphans = find_orphan_nodes(&g);
        assert!(orphans.is_empty());
    }

    #[test]
    fn test_find_hub_nodes() {
        let mut g = Graph::new(true);
        g.add_node("hub", HashMap::new()).unwrap();
        for i in 0..5 {
            let id = format!("n{}", i);
            g.add_node(&id, HashMap::new()).unwrap();
            g.add_edge("hub", &id, HashMap::new()).unwrap();
        }

        // Threshold 3: hub should qualify (degree 5 out).
        let hubs = find_hub_nodes(&g, 3);
        assert!(hubs.contains(&"hub".to_string()));
        // Leaf nodes have degree 1 — should not be hubs.
        assert!(!hubs.contains(&"n0".to_string()));
    }

    #[test]
    fn test_find_hub_nodes_none() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();

        let hubs = find_hub_nodes(&g, 10);
        assert!(hubs.is_empty());
    }

    #[test]
    fn test_degree_distribution() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap(); // orphan
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();

        let dist = degree_distribution(&g);
        // a: out=2, b: in=1, c: in=1, d: 0
        assert_eq!(dist[&0], 1); // d
        assert_eq!(dist[&1], 2); // b, c
        assert_eq!(dist[&2], 1); // a
    }

    #[test]
    fn test_degree_distribution_empty() {
        let g = Graph::new(true);
        let dist = degree_distribution(&g);
        assert!(dist.is_empty());
    }

    #[test]
    fn test_from_triples_sets_both_type_and_predicate() {
        let triples = vec![("A".to_string(), "knows".to_string(), "B".to_string())];
        let g = from_triples(&triples, true);
        let edges = g.edges_vec();
        assert_eq!(edges.len(), 1);
        let (_, _, data) = &edges[0];
        // Both "predicate" and "type" should be set.
        assert_eq!(
            data.properties.get("predicate").and_then(|v| v.as_str()),
            Some("knows")
        );
        assert_eq!(
            data.properties.get("type").and_then(|v| v.as_str()),
            Some("knows")
        );
    }

    #[test]
    fn test_project_triples_reads_type_if_predicate_absent() {
        // Edge with only "type" set, no "predicate"
        let mut g = Graph::new(true);
        g.add_node("x", HashMap::new()).unwrap();
        g.add_node("y", HashMap::new()).unwrap();
        let mut props = HashMap::new();
        props.insert("type".to_string(), Value::String("knows".to_string()));
        g.add_edge("x", "y", props).unwrap();

        let triples = project_triples(&g);
        assert_eq!(triples.len(), 1);
        assert_eq!(triples[0].1, "knows");
    }

    #[test]
    fn test_infer_types_reads_type_property() {
        // Edges with only "type" set (no "predicate") should still be inferred.
        let mut g = Graph::new(true);
        g.add_node("A", HashMap::new()).unwrap();
        g.add_node("B", HashMap::new()).unwrap();
        g.add_node("C", HashMap::new()).unwrap();

        let mut p1 = HashMap::new();
        p1.insert("type".to_string(), Value::String("subClassOf".to_string()));
        g.add_edge("A", "B", p1).unwrap();

        let mut p2 = HashMap::new();
        p2.insert("type".to_string(), Value::String("subClassOf".to_string()));
        g.add_edge("B", "C", p2).unwrap();

        let inferred = infer_types(&g, "subClassOf");
        assert!(inferred.has_edge("A", "B"));
        assert!(inferred.has_edge("B", "C"));
        assert!(inferred.has_edge("A", "C")); // inferred!
    }
}
