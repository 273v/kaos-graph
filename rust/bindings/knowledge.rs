//! PyO3 bindings for knowledge graph operations.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde_json::Value;

use super::graph::PyGraph;
use crate::core::knowledge;

/// Helper: convert a Python value to serde_json::Value (simplified).
fn py_to_json_value(obj: &Bound<'_, pyo3::PyAny>) -> PyResult<Value> {
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
    } else {
        let s = obj.str()?.to_string();
        Ok(Value::String(s))
    }
}

/// Merge two graphs with a configurable conflict strategy.
///
/// Strategies: "keep_first", "keep_latest" (default), "merge".
#[pyfunction]
#[pyo3(signature = (base, other, conflict="keep_latest"))]
fn merge_graphs(base: &PyGraph, other: &PyGraph, conflict: &str) -> PyGraph {
    PyGraph {
        inner: knowledge::merge_graphs(&base.inner, &other.inner, conflict),
    }
}

/// Add transitive closure edges for a specific relationship type.
///
/// If A->B and B->C both have the given predicate, add A->C.
#[pyfunction]
fn densify(graph: &PyGraph, predicate: &str) -> PyGraph {
    PyGraph {
        inner: knowledge::densify(&graph.inner, predicate),
    }
}

/// Extract subgraph containing nodes whose "type" property matches any value in the list.
#[pyfunction]
fn extract_subgraph_by_types(graph: &PyGraph, types: Vec<String>) -> PyGraph {
    PyGraph {
        inner: knowledge::extract_subgraph_by_types(&graph.inner, &types),
    }
}

/// Diff two graphs. Returns a dict with keys:
/// added_nodes, removed_nodes, added_edges, removed_edges, changed_node_properties.
#[pyfunction]
fn diff_graphs(py: Python<'_>, old: &PyGraph, new: &PyGraph) -> PyResult<Py<PyDict>> {
    let diff = knowledge::diff_graphs(&old.inner, &new.inner);
    let dict = PyDict::new(py);
    dict.set_item("added_nodes", diff.added_nodes)?;
    dict.set_item("removed_nodes", diff.removed_nodes)?;
    dict.set_item("added_edges", diff.added_edges)?;
    dict.set_item("removed_edges", diff.removed_edges)?;
    dict.set_item("changed_node_properties", diff.changed_node_properties)?;
    Ok(dict.into())
}

/// Extract subgraph by filtering nodes on a property value.
#[pyfunction]
fn extract_subgraph_by_property(
    graph: &PyGraph,
    key: &str,
    value: &Bound<'_, pyo3::PyAny>,
) -> PyResult<PyGraph> {
    let val = py_to_json_value(value)?;
    Ok(PyGraph {
        inner: knowledge::extract_subgraph_by_property(&graph.inner, key, &val),
    })
}

/// Project graph edges as (subject, predicate, object) triples.
#[pyfunction]
fn project_triples(graph: &PyGraph) -> Vec<(String, String, String)> {
    knowledge::project_triples(&graph.inner)
}

/// Build a graph from (subject, predicate, object) triples.
#[pyfunction]
#[pyo3(signature = (triples, directed=true))]
fn from_triples(triples: Vec<(String, String, String)>, directed: bool) -> PyGraph {
    PyGraph {
        inner: knowledge::from_triples(&triples, directed),
    }
}

/// Infer transitive types via a specific predicate (e.g., "subClassOf").
#[pyfunction]
fn infer_types(graph: &PyGraph, predicate_iri: &str) -> PyGraph {
    PyGraph {
        inner: knowledge::infer_types(&graph.inner, predicate_iri),
    }
}

/// Find orphan nodes (degree 0).
#[pyfunction]
fn find_orphan_nodes(graph: &PyGraph) -> Vec<String> {
    knowledge::find_orphan_nodes(&graph.inner)
}

/// Find hub nodes (degree > threshold).
#[pyfunction]
fn find_hub_nodes(graph: &PyGraph, threshold: usize) -> Vec<String> {
    knowledge::find_hub_nodes(&graph.inner, threshold)
}

/// Degree distribution: returns dict of {degree: count}.
#[pyfunction]
fn degree_distribution(py: Python<'_>, graph: &PyGraph) -> PyResult<Py<PyDict>> {
    let dist = knowledge::degree_distribution(&graph.inner);
    let dict = PyDict::new(py);
    for (deg, count) in &dist {
        dict.set_item(deg, count)?;
    }
    Ok(dict.into())
}

/// Register the knowledge submodule.
pub fn register_module(parent: &Bound<'_, PyModule>) -> PyResult<()> {
    let m = PyModule::new(parent.py(), "knowledge")?;

    m.add_function(wrap_pyfunction!(merge_graphs, &m)?)?;
    m.add_function(wrap_pyfunction!(diff_graphs, &m)?)?;
    m.add_function(wrap_pyfunction!(extract_subgraph_by_property, &m)?)?;
    m.add_function(wrap_pyfunction!(extract_subgraph_by_types, &m)?)?;
    m.add_function(wrap_pyfunction!(project_triples, &m)?)?;
    m.add_function(wrap_pyfunction!(from_triples, &m)?)?;
    m.add_function(wrap_pyfunction!(infer_types, &m)?)?;
    m.add_function(wrap_pyfunction!(densify, &m)?)?;
    m.add_function(wrap_pyfunction!(find_orphan_nodes, &m)?)?;
    m.add_function(wrap_pyfunction!(find_hub_nodes, &m)?)?;
    m.add_function(wrap_pyfunction!(degree_distribution, &m)?)?;

    parent.add_submodule(&m)?;
    parent
        .py()
        .import("sys")?
        .getattr("modules")?
        .set_item("kaos_graph._rust.knowledge", &m)?;

    Ok(())
}
