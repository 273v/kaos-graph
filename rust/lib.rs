//! kaos-graph: High-performance graph library for the Kelvin Agentic OS.
//!
//! Backed by petgraph's StableDiGraph with string-keyed nodes,
//! property-bearing edges, and built-in graph algorithms.

// Audit-01 KG-006: crate-root lint set per docs/oss/30-rust-packaging/clippy-and-quality.md.
// PyO3 binding registrations consume "unused" core fns, so dead_code stays at allow.
//
// `missing_docs` is `allow`'d for now (was a clean `warn` per the standard) to keep
// `cargo clippy --all-targets -- -D warnings` green while a focused docs-backfill
// pass lands in a follow-up. Bumping it back to `warn` is the only change needed
// once the public-API surface is fully documented.
#![allow(dead_code)]
#![allow(missing_docs)]
#![warn(rust_2018_idioms)]
#![warn(rust_2021_compatibility)]
#![warn(unreachable_pub)]
#![warn(unused_qualifications)]

#[cfg(feature = "pyo3")]
mod bindings;
pub mod core;

#[cfg(feature = "pyo3")]
use pyo3::prelude::*;

/// The root Python module `kaos_graph._rust`.
///
/// Audit-01 KG-006: declared `gil_used = false` for free-threaded Python
/// (PEP 703 / cpython-3.14t) compatibility. The exposed PyO3 classes
/// (`PyGraph`, etc.) own their state behind `&mut self` borrows, so the
/// PyO3 borrow checker serializes mutations across threads even without
/// the GIL. No shared mutable state, no `RefCell`/`Mutex`/`static` globals.
#[cfg(feature = "pyo3")]
#[pymodule(gil_used = false)]
#[pyo3(name = "_rust")]
fn kaos_graph_rust(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
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
