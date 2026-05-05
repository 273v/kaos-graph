//! kaos-graph: High-performance graph library for the Kelvin Agentic OS.
//!
//! Backed by petgraph's StableDiGraph with string-keyed nodes,
//! property-bearing edges, and built-in graph algorithms.

#![allow(dead_code)]

#[cfg(feature = "pyo3")]
mod bindings;
pub mod core;

#[cfg(feature = "pyo3")]
use pyo3::prelude::*;

/// The root Python module `kaos_graph._rust`.
#[cfg(feature = "pyo3")]
#[pymodule]
#[pyo3(name = "_rust")]
fn kaos_graph_rust(py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;

    bindings::graph::register_module(m)?;
    bindings::algorithms::register_module(m)?;
    bindings::knowledge::register_module(m)?;
    bindings::rdf::register_module(m)?;

    // Set __path__ so Python treats this as a package.
    m.setattr("__path__", pyo3::types::PyList::empty(py))?;
    m.setattr("__package__", "kaos_graph._rust")?;

    Ok(())
}
