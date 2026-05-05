//! PyO3 bindings for the Graph type.

use std::collections::HashMap;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use serde_json::Value;

use crate::core::graph::Graph;

/// Convert a serde_json::Value to a Python object.
fn value_to_py(py: Python<'_>, v: &Value) -> PyResult<Py<pyo3::PyAny>> {
    match v {
        Value::Null => Ok(py.None()),
        Value::Bool(b) => Ok(b.into_pyobject(py)?.to_owned().into_any().unbind()),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i.into_pyobject(py)?.into_any().unbind())
            } else if let Some(f) = n.as_f64() {
                Ok(f.into_pyobject(py)?.into_any().unbind())
            } else {
                Ok(py.None())
            }
        }
        Value::String(s) => Ok(s.into_pyobject(py)?.into_any().unbind()),
        Value::Array(arr) => {
            let list = PyList::empty(py);
            for item in arr {
                list.append(value_to_py(py, item)?)?;
            }
            Ok(list.into_pyobject(py)?.into_any().unbind())
        }
        Value::Object(map) => {
            let dict = PyDict::new(py);
            for (k, val) in map {
                dict.set_item(k, value_to_py(py, val)?)?;
            }
            Ok(dict.into_pyobject(py)?.into_any().unbind())
        }
    }
}

/// Convert a Python object to serde_json::Value.
fn py_to_value(obj: &Bound<'_, pyo3::PyAny>) -> PyResult<Value> {
    if obj.is_none() {
        Ok(Value::Null)
    } else if let Ok(b) = obj.extract::<bool>() {
        Ok(Value::Bool(b))
    } else if let Ok(i) = obj.extract::<i64>() {
        Ok(Value::Number(i.into()))
    } else if let Ok(f) = obj.extract::<f64>() {
        Ok(serde_json::Number::from_f64(f)
            .map(Value::Number)
            .unwrap_or(Value::Null))
    } else if let Ok(s) = obj.extract::<String>() {
        Ok(Value::String(s))
    } else if let Ok(list) = obj.cast::<PyList>() {
        let arr: Result<Vec<Value>, _> = list.iter().map(|item| py_to_value(&item)).collect();
        Ok(Value::Array(arr?))
    } else if let Ok(dict) = obj.cast::<PyDict>() {
        let mut map = serde_json::Map::new();
        for (k, v) in dict.iter() {
            let key: String = k.extract()?;
            map.insert(key, py_to_value(&v)?);
        }
        Ok(Value::Object(map))
    } else {
        // Fallback: convert to string
        let s = obj.str()?.to_string();
        Ok(Value::String(s))
    }
}

/// Convert a Python dict to HashMap<String, Value>.
fn pydict_to_props(dict: Option<&Bound<'_, PyDict>>) -> PyResult<HashMap<String, Value>> {
    match dict {
        None => Ok(HashMap::new()),
        Some(d) => {
            let mut map = HashMap::new();
            for (k, v) in d.iter() {
                let key: String = k.extract()?;
                map.insert(key, py_to_value(&v)?);
            }
            Ok(map)
        }
    }
}

/// Convert HashMap<String, Value> to a Python dict.
fn props_to_pydict(py: Python<'_>, props: &HashMap<String, Value>) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new(py);
    for (k, v) in props {
        dict.set_item(k, value_to_py(py, v)?)?;
    }
    Ok(dict.into())
}

/// A property graph backed by petgraph's StableDiGraph.
///
/// Nodes have string IDs and arbitrary JSON-compatible properties.
/// Edges have arbitrary JSON-compatible properties.
///
/// Args:
///     directed: Whether the graph is directed (default True).
///     name: Optional name for the graph.
#[pyclass(name = "PyGraph", module = "kaos_graph._rust.graph")]
pub struct PyGraph {
    pub(crate) inner: Graph,
}

#[pymethods]
impl PyGraph {
    #[new]
    #[pyo3(signature = (directed=true, name=None, multi=false))]
    fn new(directed: bool, name: Option<String>, multi: bool) -> Self {
        let graph = match name {
            Some(n) => Graph::with_name_multi(directed, multi, n),
            None => Graph::new_multi(directed, multi),
        };
        Self { inner: graph }
    }

    // --- Mutation ---

    /// Add a node with the given ID and optional properties dict.
    #[pyo3(signature = (id, properties=None))]
    fn add_node(&mut self, id: &str, properties: Option<&Bound<'_, PyDict>>) -> PyResult<()> {
        let props = pydict_to_props(properties)?;
        self.inner
            .add_node(id, props)
            .map_err(pyo3::exceptions::PyValueError::new_err)
    }

    /// Add an edge from source to target with optional properties dict.
    #[pyo3(signature = (source, target, properties=None))]
    fn add_edge(
        &mut self,
        source: &str,
        target: &str,
        properties: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let props = pydict_to_props(properties)?;
        self.inner
            .add_edge(source, target, props)
            .map(|_| ())
            .map_err(pyo3::exceptions::PyValueError::new_err)
    }

    /// Remove a node and all its incident edges. Returns the node's properties.
    fn remove_node(&mut self, py: Python<'_>, id: &str) -> PyResult<Py<PyDict>> {
        let data = self
            .inner
            .remove_node(id)
            .map_err(pyo3::exceptions::PyKeyError::new_err)?;
        props_to_pydict(py, &data.properties)
    }

    /// Remove an edge from source to target.
    fn remove_edge(&mut self, source: &str, target: &str) -> PyResult<()> {
        self.inner
            .remove_edge(source, target)
            .map_err(pyo3::exceptions::PyKeyError::new_err)
    }

    /// Merge properties into an existing node. Existing properties are
    /// preserved unless overwritten by the new values.
    #[pyo3(signature = (id, properties=None))]
    fn update_node(&mut self, id: &str, properties: Option<&Bound<'_, PyDict>>) -> PyResult<()> {
        let props = pydict_to_props(properties)?;
        self.inner
            .update_node(id, props)
            .map_err(pyo3::exceptions::PyKeyError::new_err)
    }

    /// Set a single property on an existing node.
    fn set_node_property(&mut self, id: &str, key: &str, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let val = py_to_value(value)?;
        self.inner
            .set_node_property(id, key, val)
            .map_err(pyo3::exceptions::PyKeyError::new_err)
    }

    // --- Query ---

    /// Get a node's properties dict, or None if not found.
    fn node(&self, py: Python<'_>, id: &str) -> PyResult<Option<Py<PyDict>>> {
        match self.inner.node(id) {
            Some(data) => Ok(Some(props_to_pydict(py, &data.properties)?)),
            None => Ok(None),
        }
    }

    /// List all node IDs.
    fn node_ids(&self) -> Vec<String> {
        self.inner
            .node_ids()
            .into_iter()
            .map(|s| s.to_string())
            .collect()
    }

    /// List all edges as (source, target, properties) tuples.
    fn edges(&self, py: Python<'_>) -> PyResult<Vec<(String, String, Py<PyDict>)>> {
        let mut result = Vec::new();
        for (src, tgt, data) in self.inner.edges_vec() {
            let props = props_to_pydict(py, &data.properties)?;
            result.push((src.to_string(), tgt.to_string(), props));
        }
        Ok(result)
    }

    /// Get successors (outgoing neighbors) of a node.
    fn successors(&self, id: &str) -> PyResult<Vec<String>> {
        self.inner
            .successors(id)
            .map(|v| v.into_iter().map(|s| s.to_string()).collect())
            .map_err(pyo3::exceptions::PyKeyError::new_err)
    }

    /// Get predecessors (incoming neighbors) of a node.
    fn predecessors(&self, id: &str) -> PyResult<Vec<String>> {
        self.inner
            .predecessors(id)
            .map(|v| v.into_iter().map(|s| s.to_string()).collect())
            .map_err(pyo3::exceptions::PyKeyError::new_err)
    }

    /// Get all neighbors (both directions) of a node.
    fn neighbors(&self, id: &str) -> PyResult<Vec<String>> {
        self.inner
            .neighbors(id)
            .map(|v| v.into_iter().map(|s| s.to_string()).collect())
            .map_err(pyo3::exceptions::PyKeyError::new_err)
    }

    /// Degree of a node (in + out for directed).
    fn degree(&self, id: &str) -> PyResult<usize> {
        self.inner
            .degree(id)
            .map_err(pyo3::exceptions::PyKeyError::new_err)
    }

    /// Check if a node exists.
    fn has_node(&self, id: &str) -> bool {
        self.inner.has_node(id)
    }

    /// Check if an edge exists.
    fn has_edge(&self, source: &str, target: &str) -> bool {
        self.inner.has_edge(source, target)
    }

    // --- Properties ---

    /// Number of nodes.
    #[getter]
    fn n_nodes(&self) -> usize {
        self.inner.n_nodes()
    }

    /// Number of edges.
    #[getter]
    fn n_edges(&self) -> usize {
        self.inner.n_edges()
    }

    /// Whether the graph is directed.
    #[getter]
    fn is_directed(&self) -> bool {
        self.inner.is_directed()
    }

    /// Whether the graph allows parallel edges (multi-graph).
    #[getter]
    fn is_multi(&self) -> bool {
        self.inner.is_multi()
    }

    /// Graph name.
    #[getter]
    fn name(&self) -> &str {
        self.inner.name()
    }

    /// Whether the graph is a DAG (no cycles).
    fn is_dag(&self) -> bool {
        self.inner.is_dag()
    }

    // --- Serialization ---

    /// Serialize to JSON string.
    fn to_json(&self) -> PyResult<String> {
        self.inner
            .to_json()
            .map_err(pyo3::exceptions::PyValueError::new_err)
    }

    /// Deserialize from JSON string with explicit caps (audit A2-#3).
    ///
    /// All four cap arguments are required at the FFI boundary; Python
    /// wrappers in :mod:`kaos_graph.graph` resolve them from
    /// :class:`KaosGraphSettings` before calling.
    #[staticmethod]
    #[pyo3(signature = (data, max_bytes, max_nodes, max_edges))]
    fn from_json(
        data: &str,
        max_bytes: usize,
        max_nodes: usize,
        max_edges: usize,
    ) -> PyResult<Self> {
        Graph::from_json_capped(data, max_bytes, max_nodes, max_edges)
            .map(|g| Self { inner: g })
            .map_err(pyo3::exceptions::PyValueError::new_err)
    }

    // --- Pickle ---
    //
    // Format: 4-byte magic "KGR1" || JSON bytes.
    // - "KGR" = kaos-graph
    // - "1"   = state-format version, bumped when the serde shape changes
    //
    // A 64 MiB hard cap inside __setstate__ prevents an attacker-controlled
    // pickle from ballooning peak memory (audit A2-#4). The cap matches
    // KaosGraphSettings.max_pickle_bytes default; bypassing the FFI surface
    // requires explicit code, by design.

    fn __getstate__(&self) -> PyResult<Vec<u8>> {
        let json = self
            .inner
            .to_json()
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
        let json_bytes = json.into_bytes();
        let mut out = Vec::with_capacity(4 + json_bytes.len());
        out.extend_from_slice(b"KGR1");
        out.extend_from_slice(&json_bytes);
        Ok(out)
    }

    fn __setstate__(&mut self, state: Vec<u8>) -> PyResult<()> {
        const MAX_PICKLE_BYTES: usize = 64 * 1024 * 1024;
        if state.len() > MAX_PICKLE_BYTES {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "kaos-graph pickle payload is {} bytes; refusing to deserialize \
                 above {} bytes (audit A2-#4). Set state on a smaller graph or \
                 deserialize from a trusted source through Graph.from_json().",
                state.len(),
                MAX_PICKLE_BYTES
            )));
        }
        if state.len() < 4 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "kaos-graph pickle payload too short to contain magic header.",
            ));
        }
        let (magic, json_bytes) = state.split_at(4);
        if magic != b"KGR1" {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "kaos-graph pickle magic mismatch: expected b'KGR1', got {:?}. \
                 Pickled state from a different kaos-graph release or format.",
                magic
            )));
        }
        let json = std::str::from_utf8(json_bytes).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!(
                "kaos-graph pickle payload after magic header is not UTF-8: {}",
                e
            ))
        })?;
        let g = Graph::from_json(json).map_err(pyo3::exceptions::PyValueError::new_err)?;
        self.inner = g;
        Ok(())
    }

    fn __repr__(&self) -> String {
        format!(
            "PyGraph(nodes={}, edges={}, directed={})",
            self.inner.n_nodes(),
            self.inner.n_edges(),
            self.inner.is_directed()
        )
    }

    fn __len__(&self) -> usize {
        self.inner.n_nodes()
    }

    fn __contains__(&self, id: &str) -> bool {
        self.inner.has_node(id)
    }

    // --- Filtering ---

    /// Return node IDs where the property `key` equals `value`.
    fn nodes_filtered(&self, key: &str, value: &Bound<'_, pyo3::PyAny>) -> PyResult<Vec<String>> {
        let val = py_to_value(value)?;
        Ok(self.inner.nodes_filtered(key, &val))
    }

    /// Return edges where the property `key` equals `value`.
    /// Each entry is (source, target, properties_dict).
    fn edges_filtered(
        &self,
        py: Python<'_>,
        key: &str,
        value: &Bound<'_, pyo3::PyAny>,
    ) -> PyResult<Vec<(String, String, Py<PyDict>)>> {
        let val = py_to_value(value)?;
        let edges = self.inner.edges_filtered(key, &val);
        let mut result = Vec::new();
        for (src, tgt, data) in edges {
            let props = props_to_pydict(py, &data.properties)?;
            result.push((src, tgt, props));
        }
        Ok(result)
    }

    // --- Graph transforms ---

    /// Extract a subgraph containing only the specified node IDs and edges between them.
    fn subgraph(&self, node_ids: Vec<String>) -> PyResult<PyGraph> {
        let ids_as_refs: Vec<&str> = node_ids.iter().map(|s| s.as_str()).collect();
        self.inner
            .subgraph(&ids_as_refs)
            .map(|g| PyGraph { inner: g })
            .map_err(pyo3::exceptions::PyValueError::new_err)
    }

    /// Extract the ego graph: all nodes within `radius` hops of `center`, plus their edges.
    fn ego_graph(&self, center: &str, radius: usize) -> PyResult<PyGraph> {
        self.inner
            .ego_graph(center, radius)
            .map(|g| PyGraph { inner: g })
            .map_err(pyo3::exceptions::PyValueError::new_err)
    }

    /// Whether the graph is (weakly) connected.
    fn is_connected(&self) -> bool {
        self.inner.is_connected()
    }

    /// Whether the graph is a tree (connected, |E| = |V| - 1, acyclic).
    fn is_tree(&self) -> bool {
        self.inner.is_tree()
    }

    /// Return a new graph with all edge directions reversed.
    fn reverse(&self) -> PyGraph {
        PyGraph {
            inner: self.inner.reverse(),
        }
    }

    /// Convert to an undirected graph (add reverse edges where missing).
    fn to_undirected(&self) -> PyGraph {
        PyGraph {
            inner: self.inner.to_undirected(),
        }
    }
}

/// Register the graph submodule.
pub fn register_module(parent: &Bound<'_, PyModule>) -> PyResult<()> {
    let m = PyModule::new(parent.py(), "graph")?;
    m.add_class::<PyGraph>()?;

    parent.add_submodule(&m)?;
    parent
        .py()
        .import("sys")?
        .getattr("modules")?
        .set_item("kaos_graph._rust.graph", &m)?;

    Ok(())
}
