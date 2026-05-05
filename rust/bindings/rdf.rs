//! PyO3 bindings for RDF/OWL loading.

use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::graph::PyGraph;
use crate::core::rdf;

/// Load an RDF file (OWL/TTL/RDF-XML/N-Triples) into a Graph.
///
/// Format is auto-detected from the file extension; unknown extensions are
/// REFUSED rather than silently fallbacking to RDF/XML (audit A2-#5). Caps
/// are mandatory at the FFI boundary (audit A2-#3).
#[pyfunction]
#[pyo3(signature = (path, max_bytes, triple_cap))]
fn load_rdf_file(
    py: Python<'_>,
    path: &str,
    max_bytes: u64,
    triple_cap: usize,
) -> PyResult<(PyGraph, Py<PyDict>)> {
    let (graph, stats) = rdf::load_rdf_file_capped(path, max_bytes, triple_cap)
        .map_err(pyo3::exceptions::PyValueError::new_err)?;
    let dict = PyDict::new(py);
    dict.set_item("total_triples", stats.total_triples)?;
    dict.set_item("nodes", stats.nodes)?;
    dict.set_item("edges", stats.edges)?;
    dict.set_item("literal_properties", stats.literal_properties)?;
    dict.set_item("load_time_ms", stats.load_time_ms as u64)?;
    Ok((PyGraph { inner: graph }, dict.into()))
}

/// Load RDF from a string with an explicit format and caps.
///
/// Supported format strings: "turtle"/"ttl", "ntriples"/"nt",
/// "rdfxml"/"xml"/"owl", "nquads"/"nq", "trig". Caps are mandatory at the
/// FFI boundary (audit A2-#3, A2-#5).
#[pyfunction]
#[pyo3(signature = (data, format, max_bytes, triple_cap))]
fn load_rdf_string(
    py: Python<'_>,
    data: &str,
    format: &str,
    max_bytes: usize,
    triple_cap: usize,
) -> PyResult<(PyGraph, Py<PyDict>)> {
    let fmt = match format {
        "turtle" | "ttl" => oxrdfio::RdfFormat::Turtle,
        "ntriples" | "nt" => oxrdfio::RdfFormat::NTriples,
        "rdfxml" | "xml" | "owl" => oxrdfio::RdfFormat::RdfXml,
        "nquads" | "nq" => oxrdfio::RdfFormat::NQuads,
        "trig" => oxrdfio::RdfFormat::TriG,
        _ => {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Unknown RDF format: '{}'. Supported: turtle, ttl, ntriples, nt, rdfxml, xml, owl, nquads, nq, trig",
                format
            )))
        }
    };
    let (graph, stats) = rdf::load_rdf_string_capped(data, fmt, max_bytes, triple_cap)
        .map_err(pyo3::exceptions::PyValueError::new_err)?;
    let dict = PyDict::new(py);
    dict.set_item("total_triples", stats.total_triples)?;
    dict.set_item("nodes", stats.nodes)?;
    dict.set_item("edges", stats.edges)?;
    dict.set_item("literal_properties", stats.literal_properties)?;
    dict.set_item("load_time_ms", stats.load_time_ms as u64)?;
    Ok((PyGraph { inner: graph }, dict.into()))
}

/// Export a Graph to Turtle format string.
#[pyfunction]
fn export_turtle(graph: &PyGraph) -> PyResult<String> {
    rdf::export_turtle(&graph.inner).map_err(pyo3::exceptions::PyValueError::new_err)
}

/// Export a Graph to N-Triples format string.
#[pyfunction]
fn export_ntriples(graph: &PyGraph) -> PyResult<String> {
    rdf::export_ntriples(&graph.inner).map_err(pyo3::exceptions::PyValueError::new_err)
}

/// Export a Graph to JSON-LD format string.
#[pyfunction]
fn export_jsonld(graph: &PyGraph) -> PyResult<String> {
    rdf::export_jsonld(&graph.inner).map_err(pyo3::exceptions::PyValueError::new_err)
}

/// Register the rdf submodule.
pub fn register_module(parent: &Bound<'_, PyModule>) -> PyResult<()> {
    let m = PyModule::new(parent.py(), "rdf")?;
    m.add_function(wrap_pyfunction!(load_rdf_file, &m)?)?;
    m.add_function(wrap_pyfunction!(load_rdf_string, &m)?)?;
    m.add_function(wrap_pyfunction!(export_turtle, &m)?)?;
    m.add_function(wrap_pyfunction!(export_ntriples, &m)?)?;
    m.add_function(wrap_pyfunction!(export_jsonld, &m)?)?;

    parent.add_submodule(&m)?;
    parent
        .py()
        .import("sys")?
        .getattr("modules")?
        .set_item("kaos_graph._rust.rdf", &m)?;

    Ok(())
}
