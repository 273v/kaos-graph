"""RDF/OWL loading -- typed Python wrappers over the Rust RDF parser.

The wrappers thread ``KaosGraphSettings`` caps + allowlist root through to
Rust on every call (audit A2-#1, #3, #5). Standalone callers without
``kaos-core`` installed get conservative built-in defaults; MCP / runtime
callers pass a context whose ``KaosGraphSettings`` overrides.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kaos_graph._rust import rdf as _raw
from kaos_graph.errors import PathTraversalError
from kaos_graph.graph import Graph

# Defaults for callers that do not supply a settings instance. Conservative
# but generous enough that legitimate inline parsing isn't gated.
_DEFAULT_MAX_BYTES = 64 * 1024 * 1024  # 64 MiB
_DEFAULT_MAX_TRIPLES = 10_000_000


def _resolve_caps(
    settings: Any,
) -> tuple[int, int, str | None]:
    """Pull (max_bytes, max_triples, allowed_root) from a settings-like object.

    ``settings`` is duck-typed: anything with ``.max_bytes``, ``.max_triples``,
    ``.allowed_root`` works. ``None`` returns defaults.
    """
    if settings is None:
        return (_DEFAULT_MAX_BYTES, _DEFAULT_MAX_TRIPLES, None)
    return (
        int(getattr(settings, "max_bytes", _DEFAULT_MAX_BYTES)),
        int(getattr(settings, "max_triples", _DEFAULT_MAX_TRIPLES)),
        getattr(settings, "allowed_root", None),
    )


def _check_allowlist(path: str, allowed_root: str | None) -> Path:
    """Resolve ``path`` and (if configured) confirm it lives under ``allowed_root``.

    A2-#1 closes the path-traversal vector at the **MCP tool** boundary
    (``kaos-graph-load-rdf``), which always supplies a settings instance with
    ``allowed_root`` set. In-process Python callers using the library
    directly already have ``open()`` capability and are trusted; passing
    ``allowed_root=None`` skips the gate.

    **TOCTOU caveat (audit follow-up #4):** ``resolve(strict=True)`` is the
    POSIX standard "follow all symlinks once and verify the destination
    exists" check. Between this check and the subsequent open in
    :func:`_load_file` (or Rust ``load_rdf_file_capped``), a sufficiently
    privileged attacker who can *write* to ``allowed_root`` could swap
    the resolved file for a symlink pointing outside the root. Closing
    that window completely would require ``O_NOFOLLOW`` semantics with an
    fd-based open, which Python's ``Path.read_bytes`` does not expose.
    The threat model intentionally requires that **``allowed_root`` is a
    directory the attacker cannot write to** (e.g. a read-only mount, a
    directory owned by a different uid, or a temp directory created with
    mode 0o700). Operators who need stricter guarantees should layer
    OS-level capabilities (chroot, namespaces, AppArmor) on top.
    """
    try:
        resolved = Path(path).resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise PathTraversalError(path, allowed_root) from exc
    if allowed_root is None:
        return resolved
    root = Path(allowed_root).resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise PathTraversalError(path, allowed_root)
    return resolved


@dataclass(slots=True, frozen=True)
class RdfLoadStats:
    """Statistics from an RDF load operation."""

    total_triples: int
    nodes: int
    edges: int
    literal_properties: int
    load_time_ms: int


def _to_stats(d: dict) -> RdfLoadStats:
    """Convert the raw stats dict from Rust into a typed dataclass."""
    return RdfLoadStats(
        total_triples=d["total_triples"],
        nodes=d["nodes"],
        edges=d["edges"],
        literal_properties=d["literal_properties"],
        load_time_ms=d["load_time_ms"],
    )


# Format aliases used by load_rdf / load_rdf_string
_EXT_TO_FORMAT: dict[str, str] = {
    ".ttl": "turtle",
    ".nt": "ntriples",
    ".nq": "nquads",
    ".trig": "trig",
    ".rdf": "rdfxml",
    ".xml": "rdfxml",
    ".owl": "rdfxml",
}


def load_rdf(
    path_or_data: str | Path,
    format: str | None = None,
    *,
    settings: Any = None,
    is_path: bool | None = None,
) -> tuple[Graph, RdfLoadStats]:
    """Load RDF from a file path or a string.

    By default a string is treated as inline RDF data (and ``format`` is
    required). Pass a :class:`pathlib.Path` or set ``is_path=True`` to force
    file loading. The file-loading path is gated by
    :class:`KaosGraphSettings.allowed_root` (audit A2-#1) — without an
    allowlist, file reads are refused.

    Args:
        path_or_data: File path or inline RDF string.
        format: Explicit format (``"turtle"``, ``"ntriples"``, ``"rdfxml"``,
            ``"nquads"``, ``"trig"``). Required for inline strings; optional
            for file loading (auto-detected from extension when omitted).
        settings: Optional :class:`KaosGraphSettings` providing caps and the
            file allowlist.
        is_path: ``True`` forces file loading, ``False`` forces string parsing.
            Default ``None`` infers from ``path_or_data`` type.

    Returns:
        Tuple of (Graph, RdfLoadStats).

    Raises:
        PathTraversalError: file loading attempted without an allowed_root
            or path resolves outside it.
        ValueError: format missing for string input, or input exceeds caps.
    """
    max_bytes, max_triples, allowed_root = _resolve_caps(settings)

    # Decide path vs string.
    treat_as_path: bool
    if is_path is not None:
        treat_as_path = is_path
    elif isinstance(path_or_data, Path):
        treat_as_path = True
    else:
        # Conservative default: never auto-load a file via .exists() probe
        # (that's the original TOCTOU vector). Strings are inline data unless
        # the caller is explicit. Backwards-incompatible by design.
        treat_as_path = False

    if treat_as_path:
        return _load_file(str(path_or_data), format, max_bytes, max_triples, allowed_root)

    if format is None:
        raise ValueError(
            "format is required when loading RDF from a string. "
            "Supported: turtle, ntriples, rdfxml, nquads, trig"
        )
    if not isinstance(path_or_data, str):
        raise TypeError("Inline RDF data must be a str.")
    py_graph, stats_dict = _raw.load_rdf_string(path_or_data, format, max_bytes, max_triples)
    return Graph._from_inner(py_graph), _to_stats(stats_dict)


def _load_file(
    path: str,
    format: str | None,
    max_bytes: int,
    max_triples: int,
    allowed_root: str | None,
) -> tuple[Graph, RdfLoadStats]:
    """Load an RDF file under the configured allowlist + caps."""
    resolved = _check_allowlist(path, allowed_root)
    if format is not None:
        # Caller wants to force a format regardless of extension. Stat the
        # file BEFORE reading so an oversized file doesn't allocate first
        # then refuse second (audit follow-up #4).
        size = resolved.stat().st_size
        if size > max_bytes:
            raise ValueError(
                f"RDF file is {size} bytes; max_bytes is {max_bytes}. "
                "Raise KaosGraphSettings.max_bytes if intended."
            )
        text = resolved.read_text(encoding="utf-8", errors="replace")
        py_graph, stats_dict = _raw.load_rdf_string(text, format, max_bytes, max_triples)
    else:
        py_graph, stats_dict = _raw.load_rdf_file(str(resolved), max_bytes, max_triples)
    return Graph._from_inner(py_graph), _to_stats(stats_dict)


def to_turtle(graph: Graph) -> str:
    """Export a Graph to Turtle format string.

    Each edge becomes an RDF triple. The edge's ``predicate`` property (if
    present) becomes the predicate IRI; otherwise
    ``http://kaos.273v.com/graph#relatedTo`` is used.  Node IDs starting with
    ``_:`` are emitted as blank nodes.

    Args:
        graph: The graph to export.

    Returns:
        Turtle-formatted RDF string.
    """
    return _raw.export_turtle(graph._inner)


def to_ntriples(graph: Graph) -> str:
    """Export a Graph to N-Triples format string.

    Same triple-generation logic as :func:`to_turtle` but serialized in
    the line-oriented N-Triples format.

    Args:
        graph: The graph to export.

    Returns:
        N-Triples-formatted RDF string.
    """
    return _raw.export_ntriples(graph._inner)


def to_jsonld(graph: Graph) -> str:
    """Export a Graph to JSON-LD format string.

    Edges are grouped by subject in a ``@graph`` array.  Each subject
    node lists its predicate-object pairs.  The edge's ``predicate``
    property (if present) becomes the JSON-LD key; otherwise
    ``http://kaos.273v.com/graph#relatedTo`` is used.

    Args:
        graph: The graph to export.

    Returns:
        JSON-LD formatted string.
    """
    return _raw.export_jsonld(graph._inner)


def load_owl(
    path: str | Path,
    *,
    settings: Any = None,
) -> tuple[Graph, RdfLoadStats]:
    """Convenience loader for OWL ontology files (RDF/XML format).

    The argument is always treated as a file path (``is_path=True``);
    inline OWL strings should go through :func:`load_rdf` directly.

    Args:
        path: Path to the ``.owl`` file.
        settings: Optional :class:`KaosGraphSettings` providing caps and
            allowlist.

    Returns:
        Tuple of (Graph, RdfLoadStats).
    """
    return load_rdf(path, format="rdfxml", settings=settings, is_path=True)


_SPARQL_NAMES = ("SparqlResult", "query_sparql", "query_sparql_ask")


def __getattr__(name: str) -> object:
    """Lazy import for optional SPARQL support (requires pyoxigraph)."""
    if name in _SPARQL_NAMES:
        from kaos_graph.rdf.sparql import SparqlResult, query_sparql, query_sparql_ask

        _lazy = {
            "query_sparql": query_sparql,
            "query_sparql_ask": query_sparql_ask,
            "SparqlResult": SparqlResult,
        }
        return _lazy[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# A2-#14a: ``__all__`` controls ``from kaos_graph.rdf import *``. Listing the
# SPARQL names unconditionally makes the star-import abort with ImportError
# when pyoxigraph is missing; only advertise them when the import succeeds.
__all__: list[str] = [
    "RdfLoadStats",
    "load_owl",
    "load_rdf",
    "to_jsonld",
    "to_ntriples",
    "to_turtle",
]

try:  # pragma: no cover — exercised only when pyoxigraph is installed
    import pyoxigraph as _pyoxigraph

    __all__.extend(_SPARQL_NAMES)
    del _pyoxigraph
except ImportError:
    pass
