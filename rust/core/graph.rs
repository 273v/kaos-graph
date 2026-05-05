use std::collections::HashMap;

use petgraph::stable_graph::{EdgeIndex, NodeIndex, StableDiGraph, StableUnGraph};
use petgraph::visit::{EdgeRef, IntoEdgeReferences, NodeIndexable};
use petgraph::Direction;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::edge::EdgeData;
use super::node::NodeData;

/// Internal storage: directed or undirected stable graph.
///
/// Using an enum rather than a type-erased trait object keeps everything
/// monomorphic — no dynamic dispatch, no trait-object limitations.
/// The `with_inner!` macro dispatches to the correct variant.
pub(crate) enum GraphInner {
    Directed(StableDiGraph<NodeData, EdgeData>),
    Undirected(StableUnGraph<NodeData, EdgeData>),
}

/// Dispatch a read-only method call to the inner graph variant.
///
/// Both `StableDiGraph` and `StableUnGraph` implement the same
/// structural methods, so the body compiles for both.
macro_rules! with_inner {
    ($self:expr, $g:ident => $body:expr) => {
        match &$self.inner {
            GraphInner::Directed($g) => $body,
            GraphInner::Undirected($g) => $body,
        }
    };
    (mut $self:expr, $g:ident => $body:expr) => {
        match &mut $self.inner {
            GraphInner::Directed($g) => $body,
            GraphInner::Undirected($g) => $body,
        }
    };
}

/// Core graph type. String-keyed, property-bearing, backed by petgraph.
///
/// Directed graphs use `StableDiGraph`; undirected graphs use `StableUnGraph`.
/// StableGraph variants preserve node indices on removal, which is critical
/// for the string-ID-to-NodeIndex mapping.
///
/// When `multi` is `false` (default), parallel edges are rejected.
/// When `multi` is `true`, multiple edges between the same pair of nodes are allowed.
pub struct Graph {
    pub(crate) inner: GraphInner,
    id_to_index: HashMap<String, NodeIndex>,
    directed: bool,
    multi: bool,
    name: String,
}

impl Graph {
    pub fn new(directed: bool) -> Self {
        Self::new_multi(directed, false)
    }

    pub fn new_multi(directed: bool, multi: bool) -> Self {
        let inner = if directed {
            GraphInner::Directed(StableDiGraph::new())
        } else {
            GraphInner::Undirected(StableUnGraph::default())
        };
        Self {
            inner,
            id_to_index: HashMap::new(),
            directed,
            multi,
            name: String::new(),
        }
    }

    pub fn with_name(directed: bool, name: String) -> Self {
        Self::with_name_multi(directed, false, name)
    }

    pub fn with_name_multi(directed: bool, multi: bool, name: String) -> Self {
        let inner = if directed {
            GraphInner::Directed(StableDiGraph::new())
        } else {
            GraphInner::Undirected(StableUnGraph::default())
        };
        Self {
            inner,
            id_to_index: HashMap::new(),
            directed,
            multi,
            name,
        }
    }

    // --- Mutation ---

    pub fn add_node(&mut self, id: &str, properties: HashMap<String, Value>) -> Result<(), String> {
        if self.id_to_index.contains_key(id) {
            return Err(format!("Node '{}' already exists", id));
        }
        let data = NodeData {
            id: id.to_string(),
            properties,
        };
        let idx = with_inner!(mut self, g => g.add_node(data));
        self.id_to_index.insert(id.to_string(), idx);
        Ok(())
    }

    pub fn add_edge(
        &mut self,
        source: &str,
        target: &str,
        properties: HashMap<String, Value>,
    ) -> Result<EdgeIndex, String> {
        let src_idx = self
            .id_to_index
            .get(source)
            .copied()
            .ok_or_else(|| format!("Source node '{}' not found", source))?;
        let tgt_idx = self
            .id_to_index
            .get(target)
            .copied()
            .ok_or_else(|| format!("Target node '{}' not found", target))?;

        // Enforce simple graph semantics unless multi-graph mode is enabled.
        if !self.multi {
            let existing = match &self.inner {
                GraphInner::Directed(g) => g.find_edge(src_idx, tgt_idx).is_some(),
                GraphInner::Undirected(g) => g.find_edge(src_idx, tgt_idx).is_some(),
            };
            if existing {
                return Err(format!("Edge '{}' -> '{}' already exists", source, target));
            }
        }

        let data = EdgeData { properties };
        // One edge — petgraph handles undirected semantics internally.
        let edge_idx = with_inner!(mut self, g => g.add_edge(src_idx, tgt_idx, data));
        Ok(edge_idx)
    }

    pub fn remove_node(&mut self, id: &str) -> Result<NodeData, String> {
        let idx = self
            .id_to_index
            .remove(id)
            .ok_or_else(|| format!("Node '{}' not found", id))?;
        with_inner!(mut self, g => {
            g.remove_node(idx)
                .ok_or_else(|| format!("Node '{}' not found in graph", id))
        })
    }

    /// Merge properties into an existing node. Existing properties are preserved
    /// unless overwritten by the new values.
    pub fn update_node(
        &mut self,
        id: &str,
        properties: HashMap<String, Value>,
    ) -> Result<(), String> {
        let idx = self
            .id_to_index
            .get(id)
            .copied()
            .ok_or_else(|| format!("Node '{}' not found", id))?;
        with_inner!(mut self, g => {
            let data = g.node_weight_mut(idx)
                .ok_or_else(|| format!("Node '{}' not found in graph", id))?;
            for (k, v) in properties {
                data.properties.insert(k, v);
            }
            Ok(())
        })
    }

    /// Set a single property on an existing node.
    pub fn set_node_property(&mut self, id: &str, key: &str, value: Value) -> Result<(), String> {
        let idx = self
            .id_to_index
            .get(id)
            .copied()
            .ok_or_else(|| format!("Node '{}' not found", id))?;
        with_inner!(mut self, g => {
            let data = g.node_weight_mut(idx)
                .ok_or_else(|| format!("Node '{}' not found in graph", id))?;
            data.properties.insert(key.to_string(), value);
            Ok(())
        })
    }

    pub fn remove_edge(&mut self, source: &str, target: &str) -> Result<(), String> {
        let src_idx = self
            .id_to_index
            .get(source)
            .copied()
            .ok_or_else(|| format!("Source node '{}' not found", source))?;
        let tgt_idx = self
            .id_to_index
            .get(target)
            .copied()
            .ok_or_else(|| format!("Target node '{}' not found", target))?;

        let edge = with_inner!(self, g => {
            g.find_edge(src_idx, tgt_idx)
                .ok_or_else(|| format!("Edge '{}' -> '{}' not found", source, target))
        })?;
        with_inner!(mut self, g => g.remove_edge(edge));
        Ok(())
    }

    // --- Query ---

    pub fn node(&self, id: &str) -> Option<&NodeData> {
        self.id_to_index
            .get(id)
            .and_then(|&idx| with_inner!(self, g => g.node_weight(idx)))
    }

    pub fn node_ids(&self) -> Vec<&str> {
        with_inner!(self, g => g.node_weights().map(|n| n.id.as_str()).collect())
    }

    pub fn edges_vec(&self) -> Vec<(&str, &str, &EdgeData)> {
        match &self.inner {
            GraphInner::Directed(g) => g
                .edge_references()
                .map(|e| {
                    let src = &g[e.source()].id;
                    let tgt = &g[e.target()].id;
                    (src.as_str(), tgt.as_str(), e.weight())
                })
                .collect(),
            GraphInner::Undirected(g) => g
                .edge_references()
                .map(|e| {
                    let src = &g[e.source()].id;
                    let tgt = &g[e.target()].id;
                    (src.as_str(), tgt.as_str(), e.weight())
                })
                .collect(),
        }
    }

    pub fn neighbors(&self, id: &str) -> Result<Vec<&str>, String> {
        let idx = self.resolve_index(id)?;
        // For both directed and undirected, petgraph .neighbors() gives
        // outgoing for directed and all adjacent for undirected.
        // For a full neighbor set on directed graphs, we union both directions.
        match &self.inner {
            GraphInner::Directed(g) => {
                let mut result: Vec<&str> = Vec::new();
                for n in g.neighbors_directed(idx, Direction::Outgoing) {
                    result.push(g[n].id.as_str());
                }
                for n in g.neighbors_directed(idx, Direction::Incoming) {
                    if !result.contains(&g[n].id.as_str()) {
                        result.push(g[n].id.as_str());
                    }
                }
                Ok(result)
            }
            GraphInner::Undirected(g) => Ok(g.neighbors(idx).map(|n| g[n].id.as_str()).collect()),
        }
    }

    pub fn successors(&self, id: &str) -> Result<Vec<&str>, String> {
        let idx = self.resolve_index(id)?;
        match &self.inner {
            GraphInner::Directed(g) => Ok(g
                .neighbors_directed(idx, Direction::Outgoing)
                .map(|n| g[n].id.as_str())
                .collect()),
            // For undirected, successors == all neighbors.
            GraphInner::Undirected(g) => Ok(g.neighbors(idx).map(|n| g[n].id.as_str()).collect()),
        }
    }

    pub fn predecessors(&self, id: &str) -> Result<Vec<&str>, String> {
        let idx = self.resolve_index(id)?;
        match &self.inner {
            GraphInner::Directed(g) => Ok(g
                .neighbors_directed(idx, Direction::Incoming)
                .map(|n| g[n].id.as_str())
                .collect()),
            // For undirected, predecessors == all neighbors.
            GraphInner::Undirected(g) => Ok(g.neighbors(idx).map(|n| g[n].id.as_str()).collect()),
        }
    }

    pub fn degree(&self, id: &str) -> Result<usize, String> {
        let idx = self.resolve_index(id)?;
        match &self.inner {
            GraphInner::Directed(g) => Ok(g.neighbors_directed(idx, Direction::Outgoing).count()
                + g.neighbors_directed(idx, Direction::Incoming).count()),
            // petgraph's undirected .neighbors() returns each adjacent node once.
            GraphInner::Undirected(g) => Ok(g.neighbors(idx).count()),
        }
    }

    pub fn has_node(&self, id: &str) -> bool {
        self.id_to_index.contains_key(id)
    }

    pub fn has_edge(&self, source: &str, target: &str) -> bool {
        match (self.id_to_index.get(source), self.id_to_index.get(target)) {
            (Some(&s), Some(&t)) => with_inner!(self, g => g.find_edge(s, t).is_some()),
            _ => false,
        }
    }

    // --- Properties ---

    pub fn n_nodes(&self) -> usize {
        with_inner!(self, g => g.node_count())
    }

    pub fn n_edges(&self) -> usize {
        with_inner!(self, g => g.edge_count())
    }

    pub fn is_directed(&self) -> bool {
        self.directed
    }

    pub fn is_multi(&self) -> bool {
        self.multi
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    // --- Structural ---

    pub fn is_dag(&self) -> bool {
        match &self.inner {
            GraphInner::Directed(g) => petgraph::algo::toposort(g, None).is_ok(),
            // Undirected graphs cannot be DAGs (edges are bidirectional).
            GraphInner::Undirected(_) => false,
        }
    }

    pub fn is_connected(&self) -> bool {
        // Weakly connected: every node reachable ignoring direction.
        // Uses union-find.
        let (node_count, node_bound) = with_inner!(self, g => (g.node_count(), g.node_bound()));
        if node_count <= 1 {
            return true;
        }
        use petgraph::unionfind::UnionFind;
        let mut uf = UnionFind::new(node_bound);

        match &self.inner {
            GraphInner::Directed(g) => {
                for edge in g.edge_references() {
                    let a = g.to_index(edge.source());
                    let b = g.to_index(edge.target());
                    uf.union(a, b);
                }
                let mut root = None;
                for node in g.node_indices() {
                    let r = uf.find(g.to_index(node));
                    match root {
                        None => root = Some(r),
                        Some(prev) => {
                            if prev != r {
                                return false;
                            }
                        }
                    }
                }
            }
            GraphInner::Undirected(g) => {
                for edge in g.edge_references() {
                    let a = g.to_index(edge.source());
                    let b = g.to_index(edge.target());
                    uf.union(a, b);
                }
                let mut root = None;
                for node in g.node_indices() {
                    let r = uf.find(g.to_index(node));
                    match root {
                        None => root = Some(r),
                        Some(prev) => {
                            if prev != r {
                                return false;
                            }
                        }
                    }
                }
            }
        }
        true
    }

    pub fn is_tree(&self) -> bool {
        let (node_count, edge_count) = with_inner!(self, g => (g.node_count(), g.edge_count()));
        if node_count == 0 {
            return true;
        }
        match &self.inner {
            // Directed tree (arborescence): connected, |E| = |V| - 1, DAG,
            // and every node has at most 1 incoming edge.
            GraphInner::Directed(g) => {
                if !self.is_connected()
                    || edge_count != node_count.saturating_sub(1)
                    || !self.is_dag()
                {
                    return false;
                }
                // Arborescence: every node has at most 1 incoming edge
                for node in g.node_indices() {
                    if g.neighbors_directed(node, Direction::Incoming).count() > 1 {
                        return false;
                    }
                }
                true
            }
            // Undirected tree: connected, |E| = |V| - 1.
            GraphInner::Undirected(_) => self.is_connected() && edge_count == node_count - 1,
        }
    }

    // --- Graph transforms ---

    /// Extract a subgraph containing only the specified node IDs and edges between them.
    pub fn subgraph(&self, node_ids: &[&str]) -> Result<Graph, String> {
        let mut sub = Graph::with_name_multi(self.directed, self.multi, self.name.clone());
        let id_set: std::collections::HashSet<&str> = node_ids.iter().copied().collect();

        // Add nodes
        for &id in node_ids {
            if let Some(data) = self.node(id) {
                sub.add_node(id, data.properties.clone())?;
            } else {
                return Err(format!("Node '{}' not found", id));
            }
        }

        // Add edges where both endpoints are in the subgraph.
        // Track added pairs for undirected to avoid duplicating edges.
        let mut added: std::collections::HashSet<(String, String)> =
            std::collections::HashSet::new();
        match &self.inner {
            GraphInner::Directed(g) => {
                for edge in g.edge_references() {
                    let src = &g[edge.source()].id;
                    let tgt = &g[edge.target()].id;
                    if id_set.contains(src.as_str()) && id_set.contains(tgt.as_str()) {
                        sub.add_edge(src, tgt, edge.weight().properties.clone())
                            .ok();
                    }
                }
            }
            GraphInner::Undirected(g) => {
                for edge in g.edge_references() {
                    let src = &g[edge.source()].id;
                    let tgt = &g[edge.target()].id;
                    if id_set.contains(src.as_str()) && id_set.contains(tgt.as_str()) {
                        let key = if src <= tgt {
                            (src.clone(), tgt.clone())
                        } else {
                            (tgt.clone(), src.clone())
                        };
                        if added.insert(key) {
                            sub.add_edge(src, tgt, edge.weight().properties.clone())
                                .ok();
                        }
                    }
                }
            }
        }

        Ok(sub)
    }

    /// Extract the ego graph: all nodes within `radius` hops of `center`, plus their edges.
    pub fn ego_graph(&self, center: &str, radius: usize) -> Result<Graph, String> {
        let start = self.resolve_index(center)?;

        // BFS to find all nodes within radius.
        let mut visited = std::collections::HashMap::new();
        let mut queue = std::collections::VecDeque::new();
        visited.insert(start, 0usize);
        queue.push_back((start, 0usize));

        while let Some((node, depth)) = queue.pop_front() {
            if depth >= radius {
                continue;
            }
            match &self.inner {
                GraphInner::Directed(g) => {
                    for neighbor in g.neighbors_directed(node, Direction::Outgoing) {
                        if let std::collections::hash_map::Entry::Vacant(e) =
                            visited.entry(neighbor)
                        {
                            e.insert(depth + 1);
                            queue.push_back((neighbor, depth + 1));
                        }
                    }
                    for neighbor in g.neighbors_directed(node, Direction::Incoming) {
                        if let std::collections::hash_map::Entry::Vacant(e) =
                            visited.entry(neighbor)
                        {
                            e.insert(depth + 1);
                            queue.push_back((neighbor, depth + 1));
                        }
                    }
                }
                GraphInner::Undirected(g) => {
                    for neighbor in g.neighbors(node) {
                        if let std::collections::hash_map::Entry::Vacant(e) =
                            visited.entry(neighbor)
                        {
                            e.insert(depth + 1);
                            queue.push_back((neighbor, depth + 1));
                        }
                    }
                }
            }
        }

        let ids: Vec<&str> = visited.keys().map(|&idx| self.id_of(idx)).collect();
        self.subgraph(&ids)
    }

    /// Return a new graph with all edge directions reversed.
    pub fn reverse(&self) -> Graph {
        match &self.inner {
            GraphInner::Directed(g) => {
                let mut rev = Graph::with_name_multi(self.directed, self.multi, self.name.clone());
                for node in g.node_weights() {
                    rev.add_node(&node.id, node.properties.clone()).ok();
                }
                for edge in g.edge_references() {
                    let src = &g[edge.source()].id;
                    let tgt = &g[edge.target()].id;
                    rev.add_edge(tgt, src, edge.weight().properties.clone())
                        .ok();
                }
                rev
            }
            // Reversing an undirected graph is a no-op — return a copy.
            GraphInner::Undirected(g) => {
                let mut copy = Graph::with_name_multi(false, self.multi, self.name.clone());
                for node in g.node_weights() {
                    copy.add_node(&node.id, node.properties.clone()).ok();
                }
                let mut added: std::collections::HashSet<(String, String)> =
                    std::collections::HashSet::new();
                for edge in g.edge_references() {
                    let src = &g[edge.source()].id;
                    let tgt = &g[edge.target()].id;
                    let key = if src <= tgt {
                        (src.clone(), tgt.clone())
                    } else {
                        (tgt.clone(), src.clone())
                    };
                    if added.insert(key) {
                        copy.add_edge(src, tgt, edge.weight().properties.clone())
                            .ok();
                    }
                }
                copy
            }
        }
    }

    /// Convert to an undirected graph. Each directed edge becomes an undirected edge;
    /// when both (u,v) and (v,u) exist, the first one's properties win.
    pub fn to_undirected(&self) -> Graph {
        let mut undir = Graph::with_name_multi(false, self.multi, self.name.clone());
        match &self.inner {
            GraphInner::Directed(g) => {
                for node in g.node_weights() {
                    undir.add_node(&node.id, node.properties.clone()).ok();
                }
                let mut added: std::collections::HashSet<(String, String)> =
                    std::collections::HashSet::new();
                for edge in g.edge_references() {
                    let src = &g[edge.source()].id;
                    let tgt = &g[edge.target()].id;
                    let key = if src <= tgt {
                        (src.clone(), tgt.clone())
                    } else {
                        (tgt.clone(), src.clone())
                    };
                    if added.insert(key) {
                        undir
                            .add_edge(src, tgt, edge.weight().properties.clone())
                            .ok();
                    }
                }
            }
            // Already undirected — just copy.
            GraphInner::Undirected(g) => {
                for node in g.node_weights() {
                    undir.add_node(&node.id, node.properties.clone()).ok();
                }
                let mut added: std::collections::HashSet<(String, String)> =
                    std::collections::HashSet::new();
                for edge in g.edge_references() {
                    let src = &g[edge.source()].id;
                    let tgt = &g[edge.target()].id;
                    let key = if src <= tgt {
                        (src.clone(), tgt.clone())
                    } else {
                        (tgt.clone(), src.clone())
                    };
                    if added.insert(key) {
                        undir
                            .add_edge(src, tgt, edge.weight().properties.clone())
                            .ok();
                    }
                }
            }
        }
        undir
    }

    // --- Filtering ---

    /// Return node IDs where the property `key` equals `value`.
    pub fn nodes_filtered(&self, key: &str, value: &Value) -> Vec<String> {
        with_inner!(self, g => {
            g.node_weights()
                .filter(|n| n.properties.get(key) == Some(value))
                .map(|n| n.id.clone())
                .collect()
        })
    }

    /// Return edges where the property `key` equals `value`.
    /// Each entry is (source_id, target_id, &EdgeData).
    pub fn edges_filtered(&self, key: &str, value: &Value) -> Vec<(String, String, &EdgeData)> {
        match &self.inner {
            GraphInner::Directed(g) => g
                .edge_references()
                .filter(|e| e.weight().properties.get(key) == Some(value))
                .map(|e| {
                    let src = g[e.source()].id.clone();
                    let tgt = g[e.target()].id.clone();
                    (src, tgt, e.weight())
                })
                .collect(),
            GraphInner::Undirected(g) => g
                .edge_references()
                .filter(|e| e.weight().properties.get(key) == Some(value))
                .map(|e| {
                    let src = g[e.source()].id.clone();
                    let tgt = g[e.target()].id.clone();
                    (src, tgt, e.weight())
                })
                .collect(),
        }
    }

    // --- Internal ---

    pub fn resolve_index(&self, id: &str) -> Result<NodeIndex, String> {
        self.id_to_index
            .get(id)
            .copied()
            .ok_or_else(|| format!("Node '{}' not found", id))
    }

    pub fn id_of(&self, idx: NodeIndex) -> &str {
        with_inner!(self, g => &g[idx].id)
    }

    /// Access the underlying directed petgraph for algorithms.
    /// Panics if the graph is undirected.
    pub fn inner_directed(&self) -> &StableDiGraph<NodeData, EdgeData> {
        match &self.inner {
            GraphInner::Directed(g) => g,
            GraphInner::Undirected(_) => {
                panic!("inner_directed() called on undirected graph")
            }
        }
    }

    /// Access the underlying undirected petgraph for algorithms.
    /// Panics if the graph is directed.
    pub fn inner_undirected(&self) -> &StableUnGraph<NodeData, EdgeData> {
        match &self.inner {
            GraphInner::Undirected(g) => g,
            GraphInner::Directed(_) => {
                panic!("inner_undirected() called on directed graph")
            }
        }
    }
}

// --- JSON serialization ---
//
// A2-#14b: every JSON-serde struct denies unknown fields so attacker-supplied
// payloads cannot stash arbitrary blobs that would cost RAM/CPU to parse.

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct GraphJson {
    directed: bool,
    #[serde(default)]
    multi: bool,
    name: String,
    nodes: Vec<NodeJson>,
    edges: Vec<EdgeJson>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct NodeJson {
    id: String,
    properties: HashMap<String, Value>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct EdgeJson {
    source: String,
    target: String,
    properties: HashMap<String, Value>,
}

impl Graph {
    pub fn to_json(&self) -> Result<String, String> {
        let nodes: Vec<NodeJson> = with_inner!(self, g => g.node_weights().map(|n| NodeJson {
                id: n.id.clone(),
                properties: n.properties.clone(),
            }).collect());

        let edges: Vec<EdgeJson> = self
            .edges_vec()
            .iter()
            .map(|(src, tgt, data)| EdgeJson {
                source: src.to_string(),
                target: tgt.to_string(),
                properties: data.properties.clone(),
            })
            .collect();

        let gj = GraphJson {
            directed: self.directed,
            multi: self.multi,
            name: self.name.clone(),
            nodes,
            edges,
        };
        serde_json::to_string(&gj).map_err(|e| e.to_string())
    }

    /// Trusted-input convenience wrapper around :func:`from_json_capped` with
    /// no caps applied.
    ///
    /// **Use only with input the caller already trusts** (e.g. internal
    /// round-trip serde, fixtures, monorepo cross-module data flow). Public
    /// API consumers exposing kaos-graph over a network or MCP boundary
    /// MUST call :func:`from_json_capped` with concrete caps from
    /// ``KaosGraphSettings``. Audit follow-up #5 — bare ``from_json`` is
    /// retained for ergonomics but documented as untrusted-input-unsafe;
    /// scheduled for rename to ``from_json_unchecked`` in v0.2.
    pub fn from_json(data: &str) -> Result<Self, String> {
        Self::from_json_capped(data, usize::MAX, usize::MAX, usize::MAX)
    }

    /// Deserialize from JSON with explicit byte / node / edge caps
    /// (audit A2-#3). The PyO3 boundary always supplies caps from
    /// ``KaosGraphSettings``; pure-Rust callers can pass ``usize::MAX``.
    pub fn from_json_capped(
        data: &str,
        max_bytes: usize,
        max_nodes: usize,
        max_edges: usize,
    ) -> Result<Self, String> {
        if data.len() > max_bytes {
            return Err(format!(
                "Graph JSON is {} bytes; refusing to parse above {} bytes \
                 (raise KaosGraphSettings.max_bytes if intended).",
                data.len(),
                max_bytes
            ));
        }
        let gj: GraphJson = serde_json::from_str(data).map_err(|e| e.to_string())?;
        if gj.nodes.len() > max_nodes {
            return Err(format!(
                "Graph JSON declares {} nodes; refusing above max_nodes={} \
                 (raise KaosGraphSettings.max_nodes if intended).",
                gj.nodes.len(),
                max_nodes
            ));
        }
        if gj.edges.len() > max_edges {
            return Err(format!(
                "Graph JSON declares {} edges; refusing above max_edges={} \
                 (raise KaosGraphSettings.max_edges if intended).",
                gj.edges.len(),
                max_edges
            ));
        }
        let mut g = Self::with_name_multi(gj.directed, gj.multi, gj.name);
        for node in &gj.nodes {
            g.add_node(&node.id, node.properties.clone())?;
        }
        for edge in &gj.edges {
            g.add_edge(&edge.source, &edge.target, edge.properties.clone())?;
        }
        Ok(g)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add_remove_nodes() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        assert_eq!(g.n_nodes(), 3);

        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        assert_eq!(g.n_edges(), 2);

        g.remove_node("b").unwrap();
        assert_eq!(g.n_nodes(), 2);
        assert_eq!(g.n_edges(), 0); // edges to/from b auto-removed
        assert!(g.has_node("a"));
        assert!(!g.has_node("b"));
        assert!(g.has_node("c"));
    }

    #[test]
    fn test_properties() {
        let mut g = Graph::new(true);
        let mut props = HashMap::new();
        props.insert("name".to_string(), Value::String("Alice".to_string()));
        props.insert("age".to_string(), Value::Number(30.into()));
        g.add_node("alice", props).unwrap();

        let node = g.node("alice").unwrap();
        assert_eq!(node.properties["name"], Value::String("Alice".to_string()));
        assert_eq!(node.properties["age"], Value::Number(30.into()));
    }

    #[test]
    fn test_neighbors() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();

        let mut succs = g.successors("a").unwrap();
        succs.sort();
        assert_eq!(succs, vec!["b", "c"]);

        let preds = g.predecessors("b").unwrap();
        assert_eq!(preds, vec!["a"]);
    }

    #[test]
    fn test_json_roundtrip() {
        let mut g = Graph::new(true);
        let mut props = HashMap::new();
        props.insert("type".to_string(), Value::String("person".to_string()));
        g.add_node("alice", props).unwrap();
        g.add_node("bob", HashMap::new()).unwrap();
        let mut edge_props = HashMap::new();
        edge_props.insert("since".to_string(), Value::Number(2020.into()));
        g.add_edge("alice", "bob", edge_props).unwrap();

        let json = g.to_json().unwrap();
        let g2 = Graph::from_json(&json).unwrap();

        assert_eq!(g2.n_nodes(), 2);
        assert_eq!(g2.n_edges(), 1);
        assert_eq!(
            g2.node("alice").unwrap().properties["type"],
            Value::String("person".to_string())
        );
    }

    #[test]
    fn test_is_dag() {
        let mut dag = Graph::new(true);
        dag.add_node("a", HashMap::new()).unwrap();
        dag.add_node("b", HashMap::new()).unwrap();
        dag.add_node("c", HashMap::new()).unwrap();
        dag.add_edge("a", "b", HashMap::new()).unwrap();
        dag.add_edge("b", "c", HashMap::new()).unwrap();
        assert!(dag.is_dag());

        dag.add_edge("c", "a", HashMap::new()).unwrap();
        assert!(!dag.is_dag());
    }

    #[test]
    fn test_duplicate_node_error() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        assert!(g.add_node("a", HashMap::new()).is_err());
    }

    #[test]
    fn test_missing_node_error() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        assert!(g.add_edge("a", "missing", HashMap::new()).is_err());
    }

    #[test]
    fn test_duplicate_edge_error() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        // Adding the same edge again should fail (simple graph, not multigraph).
        let result = g.add_edge("a", "b", HashMap::new());
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("already exists"));
        // Reverse direction should still work for directed graphs.
        assert!(g.add_edge("b", "a", HashMap::new()).is_ok());
    }

    #[test]
    fn test_subgraph() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();

        let sub = g.subgraph(&["a", "c"]).unwrap();
        assert_eq!(sub.n_nodes(), 2);
        assert!(sub.has_node("a"));
        assert!(sub.has_node("c"));
        assert!(!sub.has_node("b"));
        // Only a->c edge should be present (b not in subgraph)
        assert!(sub.has_edge("a", "c"));
        assert!(!sub.has_edge("a", "b"));
    }

    #[test]
    fn test_subgraph_missing_node() {
        let g = Graph::new(true);
        assert!(g.subgraph(&["nonexistent"]).is_err());
    }

    #[test]
    fn test_ego_graph() {
        // a -> b -> c -> d (linear chain)
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();

        // Radius 1 from b: should include a (predecessor) and c (successor)
        let ego = g.ego_graph("b", 1).unwrap();
        assert!(ego.has_node("b"));
        assert!(ego.has_node("a"));
        assert!(ego.has_node("c"));
        assert!(!ego.has_node("d"));
        assert_eq!(ego.n_nodes(), 3);
    }

    #[test]
    fn test_ego_graph_radius_zero() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();

        let ego = g.ego_graph("a", 0).unwrap();
        assert_eq!(ego.n_nodes(), 1);
        assert!(ego.has_node("a"));
        assert!(!ego.has_node("b"));
    }

    #[test]
    fn test_is_connected() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        assert!(g.is_connected());

        // Add isolated node -> disconnected
        g.add_node("c", HashMap::new()).unwrap();
        assert!(!g.is_connected());
    }

    #[test]
    fn test_is_connected_empty() {
        let g = Graph::new(true);
        assert!(g.is_connected()); // 0 nodes is trivially connected
    }

    #[test]
    fn test_is_connected_single_node() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        assert!(g.is_connected()); // 1 node is trivially connected
    }

    #[test]
    fn test_is_tree() {
        // a -> b, a -> c: tree (connected, |E|=|V|-1, DAG, each node in-degree <= 1)
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();
        assert!(g.is_tree());

        // Add extra edge -> not a tree (|E| > |V|-1)
        g.add_edge("b", "c", HashMap::new()).unwrap();
        assert!(!g.is_tree());

        // Converging DAG: a->c, b->c — connected, |E|=|V|-1, DAG,
        // but c has 2 parents so it's NOT an arborescence.
        let mut g2 = Graph::new(true);
        g2.add_node("a", HashMap::new()).unwrap();
        g2.add_node("b", HashMap::new()).unwrap();
        g2.add_node("c", HashMap::new()).unwrap();
        g2.add_edge("a", "c", HashMap::new()).unwrap();
        g2.add_edge("b", "c", HashMap::new()).unwrap();
        assert!(!g2.is_tree(), "Converging DAG a->c, b->c is not a tree");
    }

    #[test]
    fn test_is_tree_empty() {
        let g = Graph::new(true);
        assert!(g.is_tree()); // empty graph is a tree
    }

    #[test]
    fn test_reverse() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();

        let rev = g.reverse();
        assert_eq!(rev.n_nodes(), 3);
        assert_eq!(rev.n_edges(), 2);
        // Original: a->b, b->c. Reversed: b->a, c->b
        assert!(rev.has_edge("b", "a"));
        assert!(rev.has_edge("c", "b"));
        assert!(!rev.has_edge("a", "b"));
        assert!(!rev.has_edge("b", "c"));
    }

    #[test]
    fn test_to_undirected() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();

        let u = g.to_undirected();
        assert!(!u.is_directed());
        assert!(u.has_node("a"));
        assert!(u.has_node("b"));
        // Undirected: both directions present
        assert!(u.has_edge("a", "b"));
        assert!(u.has_edge("b", "a"));
    }

    // =========================================================================
    // Undirected-specific tests
    // =========================================================================

    #[test]
    fn test_undirected_edge_count() {
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        assert_eq!(g.n_edges(), 1, "One undirected edge should count as 1");
    }

    #[test]
    fn test_undirected_degree() {
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        assert_eq!(g.degree("a").unwrap(), 1);
        assert_eq!(g.degree("b").unwrap(), 1);
    }

    #[test]
    fn test_undirected_remove_edge() {
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        assert_eq!(g.n_edges(), 1);
        g.remove_edge("a", "b").unwrap();
        assert_eq!(g.n_edges(), 0);
    }

    #[test]
    fn test_undirected_edges_list() {
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        let edges = g.edges_vec();
        assert_eq!(edges.len(), 1, "Undirected graph should list 1 edge, not 2");
    }

    #[test]
    fn test_undirected_properties() {
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        let mut props = HashMap::new();
        props.insert("weight".to_string(), Value::Number(42.into()));
        g.add_edge("a", "b", props).unwrap();

        let edges = g.edges_vec();
        assert_eq!(edges.len(), 1);
        assert_eq!(
            edges[0].2.properties["weight"],
            Value::Number(42.into()),
            "Undirected edge should preserve properties"
        );
    }

    #[test]
    fn test_undirected_json_roundtrip() {
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        let mut props = HashMap::new();
        props.insert("w".to_string(), Value::Number(5.into()));
        g.add_edge("a", "b", props).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();

        let json = g.to_json().unwrap();
        let g2 = Graph::from_json(&json).unwrap();

        assert!(!g2.is_directed());
        assert_eq!(g2.n_nodes(), 3);
        assert_eq!(g2.n_edges(), 2);
        assert!(g2.has_edge("a", "b"));
        assert!(g2.has_edge("b", "a")); // undirected: both directions work
        assert!(g2.has_edge("b", "c"));
        assert_eq!(
            g2.edges_vec()
                .iter()
                .find(|(s, t, _)| (*s == "a" && *t == "b") || (*s == "b" && *t == "a"))
                .unwrap()
                .2
                .properties["w"],
            Value::Number(5.into())
        );
    }

    #[test]
    fn test_undirected_subgraph() {
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();

        let sub = g.subgraph(&["a", "c"]).unwrap();
        assert_eq!(sub.n_nodes(), 2);
        assert_eq!(
            sub.n_edges(),
            1,
            "Undirected subgraph should have 1 edge, not duplicates"
        );
        assert!(sub.has_edge("a", "c"));
        assert!(sub.has_edge("c", "a")); // undirected both directions
    }

    #[test]
    fn test_undirected_is_tree() {
        // a -- b -- c: tree (connected, |E| = |V| - 1)
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        assert!(g.is_tree());

        // Add cycle edge -> not a tree
        g.add_edge("a", "c", HashMap::new()).unwrap();
        assert!(!g.is_tree());
    }

    #[test]
    fn test_undirected_is_dag_always_false() {
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        assert!(!g.is_dag(), "Undirected graphs are never DAGs");
    }

    #[test]
    fn test_undirected_has_edge_both_directions() {
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        assert!(g.has_edge("a", "b"));
        assert!(g.has_edge("b", "a")); // undirected: lookup in both directions
    }

    #[test]
    fn test_undirected_neighbors() {
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("a", "c", HashMap::new()).unwrap();

        let mut nbrs = g.neighbors("b").unwrap();
        nbrs.sort();
        assert_eq!(nbrs, vec!["a"], "b's only neighbor is a");

        let mut nbrs_a = g.neighbors("a").unwrap();
        nbrs_a.sort();
        assert_eq!(nbrs_a, vec!["b", "c"]);
    }

    #[test]
    fn test_undirected_ego_graph() {
        // a -- b -- c -- d
        let mut g = Graph::new(false);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();
        g.add_node("d", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("b", "c", HashMap::new()).unwrap();
        g.add_edge("c", "d", HashMap::new()).unwrap();

        let ego = g.ego_graph("b", 1).unwrap();
        assert!(ego.has_node("a"));
        assert!(ego.has_node("b"));
        assert!(ego.has_node("c"));
        assert!(!ego.has_node("d"));
        assert_eq!(ego.n_nodes(), 3);
    }

    // =========================================================================
    // Property filtering tests
    // =========================================================================

    #[test]
    fn test_nodes_filtered() {
        let mut g = Graph::new(true);
        let mut props = HashMap::new();
        props.insert("type".to_string(), Value::String("person".to_string()));
        g.add_node("alice", props).unwrap();

        let mut props2 = HashMap::new();
        props2.insert("type".to_string(), Value::String("org".to_string()));
        g.add_node("acme", props2).unwrap();

        let mut props3 = HashMap::new();
        props3.insert("type".to_string(), Value::String("person".to_string()));
        g.add_node("bob", props3).unwrap();

        let persons = g.nodes_filtered("type", &Value::String("person".to_string()));
        assert_eq!(persons.len(), 2);
        assert!(persons.contains(&"alice".to_string()));
        assert!(persons.contains(&"bob".to_string()));

        let orgs = g.nodes_filtered("type", &Value::String("org".to_string()));
        assert_eq!(orgs.len(), 1);
        assert_eq!(orgs[0], "acme");

        let empty = g.nodes_filtered("type", &Value::String("bot".to_string()));
        assert!(empty.is_empty());
    }

    #[test]
    fn test_edges_filtered() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_node("c", HashMap::new()).unwrap();

        let mut props = HashMap::new();
        props.insert("rel".to_string(), Value::String("friend".to_string()));
        g.add_edge("a", "b", props).unwrap();

        let mut props2 = HashMap::new();
        props2.insert("rel".to_string(), Value::String("colleague".to_string()));
        g.add_edge("b", "c", props2).unwrap();

        let friends = g.edges_filtered("rel", &Value::String("friend".to_string()));
        assert_eq!(friends.len(), 1);
        assert_eq!(friends[0].0, "a");
        assert_eq!(friends[0].1, "b");

        let empty = g.edges_filtered("rel", &Value::String("enemy".to_string()));
        assert!(empty.is_empty());
    }

    #[test]
    fn test_nodes_filtered_missing_key() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        let result = g.nodes_filtered("nonexistent", &Value::String("val".to_string()));
        assert!(result.is_empty());
    }

    // =========================================================================
    // Multi-graph tests
    // =========================================================================

    #[test]
    fn test_multi_allows_parallel_edges() {
        let mut g = Graph::new_multi(true, true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap(); // should succeed
        assert_eq!(g.n_edges(), 2);
    }

    #[test]
    fn test_simple_rejects_parallel_edges() {
        let mut g = Graph::new(true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        assert!(g.add_edge("a", "b", HashMap::new()).is_err());
    }

    #[test]
    fn test_multi_flag_defaults_false() {
        let g = Graph::new(true);
        assert!(!g.is_multi());
    }

    #[test]
    fn test_multi_flag_true() {
        let g = Graph::new_multi(true, true);
        assert!(g.is_multi());
    }

    #[test]
    fn test_multi_json_roundtrip() {
        let mut g = Graph::new_multi(true, true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();

        let json = g.to_json().unwrap();
        let g2 = Graph::from_json(&json).unwrap();
        assert!(g2.is_multi());
        assert_eq!(g2.n_edges(), 2);
    }

    #[test]
    fn test_multi_undirected() {
        let mut g = Graph::new_multi(false, true);
        g.add_node("a", HashMap::new()).unwrap();
        g.add_node("b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        g.add_edge("a", "b", HashMap::new()).unwrap();
        assert_eq!(g.n_edges(), 2);
        assert!(!g.is_directed());
        assert!(g.is_multi());
    }
}
