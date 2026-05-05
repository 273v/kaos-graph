"""kaos-graph: High-performance graph library for the Kelvin Agentic OS."""

from kaos_graph.graph import Graph
from kaos_graph.types import BfsNode, DfsEvent, Edge, Node, Triple

# ``__version__`` matches what ``pip show kaos-graph`` reports — the PEP 440
# wheel-metadata version. The Rust crate's CARGO_PKG_VERSION is in Cargo
# SemVer form (e.g. "0.1.0-alpha.1"), which maturin normalizes to PEP 440
# ("0.1.0a1") at wheel-build time. Reading via importlib.metadata keeps the
# Python-visible string aligned with PyPI.
try:
    from importlib.metadata import version as _v

    __version__ = _v("kaos-graph")
    del _v
except Exception:  # pragma: no cover — only when not installed as a package
    from kaos_graph._rust import __version__

__all__ = [
    "BfsNode",
    "DfsEvent",
    "Edge",
    "Graph",
    "Node",
    "Triple",
    "__version__",
]
